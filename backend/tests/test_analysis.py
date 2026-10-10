"""Acceptance scenarios (brief section 10) at the analysis-engine level."""
from backend.app.services import analysis


def run(notes, state=None):
    return analysis.analyse(notes, state or {})


def test_sporting_club_grant_plus_invitation():
    r = run("President of a local sporting club called about funding for equipment and wants "
            "Julie-Ann at their presentation night on 14 November.")
    assert set(r["active_types"]) == {"grant", "event_invitation"}
    assert r["team"]["team"] == "community" and r["team"]["basis"] == "proposed"
    opts = {h["form_option"] for h in r["handoffs"]}
    assert opts == {"Grant Inquiries", "Invitation to an event"}
    keys = {q["key"] for q in r["questions"]}
    assert "form:4" in keys  # name is required by the form
    assert any(d["kind"] == "event" for d in r["dates"])
    assert any("multi" in a["key"] for a in r["actions"])


def test_ndis_incomplete():
    r = run("Caller's NDIS plan was cut at reassessment and she wants it reviewed.")
    assert r["active_types"] == ["ndis"] and r["team"]["team"] == "constituent"
    assert r["handoffs"][0]["mandatory_missing"] == ["Name", "Address"]
    assert not r["proposals"]  # nothing invented


def test_immigration_identifier_optional_and_consent_not_inferred():
    r = run("Partner visa lodged two years ago, she says she signed our consent form.")
    ck = {c["key"]: c for c in r["checklist"]}
    assert ck["immigration:dha_ref"]["basis"] == "suggestion"
    assert ck["immigration:dha_ref"]["status"] == "missing"
    assert "DHA reference" not in " ".join(r["handoffs"][0]["mandatory_missing"])
    assert ck["immigration:consent"]["status"] == "missing"  # never inferred from notes


def test_journalist_deadline():
    r = run("Journalist from the Courier-Mail wants comment on the hospital funding story, deadline 3pm today.")
    assert r["active_types"] == ["media"] and r["team"]["team"] == "comms"
    assert r["team"]["basis"] == "confirmed"
    dl = [d for d in r["dates"] if d["kind"] == "deadline"]
    assert dl and dl[0]["text"] == "3pm today"
    assert any(q["key"].startswith("deadline:") for q in r["questions"])


def test_general_admin():
    r = run("Wants to know the office opening hours.")
    assert r["active_types"] == ["admin"] and r["team"]["team"] == "administration"
    assert r["handoffs"][0]["form_option"] == "Help with another Issue"


def test_grant_keyword_alone_does_not_force_admin():
    r = run("Asking about a grant for the school library.")
    assert r["active_types"][0] == "grant" and r["team"]["team"] != "administration"


def test_parliamentary_and_ministerial_need_staff_ownership():
    r = run("Wants Julie-Ann to ask a question in parliament and write to the minister about it.")
    assert set(r["active_types"]) >= {"parliamentary", "ministerial"}
    assert r["team"]["team"] is None and r["team"]["basis"] == "staff"
    assert any("staff approval" in a["text"] for a in r["actions"])


def test_ambiguous_and_conflicting():
    r = run("Called about a problem. Gave 0412 345 678 then said 0498 765 432.")
    assert r["uncertain"] and any(q["key"] == "clarify:type" for q in r["questions"])
    assert r["contradictions"] and r["contradictions"][0]["field"] == "phone"
    assert not [p for p in r["proposals"] if p["field"] == "phone"]


def test_staff_values_authoritative_and_contradiction_raised():
    state = {"values": {"phone": "0499999999"}}
    r = run("Phone 0412 345 678", state)
    assert not r["proposals"]
    assert r["contradictions"][0]["message"] == "Notes say 0412345678 but the record has 0499999999"


def test_rejected_proposal_not_resuggested_and_dismissed_question_hidden():
    r = run("CRN 123 456 789A Centrelink", {"rejected": {"crn": ["123 456 789A"]},
                                          "dismissed_questions": ["form:4"]})
    assert not r["proposals"]
    assert "form:4" not in {q["key"] for q in r["questions"]}


def test_staff_types_override_suggestions():
    r = run("Centrelink pension stopped", {"types": {"selected": ["ministerial"]}})
    assert r["active_types"] == ["ministerial"] and r["types_source"] == "staff"


def test_not_applicable_respected():
    r = run("NDIS plan cut", {"not_applicable": ["ndis:consent"]})
    assert next(c for c in r["checklist"] if c["key"] == "ndis:consent")["status"] == "not_applicable"


def test_ready_when_mandatory_captured():
    vals = {"first_name": "Test", "last_name": "Synthetic", "address_line1": "1 Example St",
            "suburb": "Sunnybank", "state": "QLD"}
    r = run("NDIS plan cut", {"values": vals})
    assert r["ready"] and r["handoffs"][0]["mandatory_missing"] == []


def test_safety_flags_and_tfn_warning():
    r = run("She is homeless and gave her TFN 123 456 789")
    assert r["safety_flags"][0]["key"] == "homelessness" and r["tfn_warning"]


def test_fast():
    r = run("Centrelink " * 400)
    assert r["timing_ms"] < 200
