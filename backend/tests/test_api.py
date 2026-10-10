"""Auth, interactions, handoff lifecycle and controls (API level)."""
import json

import httpx
import pytest

from backend.app import auth
from backend.app.services import handoff, jev

from .conftest import HDR, PASSWORD

VALID = {"first_name": "Test", "last_name": "Synthetic", "address_line1": "1 Example St",
         "suburb": "Sunnybank", "state": "QLD"}


# ---------------------------------------------------------------- auth & controls --
def test_api_requires_sign_in(anon):
    for path in ("/api/meta", "/api/interactions", "/api/templates"):
        assert anon.get(path).status_code == 401
    assert anon.get("/api/health").status_code == 200
    assert anon.get("/").status_code == 200  # app shell holds no case data


def test_login_rejects_bad_password_and_throttles(anon):
    for _ in range(auth.MAX_FAILURES):
        r = anon.post("/api/auth/login", json={"username": "alex", "password": "wrong"}, headers=HDR)
        assert r.status_code == 401
    r = anon.post("/api/auth/login", json={"username": "alex", "password": PASSWORD}, headers=HDR)
    assert r.status_code == 429
    auth._failures.clear()


def test_session_cookie_flags(anon):
    r = anon.post("/api/auth/login", json={"username": "alex", "password": PASSWORD}, headers=HDR)
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


def test_csrf_header_required_for_writes(client):
    r = client.post("/api/interactions", headers={"X-ConstitBrief": ""})
    assert r.status_code == 403


def test_logout_ends_session(client):
    client.post("/api/auth/logout")
    assert client.get("/api/meta").status_code == 401


def test_security_headers(client):
    r = client.get("/api/meta")
    assert r.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in client.get("/").headers["content-security-policy"]


# ----------------------------------------------------------------- interactions --
def test_interaction_save_conflict_and_isolation(client, other):
    it = client.post("/api/interactions").json()
    assert it["ref"].startswith("CB-")
    r = client.put(f"/api/interactions/{it['id']}", json={"version": 0, "notes": "synthetic", "state": {}})
    assert r.json()["version"] == 1
    stale = client.put(f"/api/interactions/{it['id']}", json={"version": 0, "notes": "x", "state": {}})
    assert stale.status_code == 409
    assert other.get(f"/api/interactions/{it['id']}").status_code == 404  # another officer


def test_clear_interaction_wipes_content_but_keeps_handoff_log(client):
    it = client.post("/api/interactions").json()
    client.put(f"/api/interactions/{it['id']}", json={"version": 0, "notes": "Synthetic notes",
                                                      "state": {"values": VALID}})
    prep = client.post("/api/handoffs/prepare", json={"interaction_id": it["id"], "type_id": "ndis",
                                                      "form_option": "Help with an NDIS issue",
                                                      "values": VALID}).json()
    assert client.delete(f"/api/interactions/{it['id']}").status_code == 204
    assert client.get(f"/api/interactions/{it['id']}").status_code == 404
    from backend.app import db
    with db.get_conn() as conn:
        row = conn.execute("SELECT notes, state FROM interactions WHERE id = ?", (it["id"],)).fetchone()
        log = conn.execute("SELECT * FROM handoffs WHERE id = ?", (prep["handoff"]["id"],)).fetchone()
    assert row["notes"] == "" and row["state"] == "{}"
    assert log is not None and "Synthetic" not in json.dumps(dict(log))


def test_expired_drafts_purged(client):
    from backend.app import db
    it = client.post("/api/interactions").json()
    with db.get_conn() as conn:
        conn.execute("UPDATE interactions SET expires_at = '2000-01-01T00:00:00+00:00' WHERE id = ?", (it["id"],))
    db.purge_expired()
    assert client.get(f"/api/interactions/{it['id']}").status_code == 404


def test_unknown_record_fields_dropped(client):
    it = client.post("/api/interactions").json()
    client.put(f"/api/interactions/{it['id']}", json={"version": 0, "notes": "", "state": {"values": {"evil": "x", "phone": "1"}}})
    assert client.get(f"/api/interactions/{it['id']}").json()["state"]["values"] == {"phone": "1"}


