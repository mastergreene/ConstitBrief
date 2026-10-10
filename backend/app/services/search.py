"""Live policy search restricted to official Australian government domains.

Providers (first configured wins): Brave Search API, then Google Programmable
Search. With no provider key the endpoint still returns the curated contact
directory and pre-built site-restricted search links, so the feature degrades
rather than disappears.

Every result is re-checked against the domain allow-list server-side; the
`site:` operators in the query are a hint to the provider, not the control.
"""
from __future__ import annotations

import hashlib
import html
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote_plus, urlparse

import httpx

from ..config import settings
from ..db import get_conn, now_iso

log = logging.getLogger(__name__)

# Key national contact numbers, shown alongside search results. Review periodically.
TYPE_DOMAINS = {
    "services_australia": ("servicesaustralia.gov.au", "my.gov.au"),
    "immigration": ("homeaffairs.gov.au",),
    "ndis": ("ndis.gov.au",),
    "aged_care": ("myagedcare.gov.au",),
    "ato": ("ato.gov.au",),
    "dva": ("dva.gov.au",),
}

# Key national contact numbers, shown alongside search results. Review periodically.
DIRECTORY: dict[str, list[dict[str, str]]] = {
    "services_australia": [
        {"name": "Centrelink - Employment services", "phone": "132 850"},
        {"name": "Centrelink - Families", "phone": "136 150"},
        {"name": "Centrelink - Older Australians", "phone": "132 300"},
        {"name": "Centrelink - Disability, sickness & carers", "phone": "132 717"},
        {"name": "Medicare", "phone": "132 011"},
        {"name": "myGov help desk", "phone": "13 23 07"},
    ],
    "immigration": [
        {"name": "Home Affairs Global Service Centre", "phone": "131 881"},
        {"name": "Citizenship information line", "phone": "131 880"},
    ],
    "ndis": [{"name": "NDIS contact centre", "phone": "1800 800 110"}],
    "aged_care": [{"name": "My Aged Care", "phone": "1800 200 422"}],
    "ato": [{"name": "ATO - individuals", "phone": "13 28 61"},
            {"name": "Inspector-General of Taxation & Taxation Ombudsman", "phone": "1800 199 010"}],
    "dva": [{"name": "DVA", "phone": "1800 838 372"},
            {"name": "Open Arms - Veterans & Families Counselling", "phone": "1800 011 046"}],
    "nbn": [{"name": "Telecommunications Industry Ombudsman", "phone": "1800 062 058"}],
    "general": [
        {"name": "Commonwealth Ombudsman", "phone": "1300 362 072"},
        {"name": "TIS National (interpreters)", "phone": "131 450"},
    ],
}


def allowed(url: str, domains: tuple[str, ...] | list[str]) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return any(host == d or host.endswith("." + d) for d in domains)


def scope_domains(category: str | None, requested: list[str] | None = None) -> list[str]:
    allow = list(settings.search_domains)
    if requested:
        scoped = [d.lower() for d in requested if d.lower() in allow]
        if scoped:
            return scoped
    if category and category in TYPE_DOMAINS:
        scoped = [d for d in TYPE_DOMAINS[category] if d in allow]
        if scoped:
            return scoped
    return allow


def build_query(q: str, domains: list[str]) -> str:
    sites = " OR ".join(f"site:{d}" for d in domains)
    return f"{q} ({sites})" if len(domains) > 1 else f"{q} site:{domains[0]}"


def fallback_links(q: str, domains: list[str]) -> list[dict[str, str]]:
    return [
        {
            "domain": d,
            "url": "https://www.google.com/search?q=" + quote_plus(f"{q} site:{d}"),
        }
        for d in domains
    ]


GOV_PHONE = re.compile(
    r"(?<![\d])(1[38]00[ ]?\d{3}[ ]?\d{3}|13\d[ ]?\d{3}|13[ ]?\d{2}[ ]?\d{2}|"
    r"\(0[2378]\)[ ]?\d{4}[ ]?\d{4}|0[2378][ ]?\d{4}[ ]?\d{4})(?!\d)"
)


