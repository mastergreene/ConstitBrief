"""Reviewed handoff into the existing Jotform.

Why not submit server-side? Jotform support states that submissions created through the
API do not fire the form's email notifications or integrations, which would bypass the
office's five configured destinations. So the submission itself always happens in the real
form, by a staff member. This module:

  prepared  -> validated, field-by-field copy produced (no submission yet)
  opened    -> staff opened the form to submit; outcome UNCERTAIN until reported/confirmed
  reported_submitted -> staff say they submitted it
  confirmed -> found in Jotform by its reference (needs a read-only JOTFORM_API_KEY)
  cancelled

Duplicate guard: one live handoff per (interaction, form option). Once a handoff is
reported or confirmed, preparing the same option again requires an explicit
"additional submission" confirmation. Handoff rows store no notes or field values.
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timedelta
from typing import Any

import httpx

from ..config import settings
from ..db import get_conn, now_iso
from . import formmap, taxonomy

_lock = threading.Lock()
LIVE = ("prepared", "opened")
DONE = ("reported_submitted", "confirmed")


class HandoffError(Exception):
    def __init__(self, status: int, message: str, extra: dict[str, Any] | None = None):
        super().__init__(message)
        self.status, self.message, self.extra = status, message, extra or {}


def _row(r: Any) -> dict[str, Any]:
    d = dict(r)
    d["valid"] = bool(d["valid"])
    return d


def _interaction(conn: Any, interaction_id: str, user: dict[str, Any]) -> Any:
    row = conn.execute("SELECT * FROM interactions WHERE id = ? AND status = 'open'",
                       (interaction_id,)).fetchone()
    if not row or (row["officer_id"] != user["id"] and user["role"] != "admin"):
        raise HandoffError(404, "Interaction not found")
    return row


def list_for(interaction_id: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
        return [_row(r) for r in conn.execute(
            "SELECT * FROM handoffs WHERE interaction_id = ? ORDER BY id", (interaction_id,))]


def prepare(user: dict[str, Any], interaction_id: str, type_id: str, form_option: str,
            values: dict[str, Any], summary: dict[str, str], approved_actions: list[str],
            confirmed_deadlines: list[str], additional: bool = False) -> dict[str, Any]:
    if type_id not in taxonomy.TYPE_BY_ID:
        raise HandoffError(422, "Unknown enquiry type")
    if form_option not in formmap.form_options():
        raise HandoffError(422, "That option is not on the Jotform")
    extra = [("Staff-approved follow-up", a) for a in approved_actions if a.strip()]
    extra += [("Deadline (staff confirmed)", d) for d in confirmed_deadlines if d.strip()]
    team = taxonomy.suggested_team([type_id])
    with _lock, get_conn() as conn:
        inter = _interaction(conn, interaction_id, user)
        rows = conn.execute("SELECT * FROM handoffs WHERE interaction_id = ? AND form_option = ? "
                            "AND status != 'cancelled' ORDER BY id", (interaction_id, form_option)).fetchall()
        live = next((r for r in rows if r["status"] in LIVE), None)
        done = [r for r in rows if r["status"] in DONE]
        if done and not live and not additional:
            raise HandoffError(409, "A handoff for this form option has already been submitted.",
                               {"existing": [_row(r) for r in done]})
        if live:
            ref = live["ref"]
        else:
            n = conn.execute("SELECT COUNT(*) FROM handoffs WHERE interaction_id = ?",
                             (interaction_id,)).fetchone()[0] + 1
            ref = f"{inter['ref']}-{n}"
        built = formmap.build(form_option, values, summary, ref, extra)
        payload_hash = hashlib.sha256(json.dumps(built["rows"], sort_keys=True).encode()).hexdigest()[:16]
        if live:
            conn.execute("UPDATE handoffs SET type_id=?, valid=?, payload_hash=?, prepared_at=?, "
                         "status='prepared', approved_by=?, mapping_version=? WHERE id=?",
                         (type_id, int(built["valid"]), payload_hash, now_iso(), user["id"],
                          built["mapping_version"], live["id"]))
            hid = live["id"]
        else:
            hid = conn.execute(
                "INSERT INTO handoffs (interaction_id, ref, type_id, form_option, mapping_version, "
                "status, valid, payload_hash, approved_by, prepared_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (interaction_id, ref, type_id, form_option, built["mapping_version"], "prepared",
                 int(built["valid"]), payload_hash, user["id"], now_iso())).lastrowid
        row = conn.execute("SELECT * FROM handoffs WHERE id = ?", (hid,)).fetchone()
    return {"handoff": _row(row), **built, "team": team,
            "form_url": formmap.safe_url(form_option, values),
            "url_policy": _url_policy()}


def _url_policy() -> str:
    if settings.jotform_prefill_contact:
        return "The link pre-selects the enquiry type and contact details. Nothing else is in the URL."
    if settings.jotform_prefill_type:
        return "The link only pre-selects the enquiry type. Paste the other fields from here."
    return "The link opens a blank form. Paste every field from here."


def _get(conn: Any, handoff_id: int, user: dict[str, Any]) -> Any:
    row = conn.execute("SELECT * FROM handoffs WHERE id = ?", (handoff_id,)).fetchone()
    if not row:
        raise HandoffError(404, "Handoff not found")
    _interaction(conn, row["interaction_id"], user)
    return row


def mark_opened(user: dict[str, Any], handoff_id: int, payload_hash: str) -> dict[str, Any]:
    with _lock, get_conn() as conn:
        row = _get(conn, handoff_id, user)
        if row["status"] in DONE:
            raise HandoffError(409, "This handoff is already recorded as submitted.", {"handoff": _row(row)})
        if row["status"] == "cancelled":
            raise HandoffError(409, "This handoff was cancelled. Prepare it again.")
        if row["payload_hash"] != payload_hash:
            raise HandoffError(409, "The record changed since it was reviewed. Review it again.")
        if not row["valid"]:
            raise HandoffError(422, "Mandatory Jotform fields are missing. Complete them first.")
        conn.execute("UPDATE handoffs SET status='opened', opened_at=COALESCE(opened_at, ?) WHERE id=?",
                     (now_iso(), handoff_id))
        return _row(conn.execute("SELECT * FROM handoffs WHERE id = ?", (handoff_id,)).fetchone())


def report(user: dict[str, Any], handoff_id: int, submitted: bool, submission_id: str = "") -> dict[str, Any]:
    with _lock, get_conn() as conn:
        row = _get(conn, handoff_id, user)
        if row["status"] == "confirmed":
            return _row(row)
        if submitted:
            conn.execute("UPDATE handoffs SET status='reported_submitted', reported_at=?, "
                         "submission_id=COALESCE(NULLIF(?, ''), submission_id) WHERE id=?",
                         (now_iso(), submission_id.strip()[:40], handoff_id))
        else:
            conn.execute("UPDATE handoffs SET status='prepared', note='Staff reported not submitted' "
                         "WHERE id=?", (handoff_id,))
        return _row(conn.execute("SELECT * FROM handoffs WHERE id = ?", (handoff_id,)).fetchone())


def cancel(user: dict[str, Any], handoff_id: int) -> dict[str, Any]:
    with _lock, get_conn() as conn:
        row = _get(conn, handoff_id, user)
        if row["status"] in DONE:
            raise HandoffError(409, "A submitted handoff can't be cancelled here. Withdraw it in Jotform.")
        conn.execute("UPDATE handoffs SET status='cancelled' WHERE id=?", (handoff_id,))
        return _row(conn.execute("SELECT * FROM handoffs WHERE id = ?", (handoff_id,)).fetchone())


def verification_available() -> bool:
    return bool(settings.jotform_api_key)


async def verify(user: dict[str, Any], handoff_id: int,
                 client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    """Look for the handoff reference in recent Jotform submissions (read-only API)."""
    if not verification_available():
        raise HandoffError(501, "Jotform verification is not configured (JOTFORM_API_KEY).")
    with get_conn() as conn:
        row = _get(conn, handoff_id, user)
    if row["status"] == "confirmed":
        return {"found": True, "handoff": _row(row)}
    since = datetime.fromisoformat(row["opened_at"] or row["prepared_at"]) - timedelta(days=1)
    own = client is None
    client = client or httpx.AsyncClient(timeout=10)
    try:
        resp = await client.get(
            f"{settings.jotform_api_base}/form/{settings.jotform_form_id}/submissions",
            params={"limit": 200, "orderby": "created_at",
                    "filter": json.dumps({"created_at:gt": since.strftime("%Y-%m-%d %H:%M:%S")})},
            headers={"APIKEY": settings.jotform_api_key})
        resp.raise_for_status()
        submissions = resp.json().get("content") or []
    except (httpx.HTTPError, ValueError) as exc:
        raise HandoffError(502, f"Couldn't reach Jotform to check ({type(exc).__name__}). "
                                "The handoff status is unchanged.") from exc
    finally:
        if own:
            await client.aclose()
    needle = f"ConstitBrief ref: {row['ref']}"
    match = next((s for s in submissions if needle in json.dumps(s.get("answers") or {})), None)
    if not match:
        return {"found": False, "handoff": _row(row)}
    with _lock, get_conn() as conn:
        conn.execute("UPDATE handoffs SET status='confirmed', confirmed_at=?, submission_id=? WHERE id=?",
                     (now_iso(), str(match.get("id", ""))[:40], handoff_id))
        updated = conn.execute("SELECT * FROM handoffs WHERE id = ?", (handoff_id,)).fetchone()
    return {"found": True, "handoff": _row(updated)}
