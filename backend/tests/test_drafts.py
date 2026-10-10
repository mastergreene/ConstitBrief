import asyncio
import json

import httpx

from backend.app.services import drafts


def test_polish_never_sees_names_and_name_is_restored(set_setting, monkeypatch):
    set_setting("openrouter_api_key", "sk-test")
    set_setting("generate_model", "some/model")
    sent = {}

    def handler(request):
        body = json.loads(request.content)
        sent["text"] = json.dumps(body)
        draft = json.loads(body["messages"][1]["content"].split("Draft to polish:\n", 1)[1])
        draft["email"] = draft["email"].replace("Thanks so much", "Thank you heaps")
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(draft)}}]})

    real = httpx.AsyncClient
    monkeypatch.setattr(drafts.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler)))
    out = asyncio.run(drafts.generate("acknowledgement", "ndis",
                                      {"first_name": "Bronwyn", "last_name": "Smith"},
                                      "Bronwyn on 0412 345 678", []))
    assert out["engine"] == "model"
    assert "Bronwyn" not in sent["text"] and "0412" not in sent["text"]
    assert out["email"].startswith("Hi Bronwyn,") and "Thank you heaps" in out["email"]


def test_polish_rejected_if_signoff_dropped(set_setting, monkeypatch):
    set_setting("openrouter_api_key", "sk-test")
    set_setting("generate_model", "some/model")
    bad = {"subject": "x", "email": "Hi {FIRST_NAME}, bye", "sms": "x"}
    real = httpx.AsyncClient
    monkeypatch.setattr(drafts.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(bad)}}]}))))
    out = asyncio.run(drafts.generate("acknowledgement", "general", {"first_name": "Al"}, "", []))
    assert out["engine"] == "template" and "Team Moreton" in out["email"]


def test_resolution_includes_template_and_safety():
    t = [{"title": "Linking", "body": "Step 1", "sms": "Link it."}]
    out = asyncio.run(drafts.generate("resolution", "services_australia", {}, "she is homeless", t, False))
    assert "Step 1" in out["email"] and "1800 474 753" in out["email"]
    assert out["sms"].startswith("Hi there, thanks for calling. Link it.")
