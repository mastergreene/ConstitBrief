"""Standard-response library (SQLite-backed)."""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from ..db import get_conn, now_iso

_WORD = re.compile(r"[a-z0-9']+")
_STOP = frozenset(
    "a an and are as at be but by for from has have he her his i if in is it its me my of on "
    "or our she so that the their them they this to was we were what when which who will with "
    "you your about can not no do does did get got been".split()
)


def _row(r: sqlite3.Row) -> dict[str, Any]:
    d = dict(r)
    d["tags"] = json.loads(d.get("tags") or "[]")
    d["source_urls"] = json.loads(d.get("source_urls") or "[]")
    d["needs_review"] = bool(d.get("needs_review"))
    return d


def list_templates(category: str | None = None, q: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM templates"
    args: list[Any] = []
    where = []
    if category:
        where.append("category = ?")
        args.append(category)
    if q:
        where.append("(title LIKE ? OR summary LIKE ? OR body LIKE ? OR tags LIKE ?)")
        like = f"%{q}%"
        args += [like, like, like, like]
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY category, title"
    with get_conn() as conn:
        return [_row(r) for r in conn.execute(sql, args)]


def get_template(tid: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        r = conn.execute("SELECT * FROM templates WHERE id = ?", (tid,)).fetchone()
    return _row(r) if r else None


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "template"


def create_template(data: dict[str, Any]) -> dict[str, Any]:
    slug = data.get("slug") or _slugify(data["title"])
    with get_conn() as conn:
        base, n = slug, 2
        while conn.execute("SELECT 1 FROM templates WHERE slug = ?", (slug,)).fetchone():
            slug, n = f"{base}-{n}", n + 1
        cur = conn.execute(
            """INSERT INTO templates (slug, title, category, tags, summary, sms, body,
               source_urls, needs_review, last_reviewed, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                slug, data["title"], data["category"], json.dumps(data.get("tags", [])),
                data.get("summary", ""), data.get("sms", ""), data.get("body", ""),
                json.dumps(data.get("source_urls", [])), 0, now_iso()[:10], now_iso(),
            ),
        )
        tid = cur.lastrowid
    return get_template(tid)  # type: ignore[return-value]


def update_template(tid: int, data: dict[str, Any]) -> dict[str, Any] | None:
    current = get_template(tid)
    if not current:
        return None
    merged = {**current, **{k: v for k, v in data.items() if v is not None}}
    with get_conn() as conn:
        conn.execute(
            """UPDATE templates SET title=?, category=?, tags=?, summary=?, sms=?, body=?,
               source_urls=?, needs_review=0, last_reviewed=?, updated_at=? WHERE id=?""",
            (
                merged["title"], merged["category"], json.dumps(merged["tags"]),
                merged["summary"], merged["sms"], merged["body"],
                json.dumps(merged["source_urls"]), now_iso()[:10], now_iso(), tid,
            ),
        )
    return get_template(tid)


def delete_template(tid: int) -> bool:
    with get_conn() as conn:
        return conn.execute("DELETE FROM templates WHERE id = ?", (tid,)).rowcount > 0


def _terms(text: str) -> set[str]:
    return {w for w in _WORD.findall((text or "").lower()) if w not in _STOP and len(w) > 2}


def suggest(notes: str, category: str, limit: int = 5) -> list[dict[str, Any]]:
    """Rank templates for the notes: same-category first, then keyword overlap."""
    terms = _terms(notes)
    text = (notes or "").lower()
    scored = []
    for t in list_templates():
        score = 0.0
        if t["category"] == category:
            score += 2.0
        elif t["category"] == "general":
            score += 0.3
        for tag in t["tags"]:
            tag_l = tag.lower()
            if " " in tag_l and tag_l in text:
                score += 2.0
            elif tag_l in terms:
                score += 1.5
        score += 0.4 * len(terms & _terms(t["title"]))
        if score > 0.3:
            scored.append((score, t))
    scored.sort(key=lambda x: (-x[0], x[1]["title"]))
    return [dict(t, score=round(s, 2)) for s, t in scored[:limit]]