# ---------------------------------------------------------------------- analyse --
def test_analyse_endpoint_echoes_seq(client):
    r = client.post("/api/analyse", json={"notes": "NDIS plan", "state": {}, "seq": 42}).json()
    assert r["seq"] == 42 and r["active_types"] == ["ndis"] and r["model_status"] == "not_requested"


def test_ai_unavailable_falls_back_to_rules(client, set_setting, monkeypatch):
    set_setting("analysis_provider", "jev")
    set_setting("openrouter_api_key", "sk-test")
    real = httpx.AsyncClient
    monkeypatch.setattr(jev.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(lambda r: httpx.Response(503))))
    r = client.post("/api/analyse", json={"notes": "NDIS plan cut", "state": {}, "model": True}).json()
    assert r["model_status"] == "unavailable" and r["active_types"] == ["ndis"]


# ---------------------------------------------------------------------- handoff --
def _new(client, values=VALID):
    it = client.post("/api/interactions").json()
    body = {"interaction_id": it["id"], "type_id": "ndis", "form_option": "Help with an NDIS issue",
            "values": values, "summary": {"issue": "Synthetic issue"}}
    return it, body


def test_missing_mandatory_blocks_opening(client):
    it, body = _new(client, {"first_name": "Test"})
    prep = client.post("/api/handoffs/prepare", json=body).json()
    assert not prep["valid"] and prep["errors"]
    r = client.post(f"/api/handoffs/{prep['handoff']['id']}/opened",
                    json={"payload_hash": prep["handoff"]["payload_hash"]})
    assert r.status_code == 422


def test_valid_lifecycle_and_duplicate_prevention(client):
    it, body = _new(client)
    prep = client.post("/api/handoffs/prepare", json=body).json()
    hid, phash = prep["handoff"]["id"], prep["handoff"]["payload_hash"]
    assert prep["valid"] and prep["form_url"].endswith("typeA=Help+with+an+NDIS+issue")
    # Preparing again before submission reuses the same handoff (no duplicates on retry).
    again = client.post("/api/handoffs/prepare", json=body).json()
    assert again["handoff"]["id"] == hid
    # Opening with a stale review is refused.
    assert client.post(f"/api/handoffs/{hid}/opened", json={"payload_hash": "stale"}).status_code == 409
    opened = client.post(f"/api/handoffs/{hid}/opened", json={"payload_hash": phash}).json()
    assert opened["status"] == "opened"
    # Double-click on open is harmless.
    assert client.post(f"/api/handoffs/{hid}/opened", json={"payload_hash": phash}).json()["status"] == "opened"
    rep = client.post(f"/api/handoffs/{hid}/report", json={"submitted": True, "submission_id": "123"}).json()
    assert rep["status"] == "reported_submitted" and rep["submission_id"] == "123"
    # Retrying after submission is blocked unless staff explicitly ask for an additional one.
    dup = client.post("/api/handoffs/prepare", json=body)
    assert dup.status_code == 409 and dup.json()["detail"]["existing"][0]["id"] == hid
    extra = client.post("/api/handoffs/prepare", json={**body, "additional": True}).json()
    assert extra["handoff"]["id"] != hid and extra["handoff"]["ref"].endswith("-2")
    # Can't cancel something already submitted.
    assert client.post(f"/api/handoffs/{hid}/cancel").status_code == 409


def test_staff_can_report_not_submitted(client):
    it, body = _new(client)
    prep = client.post("/api/handoffs/prepare", json=body).json()
    hid = prep["handoff"]["id"]
    client.post(f"/api/handoffs/{hid}/opened", json={"payload_hash": prep["handoff"]["payload_hash"]})
    assert client.post(f"/api/handoffs/{hid}/report", json={"submitted": False}).json()["status"] == "prepared"


def test_other_officer_cannot_touch_handoff(client, other):
    it, body = _new(client)
    prep = client.post("/api/handoffs/prepare", json=body).json()
    r = other.post(f"/api/handoffs/{prep['handoff']['id']}/opened", json={"payload_hash": "x"})
    assert r.status_code == 404


