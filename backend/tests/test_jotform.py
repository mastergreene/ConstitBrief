import json
import shutil
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from backend.app.services import jotform

DATA = {
    "first_name": "Jo", "last_name": "O'Brien", "phone": "0412345678", "email": "jo@example.com",
    "address_line1": "12 Smith St", "suburb": "Sunnybank", "postcode": "4109", "crn": "123 456 789A",
    "dob": "1950-03-04", "consent_signed": True, "payment_type": "Age Pension (100%)",
}


def test_prefill_parameters():
    out = jotform.build_url("services_australia", DATA, "Payment stopped. TFN 123 456 789")
    qs = {k: v[0] for k, v in parse_qs(urlparse(out["url"]).query).items()}
    assert out["url"].startswith("https://form.jotform.com/252413844700855?")
    assert qs["name[first]"] == "Jo" and qs["name[last]"] == "O'Brien"
    assert qs["phoneNumber120"] == "0412345678"
    assert qs["email"] == "jo@example.com"
    assert qs["address132[addr_line1]"] == "12 Smith St"
    assert qs["address132[city]"] == "Sunnybank"
    assert qs["address132[state]"] == "QLD"
    assert qs["address132[postal]"] == "4109"
    assert qs["crn"] == "123 456 789A"
    assert qs["typeA"] == "Services Australia (Centrelink / Medicare)"
    info = qs["moreInformation"]
    assert "Date of birth: 04/03/1950" in info
    assert "Signed privacy consent / authority received: Yes" in info
    assert "123 456 789" not in info  # TFN removed
    assert not out["truncated"]


def test_typea_override(set_setting):
    set_setting("jotform_typea_map", {"services_australia": "Centrelink"})
    out = jotform.build_url("services_australia", DATA)
    assert parse_qs(urlparse(out["url"]).query)["typeA"] == ["Centrelink"]


def test_long_notes_are_truncated_to_fit():
    out = jotform.build_url("general", DATA, "x" * 20000)
    assert out["truncated"]
    assert len(out["url"]) <= jotform.MAX_URL_LENGTH
    assert "notes truncated" in parse_qs(urlparse(out["url"]).query)["moreInformation"][0]


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_js_builder_matches_python(client, tmp_path):
    """The offline JS builder must produce the same URL as the server."""
    meta = client.get("/api/meta").json()
    notes = "Payment stopped (again)! Caller's TFN 123 456 789 * & = ?"
    expected = jotform.build_url("services_australia", DATA, notes, "urgent")["url"]
    js = Path(__file__).resolve().parents[2] / "frontend" / "js" / "jotform.js"
    script = tmp_path / "run.mjs"
    script.write_text(
        f"import {{ buildJotformUrl }} from {json.dumps(js.as_uri())};\n"
        f"const meta = {json.dumps(meta)};\n"
        f"process.stdout.write(buildJotformUrl(meta, 'services_australia', {json.dumps(DATA)}, "
        f"{json.dumps(notes)}, 'urgent').url);\n"
    )
    got = subprocess.run(["node", str(script)], capture_output=True, text=True, check=True).stdout
    assert got == expected
