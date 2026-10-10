import asyncio
import json

import httpx

from backend.app.services import jev, rules, triage

DOC_STYLE_RESPONSE = {
    "id": "gen-dec-1", "model": "typesafe/jev-1.13-20260917", "provider": "TypeSafe",
    "answers": {
        "category": {"type": "choice", "choice": "immigration", "confidence": 0.81,
                     "probabilities": {"immigration": 0.9, "general": 0.1}},
        "needs_representation": {"type": "noul", "noul": 0.92},
        "urgency": {"type": "score", "score": 1.0, "confidence": 0.7,
                    "probabilities": {"0": 0.1, "1": 0.8, "2": 0.1}},
        "notes_cover__lodgement_date": {"type": "noul", "noul": 0.88},
        "notes_cover__outcome": {"type": "noul", "noul": 0.2},
    },
    "usage": {"input_tokens": 500, "output_tokens": 60, "cost": 0.00002},
}


def test_parse_response():
    out = jev.parse_response(DOC_STYLE_RESPONSE)
    assert out["category"] == "immigration"
    assert out["needs_representation"] == 0.92
    assert out["urgency"] == 0.5
    assert out["notes_cover"] == ["lodgement_date"]


def test_request_shape_and_no_pii():
    open_reqs = rules.evaluate_requirements("immigration", {})
    body = jev.build_request("Jo on 0412 345 678, TRN EGO1234567, jo@example.com", None,
                             {"first_name": "Jo", "phone": ""}, open_reqs)
    assert body["model"] == "typesafe/jev-1.13"
    assert set(body) == {"model", "state", "questions"}
    dumped = json.dumps(body["state"])
    for leaked in ("0412", "EGO1234567", "jo@example.com"):
        assert leaked not in dumped
    assert body["state"]["fields_already_captured"] == ["first_name"]
    q = body["questions"]
    assert q["category"]["type"] == "choice" and "immigration" in q["category"]["criteria"]
    assert q["needs_representation"]["type"] == "noul"
    assert q["urgency"]["type"] == "score" and len(q["urgency"]["criteria"]) == 3
    assert "notes_cover__lodgement_date" in q


def _run(coro):
    return asyncio.run(coro)


def test_triage_uses_jev_when_available(set_setting, monkeypatch):
    set_setting("openrouter_api_key", "sk-test")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=DOC_STYLE_RESPONSE)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(jev.httpx, "AsyncClient",
                        lambda **kw: real_client(transport=httpx.MockTransport(handler)))
    out = _run(triage.triage("Partner visa lodged March 2024, still waiting", None, {}))
    assert seen["auth"] == "Bearer sk-test"
    assert out["engine"] == "jev+rules"
    assert out["category"] == "immigration" and out["category_source"] == "jev"
    assert out["mode"] == "escalate"
    assert out["urgency"] == "time_sensitive"
    lod = next(r for r in out["requirements"] if r["key"] == "lodgement_date")
    assert lod["maybe_in_notes"] is True


def test_triage_falls_back_when_jev_errors(set_setting, monkeypatch):
    set_setting("openrouter_api_key", "sk-test")
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        jev.httpx, "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(lambda r: httpx.Response(502))))
    out = _run(triage.triage("Centrelink debt review", None, {}))
    assert out["engine"] == "rules"
    assert out["category"] == "services_australia"


def test_selected_category_wins_and_flags_force_urgent():
    out = _run(triage.triage("no food and homeless", "ndis", {}))
    assert out["category"] == "ndis" and out["category_source"] == "selected"
    assert out["urgency"] == "urgent"
    assert out["safety_flags"]
