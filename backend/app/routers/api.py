from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException

from .. import db
from ..config import settings
from ..schemas import CaseIn, GenerateIn, JotformIn, SearchIn, TemplateIn, TemplatePatch, TriageIn
from ..services import drafts, jev, jotform, rules, search, templates, triage

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True}


@router.get("/meta")
def meta() -> dict[str, Any]:
    return {
        **rules.meta(),
        "jotform": {
            "url": settings.jotform_url,
            "params": jotform.PARAMS,
            "type_param": jotform.TYPE_PARAM,
            "notes_param": jotform.NOTES_PARAM,
            "max_url_length": jotform.MAX_URL_LENGTH,
            "typea": {c.id: jotform.typea_value(c.id) for c in rules.CATEGORIES},
        },
        "features": {
            "jev": jev.enabled(),
            "search_provider": search.provider(),
            "draft_model": bool(settings.openrouter_api_key and settings.generate_model),
            "auth": bool(settings.access_token),
        },
        "office": {"signoff": settings.office_signoff, "name": settings.office_name},
    }


# ---- Triage ----------------------------------------------------------------
@router.post("/triage")
async def run_triage(body: TriageIn) -> dict[str, Any]:
    return await triage.triage(body.notes, body.category, body.data)


# ---- Search ----------------------------------------------------------------
@router.post("/search")
async def run_search(body: SearchIn) -> dict[str, Any]:
    return await search.search(body.q, body.category, body.domains)


# ---- Templates -------------------------------------------------------------
@router.get("/templates")
def list_templates(category: str | None = None, q: str | None = None) -> list[dict[str, Any]]:
    return templates.list_templates(category, q)


@router.get("/templates/{tid}")
def get_template(tid: int) -> dict[str, Any]:
    t = templates.get_template(tid)
    if not t:
        raise HTTPException(404, "Template not found")
    return t


@router.post("/templates", status_code=201)
def create_template(body: TemplateIn) -> dict[str, Any]:
    return templates.create_template(body.model_dump())


@router.patch("/templates/{tid}")
def update_template(tid: int, body: TemplatePatch) -> dict[str, Any]:
    t = templates.update_template(tid, body.model_dump(exclude_unset=True))
    if not t:
        raise HTTPException(404, "Template not found")
    return t


@router.delete("/templates/{tid}", status_code=204)
def delete_template(tid: int) -> None:
    if not templates.delete_template(tid):
        raise HTTPException(404, "Template not found")


@router.post("/templates/reseed")
def reseed() -> dict[str, int]:
    return {"added": db.reseed_missing()}


# ---- Drafts & Jotform ------------------------------------------------------
@router.post("/generate")
async def generate(body: GenerateIn) -> dict[str, Any]:
    tmpl = [t for t in (templates.get_template(i) for i in body.template_ids) if t]
    return await drafts.generate(body.kind, body.category, body.data, body.notes, tmpl, body.polish)


@router.post("/jotform")
def build_jotform(body: JotformIn) -> dict[str, Any]:
    return jotform.build_url(body.category, body.data, body.notes, body.urgency)


# ---- Recent cases ----------------------------------------------------------
def _case_row(r) -> dict[str, Any]:
    d = dict(r)
    d["data"] = json.loads(d["data"] or "{}")
    return d


def _label(data: dict[str, Any], category: str) -> str:
    name = " ".join(str(data.get(k) or "").strip() for k in ("first_name", "last_name")).strip()
    cat = rules.CATEGORY_BY_ID.get(category)
    return f"{name or 'Unnamed'} · {cat.short if cat else category}"


@router.get("/cases")
def list_cases(limit: int = 30) -> list[dict[str, Any]]:
    db.purge_old_cases()
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM cases ORDER BY updated_at DESC LIMIT ?", (max(1, min(limit, 200)),)
        ).fetchall()
    return [_case_row(r) for r in rows]


@router.put("/cases")
def upsert_case(body: CaseIn) -> dict[str, Any]:
    ts = db.now_iso()
    data = {k: v for k, v in body.data.items() if k in rules.FIELD_BY_ID}
    notes = rules.redact_tfn(body.notes)
    with db.get_conn() as conn:
        conn.execute(
            """INSERT INTO cases (client_id, category, mode, label, data, notes, draft, status,
                                  created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(client_id) DO UPDATE SET
                 category=excluded.category, mode=excluded.mode, label=excluded.label,
                 data=excluded.data, notes=excluded.notes, draft=excluded.draft,
                 status=excluded.status, updated_at=excluded.updated_at""",
            (body.client_id, body.category, body.mode, _label(data, body.category),
             json.dumps(data), notes, body.draft, body.status, ts, ts),
        )
        row = conn.execute("SELECT * FROM cases WHERE client_id = ?", (body.client_id,)).fetchone()
    return _case_row(row)


@router.delete("/cases/{client_id}", status_code=204)
def delete_case(client_id: str) -> None:
    with db.get_conn() as conn:
        if conn.execute("DELETE FROM cases WHERE client_id = ?", (client_id,)).rowcount == 0:
            raise HTTPException(404, "Case not found")