def test_verification_finds_reference(client, set_setting, monkeypatch):
    set_setting("jotform_api_key", "jf-test")
    it, body = _new(client)
    prep = client.post("/api/handoffs/prepare", json=body).json()
    hid, ref = prep["handoff"]["id"], prep["handoff"]["ref"]
    client.post(f"/api/handoffs/{hid}/opened", json={"payload_hash": prep["handoff"]["payload_hash"]})
    seen = {}

    def handler(req):
        seen["key"] = req.headers.get("APIKEY")
        return httpx.Response(200, json={"content": [
            {"id": "999", "answers": {"37": {"answer": f"Synthetic\n\nConstitBrief ref: {ref}"}}}]})

    real = httpx.AsyncClient
    monkeypatch.setattr(handoff.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler)))
    r = client.post(f"/api/handoffs/{hid}/verify").json()
    assert seen["key"] == "jf-test"
    assert r["found"] and r["handoff"]["status"] == "confirmed" and r["handoff"]["submission_id"] == "999"


def test_verification_unavailable_without_key(client):
    it, body = _new(client)
    prep = client.post("/api/handoffs/prepare", json=body).json()
    assert client.post(f"/api/handoffs/{prep['handoff']['id']}/verify").status_code == 501


def test_unknown_form_option_rejected(client):
    it, body = _new(client)
    r = client.post("/api/handoffs/prepare", json={**body, "form_option": "Party Member Inquiry"})
    assert r.status_code == 422


# ---------------------------------------------------------------------- library --
def test_guidance_only_shows_approved_and_only_admin_edits(client, admin):
    assert client.post("/api/guidance", json={"types": ["services_australia"], "notes": "mygov link"}).json() == []
    t = next(x for x in client.get("/api/templates").json() if x["slug"] == "mygov-link-centrelink")
    assert client.patch(f"/api/templates/{t['id']}", json={"approve": True}).status_code == 403
    approved = admin.patch(f"/api/templates/{t['id']}", json={"approve": True}).json()
    assert not approved["needs_review"] and approved["reviewed_by"] == "Admin"
    got = client.post("/api/guidance", json={"types": ["services_australia"], "notes": "mygov linking"}).json()
    assert [g["slug"] for g in got] == ["mygov-link-centrelink"]
    edited = admin.patch(f"/api/templates/{t['id']}", json={"body": "changed"}).json()
    assert edited["needs_review"]  # an edit needs re-approval


# ------------------------------------------------------------------- jev provider --
def test_jev_request_is_redacted_and_typed():
    body = jev.build_request("Jo on 0412 345 678 CRN 123456789A wants a grant", {"first_name": "Jo"},
                             [{"key": "form:4", "label": "Name"}])
    dumped = json.dumps(body["state"])
    assert "0412" not in dumped and "123456789A" not in dumped and "Jo " not in dumped
    assert body["questions"]["type__grant"]["type"] == "noul"
    assert "cover__form:4" in body["questions"]


def test_jev_response_validated():
    out = jev.parse_response({"answers": {
        "type__grant": {"type": "noul", "noul": 0.9}, "type__bogus": {"noul": 0.99},
        "cover__form:4": {"noul": 0.95}, "cover__injected": {"noul": 0.99},
        "type__media": {"noul": "high"}}}, {"form:4"})
    assert out["types"] == {"grant": 0.9} and out["covered"] == ["form:4"]


def test_generate_ack_makes_no_promises(client):
    d = client.post("/api/generate", json={"type_id": "event_invitation", "values": {"first_name": "Test"}}).json()
    assert "check her availability" in d["email"] and "will attend" not in d["email"]
    g = client.post("/api/generate", json={"type_id": "grant", "values": {}}).json()
    assert "can't guarantee funding" in g["email"]


def test_bootstrap_admin_only_when_no_users(set_setting, tmp_path):
    import sqlite3

    from backend.app import db
    set_setting("bootstrap_admin_username", "boot")
    set_setting("bootstrap_admin_password", "bootstrap-pass-1")
    fresh = tmp_path / "fresh.sqlite3"
    db.init_db(fresh)
    rows = sqlite3.connect(fresh).execute("SELECT username, role FROM users").fetchall()
    assert rows == [("boot", "admin")]
    db._initialised.discard(fresh)
    set_setting("bootstrap_admin_username", "second")
    db.init_db(fresh)  # users exist: nothing added
    assert sqlite3.connect(fresh).execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
