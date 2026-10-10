import json

import httpx

from backend.app.services import search


def test_meta_and_static(client):
    meta = client.get("/api/meta").json()
    assert {c["id"] for c in meta["categories"]} >= {"services_australia", "immigration", "general"}
    assert meta["jotform"]["params"]["first_name"] == "name[first]"
    assert client.get("/").status_code == 200
    sw = client.get("/sw.js")
    assert sw.status_code == 200 and sw.headers["cache-control"] == "no-cache"
    assert client.get("/manifest.webmanifest").headers["content-type"].startswith("application/manifest+json")


def test_seeded_templates_and_crud(client):
    items = client.get("/api/templates").json()
    slugs = {t["slug"] for t in items}
    assert {"mygov-link-centrelink", "ministerial-intervention-explainer",
            "flags-portraits-eligibility", "myagedcare-getting-started"} <= slugs
    assert all(t["needs_review"] for t in items)

    created = client.post("/api/templates", json={
        "title": "Test response", "category": "general", "tags": ["test"], "body": "Hello"}).json()
    assert created["slug"] == "test-response" and not created["needs_review"]
    patched = client.patch(f"/api/templates/{created['id']}", json={"sms": "Short"}).json()
    assert patched["sms"] == "Short" and patched["body"] == "Hello"
    assert client.delete(f"/api/templates/{created['id']}").status_code == 204
    assert client.get(f"/api/templates/{created['id']}").status_code == 404


def test_triage_endpoint(client):
    r = client.post("/api/triage", json={
        "notes": "Mum's Age Pension stopped, CRN 123 456 789A, wants a review",
        "data": {"first_name": "Jo", "unknown_field": "dropped"}})
    t = r.json()
    assert t["category"] == "services_australia"
    assert t["extracted"]["crn"] == "123 456 789A"
    assert any(s["slug"] == "centrelink-review-of-decision" for s in t["suggested_templates"])
    assert "123" not in t["search_query"]


def test_cases_roundtrip_redacts_tfn(client):
    body = {"client_id": "abc-123", "category": "general", "notes": "TFN 123 456 789",
            "data": {"first_name": "Jo", "evil": "x"}}
    saved = client.put("/api/cases", json=body).json()
    assert "123 456 789" not in saved["notes"]
    assert saved["data"] == {"first_name": "Jo"}
    assert saved["label"].startswith("Jo")
    body["status"] = "lodged"
    client.put("/api/cases", json=body)
    rows = [r for r in client.get("/api/cases").json() if r["client_id"] == "abc-123"]
    assert len(rows) == 1 and rows[0]["status"] == "lodged"
    assert client.delete("/api/cases/abc-123").status_code == 204


def test_access_token(client, set_setting):
    set_setting("access_token", "s3cret")
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/meta").status_code == 401
    assert client.get("/api/meta", headers={"X-Access-Token": "nope"}).status_code == 401
    assert client.get("/api/meta", headers={"X-Access-Token": "s3cret"}).status_code == 200
    assert client.get("/").status_code == 200  # shell stays public


def test_generate_ack(client):
    d = client.post("/api/generate", json={
        "kind": "acknowledgement", "category": "immigration",
        "data": {"first_name": "Jo", "visa_subclass": "820"}, "notes": ""}).json()
    assert d["email"].startswith("Hi Jo,")
    assert "Team Moreton" in d["email"] and "consent" in d["email"]
    assert "{FIRST_NAME}" not in d["email"] + d["sms"]
    assert d["engine"] == "template"


def test_search_filters_to_allowed_domains(client, set_setting, monkeypatch):
    set_setting("brave_api_key", "brave-test")
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["q"] = request.url.params["q"]
        return httpx.Response(200, json={"web": {"results": [
            {"title": "<strong>Carer</strong> Payment", "url": "https://www.servicesaustralia.gov.au/carer-payment",
             "description": "Call 132 717 for help"},
            {"title": "Spam", "url": "https://servicesaustralia.gov.au.evil.com/x", "description": ""},
            {"title": "Blog", "url": "https://example.com/carer", "description": ""},
        ]}})

    real = httpx.AsyncClient
    monkeypatch.setattr(search.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler)))
    r = client.post("/api/search", json={"q": "carer payment unique-q-1", "category": "services_australia"}).json()
    assert "site:servicesaustralia.gov.au" in captured["q"]
    assert [x["url"] for x in r["results"]] == ["https://www.servicesaustralia.gov.au/carer-payment"]
    assert r["results"][0]["title"] == "Carer Payment"
    assert r["results"][0]["phones"] == ["132 717"]
    again = client.post("/api/search", json={"q": "carer payment unique-q-1", "category": "services_australia"}).json()
    assert again["cached"] is True


def test_search_without_provider_returns_links(client):
    r = client.post("/api/search", json={"q": "aged care assessment", "category": "aged_care"}).json()
    assert r["provider"] is None
    assert r["links"][0]["domain"] == "myagedcare.gov.au"
    assert any(d.get("phone") == "1800 200 422" for d in r["directory"])
