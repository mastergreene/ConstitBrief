import asyncio
import json

import httpx

from backend.app.services import drafts, search


def test_search_filters_to_allowed_domains(client, set_setting, monkeypatch):
    set_setting("brave_api_key", "brave-test")
    captured = {}

    def handler(request):
        captured["q"] = request.url.params["q"]
        return httpx.Response(200, json={"web": {"results": [
            {"title": "<strong>Carer</strong> Payment", "url": "https://www.servicesaustralia.gov.au/carer-payment",
             "description": "Call 132 717"},
            {"title": "Spoof", "url": "https://servicesaustralia.gov.au.evil.example/x", "description": ""},
            {"title": "Blog", "url": "https://example.com/carer", "description": ""}]}})

    real = httpx.AsyncClient
    monkeypatch.setattr(search.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler)))
    r = client.post("/api/search", json={"q": "carer payment q1", "type_id": "services_australia"}).json()
    assert "site:servicesaustralia.gov.au" in captured["q"]
    assert [x["url"] for x in r["results"]] == ["https://www.servicesaustralia.gov.au/carer-payment"]
    assert r["results"][0]["title"] == "Carer Payment" and r["results"][0]["phones"] == ["132 717"]
    assert client.post("/api/search", json={"q": "carer payment q1", "type_id": "services_australia"}).json()["cached"]


def test_search_without_provider_gives_links(client):
    r = client.post("/api/search", json={"q": "aged care assessment", "type_id": "aged_care"}).json()
    assert r["provider"] is None and r["links"][0]["domain"] == "myagedcare.gov.au"


def test_polish_never_sees_names(set_setting, monkeypatch):
    set_setting("openrouter_api_key", "sk-test")
    set_setting("generate_model", "some/model")
    sent = {}

    def handler(request):
        body = json.loads(request.content)
        sent["text"] = json.dumps(body)
        draft = json.loads(body["messages"][1]["content"].split("Draft to polish:\n", 1)[1])
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(draft)}}]})

    real = httpx.AsyncClient
    monkeypatch.setattr(drafts.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler)))
    out = asyncio.run(drafts.generate("ndis", {"first_name": "Bronwyn"}, "Bronwyn on 0412 345 678", []))
    assert out["engine"] == "model" and out["email"].startswith("Hi Bronwyn,")
    assert "Bronwyn" not in sent["text"] and "0412" not in sent["text"]