def _strip_html(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text or ""))


def _phones(text: str) -> list[str]:
    seen: list[str] = []
    for m in GOV_PHONE.finditer(text or ""):
        p = " ".join(m.group(0).split())
        if p not in seen:
            seen.append(p)
    return seen[:3]


def _cache_key(provider: str, query: str) -> str:
    return hashlib.sha256(f"{provider}|{query}".encode()).hexdigest()


def _cache_get(key: str) -> list[dict[str, Any]] | None:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.search_cache_hours)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT payload, created_at FROM search_cache WHERE cache_key = ?", (key,)
        ).fetchone()
    if not row:
        return None
    if datetime.fromisoformat(row["created_at"]) < cutoff:
        return None
    return json.loads(row["payload"])


def _cache_put(key: str, results: list[dict[str, Any]]) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO search_cache (cache_key, payload, created_at) VALUES (?,?,?)",
            (key, json.dumps(results), now_iso()),
        )


async def _brave(client: httpx.AsyncClient, query: str) -> list[dict[str, Any]]:
    resp = await client.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": 15, "country": "AU", "search_lang": "en"},
        headers={"X-Subscription-Token": settings.brave_api_key, "Accept": "application/json"},
    )
    resp.raise_for_status()
    out = []
    for r in (resp.json().get("web") or {}).get("results", []):
        snippet = r.get("description") or ""
        extra = " ".join(r.get("extra_snippets") or [])
        out.append({"title": r.get("title", ""), "url": r.get("url", ""),
                    "snippet": snippet, "extra": extra})
    return out


async def _google(client: httpx.AsyncClient, query: str) -> list[dict[str, Any]]:
    resp = await client.get(
        "https://www.googleapis.com/customsearch/v1",
        params={"key": settings.google_cse_key, "cx": settings.google_cse_cx, "q": query,
                "num": 10, "gl": "au"},
    )
    resp.raise_for_status()
    return [
        {"title": i.get("title", ""), "url": i.get("link", ""), "snippet": i.get("snippet", ""),
         "extra": ""}
        for i in resp.json().get("items", [])
    ]


def provider() -> str | None:
    if settings.brave_api_key:
        return "brave"
    if settings.google_cse_key and settings.google_cse_cx:
        return "google"
    return None


async def search(
    q: str,
    category: str | None = None,
    domains: list[str] | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    q = " ".join((q or "").split())[:200]
    scoped = scope_domains(category, domains)
    directory = DIRECTORY.get(category or "", []) + (
        DIRECTORY["general"] if category != "general" else []
    )
    base: dict[str, Any] = {
        "query": q,
        "domains": scoped,
        "directory": directory,
        "links": fallback_links(q, scoped) if q else [],
        "results": [],
        "provider": provider(),
        "cached": False,
        "error": None,
    }
    if not q or not base["provider"]:
        return base

    query = build_query(q, scoped)
    key = _cache_key(base["provider"], query)
    cached = _cache_get(key)
    if cached is not None:
        return {**base, "results": cached, "cached": True}

    own_client = client is None
    client = client or httpx.AsyncClient(timeout=8)
    try:
        raw = await (_brave if base["provider"] == "brave" else _google)(client, query)
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("Gov search failed: %s", exc)
        return {**base, "error": "Live search is unavailable right now - use the links below."}
    finally:
        if own_client:
            await client.aclose()

    results = []
    for r in raw:
        if not allowed(r["url"], scoped):
            continue
        results.append(
            {
                "title": _strip_html(r["title"]),
                "url": r["url"],
                "domain": urlparse(r["url"]).hostname,
                "snippet": _strip_html(r["snippet"]),
                "phones": _phones(_strip_html(f"{r['snippet']} {r['extra']}")),
            }
        )
    results = results[:8]
    _cache_put(key, results)
    return {**base, "results": results}
