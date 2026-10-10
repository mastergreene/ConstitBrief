from __future__ import annotations

import json
import secrets
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from .. import auth, db
from ..config import settings, storage_is_ephemeral
from ..schemas import (AnalyseIn, GenerateIn, GuidanceIn, InteractionSave, LoginIn, OpenIn, PrepareIn,
                       ReportIn, SearchIn, TemplateIn, TemplatePatch)
from ..services import analysis, drafts, formmap, handoff, jev, search, taxonomy, templates

router = APIRouter(prefix="/api")
Authed = Depends(auth.current_user)


@router.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True}


# ---- Auth ------------------------------------------------------------------
@router.post("/auth/login")
def login(body: LoginIn, request: Request, response: Response) -> dict[str, Any]:
    return auth.login(body.username, body.password, response,
                      request.client.host if request.client else "?")


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response) -> None:
    auth.logout(request, response)


@router.get("/auth/me")
def me(user: dict = Authed) -> dict[str, Any]:
    return user


# ---- Meta ------------------------------------------------------------------
@router.get("/meta")
def meta(user: dict = Authed) -> dict[str, Any]:
    return {
        **taxonomy.meta(),
        "form": {**formmap.summary_for_docs(),
                 "branches": {opt: [{"qid": e["qid"], "label": e.get("label_override") or
                                     next(f["label"] for f in formmap.snapshot()["fields"] if f["qid"] == e["qid"]),
                                     "record": e.get("record"), "transform": e["transform"]}
                                    for e in b["fields"]]
                              for opt, b in formmap.mapping()["branches"].items()}},
        "features": {
            "analysis_model": jev.enabled(),
            "search_provider": search.provider(),
            "draft_model": bool(settings.openrouter_api_key and settings.generate_model),
            "jotform_verification": handoff.verification_available(),
            "prefill_contact": settings.jotform_prefill_contact,
            "ephemeral_storage": storage_is_ephemeral(),
        },
        "draft_retention_hours": settings.draft_retention_hours,
        "office": {"signoff": settings.office_signoff, "name": settings.office_name},
    }


# ---- Interactions (draft recovery) ------------------------------------------
def _ref() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "CB-" + "".join(secrets.choice(alphabet) for _ in range(6))


def _interaction_out(r: Any) -> dict[str, Any]:
    d = dict(r)
    d["state"] = json.loads(d["state"] or "{}")
    return d


def _own(conn: Any, iid: str, user: dict) -> Any:
    row = conn.execute("SELECT * FROM interactions WHERE id = ? AND status = 'open'", (iid,)).fetchone()
    if not row or (row["officer_id"] != user["id"] and user["role"] != "admin"):
        raise HTTPException(404, "Interaction not found or expired")
    return row


@router.post("/interactions", status_code=201)
def create_interaction(user: dict = Authed) -> dict[str, Any]:
    db.purge_expired()
    iid, ts = str(uuid.uuid4()), db.now_iso()
    with db.get_conn() as conn:
        for _ in range(5):
            ref = _ref()
            if not conn.execute("SELECT 1 FROM interactions WHERE ref = ?", (ref,)).fetchone():
                break
        conn.execute("INSERT INTO interactions (id, ref, officer_id, created_at, updated_at, expires_at) "
                     "VALUES (?,?,?,?,?,?)", (iid, ref, user["id"], ts, ts,
                                               db.expiry(settings.draft_retention_hours)))
        return _interaction_out(_own(conn, iid, user))


@router.get("/interactions")
def list_interactions(user: dict = Authed) -> list[dict[str, Any]]:
    db.purge_expired()
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT id, ref, created_at, updated_at, expires_at, substr(notes, 1, 120) AS preview "
            "FROM interactions WHERE officer_id = ? AND status = 'open' ORDER BY updated_at DESC LIMIT 30",
            (user["id"],)).fetchall()
    return [dict(r) for r in rows]


@router.get("/interactions/{iid}")
def get_interaction(iid: str, user: dict = Authed) -> dict[str, Any]:
    with db.get_conn() as conn:
        out = _interaction_out(_own(conn, iid, user))
    out["handoffs"] = handoff.list_for(iid)
    return out


@router.put("/interactions/{iid}")
def save_interaction(iid: str, body: InteractionSave, user: dict = Authed) -> dict[str, Any]:
    with db.get_conn() as conn:
        row = _own(conn, iid, user)
        if row["version"] != body.version:
            raise HTTPException(409, "This interaction was changed elsewhere. Reload it.")
        ts = db.now_iso()
        conn.execute("UPDATE interactions SET notes=?, state=?, version=version+1, updated_at=?, "
                     "expires_at=? WHERE id=?",
                     (body.notes, json.dumps(body.state.model_dump()), ts,
                      db.expiry(settings.draft_retention_hours), iid))
        return {"version": row["version"] + 1, "updated_at": ts}


