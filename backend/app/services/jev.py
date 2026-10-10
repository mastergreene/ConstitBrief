"""Jev decision gate (TypeSafe Jev on OpenRouter's Decisions API).

POST {JEV_URL}
  {"model": "typesafe/jev-1.13",
   "state": {...},
   "questions": {"<key>": {"type": "choice"|"noul"|"score", "instructions": ..., "criteria": ...}}}
->
  {"answers": {"<key>": {"type": "choice", "choice": ..., "confidence": ..., "probabilities": {...}},
               "<key>": {"type": "noul", "noul": 0.93},
               "<key>": {"type": "score", "score": 1.4, "confidence": ..., ...}},
   "usage": {...}}

Only PII-redacted notes and booleans describing which form fields are filled
are sent. Names, addresses, phone numbers and identifiers never leave the server.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from ..config import settings
from . import rules

log = logging.getLogger(__name__)

URGENCY_LEVELS = (
    "Routine - information or a standard request with no deadline",
    "Time-sensitive - a deadline, review window or payment date is approaching",
    "Urgent - welfare or safety risk, no income, homelessness, or imminent visa expiry / removal",
)

# A Noul probability at or above this means "the notes already cover it".
NOTES_COVER_THRESHOLD = 0.7


def enabled() -> bool:
    return bool(settings.openrouter_api_key)


def build_request(
    notes: str, category_hint: str | None, data: dict[str, Any], open_reqs: list[dict[str, Any]]
) -> dict[str, Any]:
    state = {
        "office": "Australian federal electorate office (Moreton, Brisbane, Queensland)",
        "caseworker_notes": rules.redact_pii(notes, data)[:8000],
        "caseworker_selected_category": category_hint or "not selected",
        "fields_already_captured": sorted(k for k, v in data.items() if rules._filled(v)),
    }
    questions: dict[str, Any] = {
        "category": {
            "type": "choice",
            "instructions": "Which casework category best fits the constituent's enquiry?",
            "criteria": {c.id: c.description for c in rules.CATEGORIES},
        },
        "needs_representation": {
            "type": "noul",
            "instructions": (
                "Does this matter need the office to make formal representations to an agency "
                "or Minister, rather than being resolved now with information or a referral?"
            ),
            "criteria": {
                "true": "The constituent has an unresolved problem with an agency decision, "
                        "delay, debt, refusal or complaint that they cannot fix themselves.",
                "false": "The constituent needs information, a form, a phone number, a referral "
                         "or a standard request that can be handled on this call.",
            },
        },
        "urgency": {
            "type": "score",
            "instructions": "How urgent is this matter for the constituent?",
            "criteria": list(URGENCY_LEVELS),
        },
    }
    for req in open_reqs:
        q = rules.REQUIREMENTS[req["key"]].notes_question
        if q:
            questions[f"notes_cover__{req['key']}"] = {
                "type": "noul",
                "instructions": f"Do the caseworker notes already provide this? {q}",
                "criteria": {
                    "true": q,
                    "false": "The notes do not say this, or only mention it vaguely.",
                },
            }
    return {"model": settings.jev_model, "state": state, "questions": questions}


async def decide(
    notes: str,
    category_hint: str | None,
    data: dict[str, Any],
    open_reqs: list[dict[str, Any]],
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any] | None:
    """Call Jev. Returns parsed answers, or None if disabled / unavailable."""
    if not enabled() or not (notes or "").strip():
        return None
    payload = build_request(notes, category_hint, data, open_reqs)
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "X-Title": "Moreton Casework Fast-Resolver",
    }
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=settings.jev_timeout)
    try:
        resp = await client.post(settings.jev_url, json=payload, headers=headers)
        resp.raise_for_status()
        return parse_response(resp.json())
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        log.warning("Jev decision call failed, using rule-based triage only: %s", exc)
        return None
    finally:
        if own_client:
            await client.aclose()


def parse_response(body: dict[str, Any]) -> dict[str, Any]:
    answers = body.get("answers") or {}
    out: dict[str, Any] = {"model": body.get("model"), "cost": (body.get("usage") or {}).get("cost")}

    cat = answers.get("category") or {}
    if cat.get("choice") in rules.CATEGORY_BY_ID:
        out["category"] = cat["choice"]
        out["category_confidence"] = float(cat.get("confidence") or 0.0)
        out["category_probabilities"] = cat.get("probabilities") or {}

    rep = answers.get("needs_representation") or {}
    if "noul" in rep:
        out["needs_representation"] = float(rep["noul"])

    urg = answers.get("urgency") or {}
    if "score" in urg:
        # Normalise 0..(n-1) onto 0..1 so the UI doesn't depend on the scale length.
        out["urgency"] = max(0.0, min(1.0, float(urg["score"]) / (len(URGENCY_LEVELS) - 1)))

    covered = []
    for key, ans in answers.items():
        if key.startswith("notes_cover__") and float(ans.get("noul") or 0) >= NOTES_COVER_THRESHOLD:
            covered.append(key.removeprefix("notes_cover__"))
    out["notes_cover"] = covered
    return out