@router.delete("/interactions/{iid}", status_code=204)
def clear_interaction(iid: str, user: dict = Authed) -> None:
    """Wipe notes and record. The handoff audit trail (no case content) is kept."""
    with db.get_conn() as conn:
        _own(conn, iid, user)
        conn.execute("UPDATE interactions SET status='cleared', notes='', state='{}', updated_at=? "
                     "WHERE id=?", (db.now_iso(), iid))


# ---- Analysis ----------------------------------------------------------------
@router.post("/analyse")
async def analyse(body: AnalyseIn, user: dict = Authed) -> dict[str, Any]:
    state = body.state.model_dump()
    result = analysis.analyse(body.notes, state)
    if body.model:
        open_items = [i for i in result["checklist"] if i["status"] == "missing"]
        model = await jev.decide(body.notes, state["values"], open_items)
        if model is not None:
            result = analysis.analyse(body.notes, state, model)
            result["model_status"] = "ok"
        else:
            result["model_status"] = "unavailable" if jev.enabled() else "off"
    else:
        result["model_status"] = "not_requested"
    result["seq"] = body.seq
    return result


# ---- Handoffs ----------------------------------------------------------------
def _handoff_call(fn, *args):
    try:
        return fn(*args)
    except handoff.HandoffError as e:
        raise HTTPException(e.status, {"message": e.message, **e.extra}) from e


@router.post("/handoffs/prepare")
def prepare_handoff(body: PrepareIn, user: dict = Authed) -> dict[str, Any]:
    return _handoff_call(handoff.prepare, user, body.interaction_id, body.type_id, body.form_option,
                         body.values, body.summary, body.approved_actions, body.confirmed_deadlines,
                         body.additional)


@router.post("/handoffs/{hid}/opened")
def opened(hid: int, body: OpenIn, user: dict = Authed) -> dict[str, Any]:
    return _handoff_call(handoff.mark_opened, user, hid, body.payload_hash)


@router.post("/handoffs/{hid}/report")
def report(hid: int, body: ReportIn, user: dict = Authed) -> dict[str, Any]:
    return _handoff_call(handoff.report, user, hid, body.submitted, body.submission_id)


@router.post("/handoffs/{hid}/cancel")
def cancel(hid: int, user: dict = Authed) -> dict[str, Any]:
    return _handoff_call(handoff.cancel, user, hid)


@router.post("/handoffs/{hid}/verify")
async def verify(hid: int, user: dict = Authed) -> dict[str, Any]:
    try:
        return await handoff.verify(user, hid)
    except handoff.HandoffError as e:
        raise HTTPException(e.status, {"message": e.message, **e.extra}) from e


# ---- Guidance library & search ----------------------------------------------
@router.get("/templates")
def list_templates(category: str | None = None, q: str | None = None,
                   user: dict = Authed) -> list[dict[str, Any]]:
    return templates.list_templates(category, q)


@router.post("/guidance")
def guidance(body: GuidanceIn, user: dict = Authed) -> list[dict[str, Any]]:
    """Approved (reviewed) library entries relevant to the active enquiry types."""
    return templates.suggest(body.notes, [t for t in body.types if t in taxonomy.TYPE_BY_ID],
                             approved_only=True)


@router.post("/templates", status_code=201)
def create_template(body: TemplateIn, user: dict = Depends(auth.require_admin)) -> dict[str, Any]:
    return templates.create_template(body.model_dump(), user)


@router.patch("/templates/{tid}")
def update_template(tid: int, body: TemplatePatch,
                    user: dict = Depends(auth.require_admin)) -> dict[str, Any]:
    t = templates.update_template(tid, body.model_dump(exclude_unset=True), user)
    if not t:
        raise HTTPException(404, "Template not found")
    return t


@router.delete("/templates/{tid}", status_code=204)
def delete_template(tid: int, user: dict = Depends(auth.require_admin)) -> None:
    if not templates.delete_template(tid):
        raise HTTPException(404, "Template not found")


@router.post("/search")
async def run_search(body: SearchIn, user: dict = Authed) -> dict[str, Any]:
    return await search.search(body.q, body.type_id, body.domains)


@router.post("/generate")
async def generate(body: GenerateIn, user: dict = Authed) -> dict[str, Any]:
    tmpl = [t for t in (templates.get_template(i) for i in body.template_ids) if t and not t["needs_review"]]
    return await drafts.generate(body.type_id, body.values, body.notes, tmpl, body.polish)
