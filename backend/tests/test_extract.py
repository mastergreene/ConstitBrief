from datetime import date

from backend.app.services import extract


def test_identifier_proposals_have_evidence():
    notes = "Ph 0412 345 678, CRN 123 456 789a, NDIS 431234567, TRN: EGO1234567, subclass 820"
    got = {f["field"]: f for f in extract.facts(notes)}
    assert got["phone"]["value"] == "0412345678"
    assert got["crn"]["value"] == "123 456 789A"
    assert got["ndis_number"]["value"] == "431234567"
    assert got["dha_reference"]["value"] == "EGO1234567"
    assert got["visa_subclass"]["value"] == "820"
    ev = got["crn"]["evidence"]
    assert notes[ev["start"]:ev["end"]] == ev["text"] == "123 456 789a"


def test_never_extracts_names_or_consent():
    fields = {f["field"] for f in extract.facts("Sarah Smith said she signed the consent form")}
    assert fields == set()


def test_tfn_never_becomes_another_identifier():
    assert extract.facts("TFN 123 456 789") == []
    assert extract.contains_tfn("my tax file number is 123456789")
    assert "123" not in extract.redact_tfn("TFN: 123 456 789")


def test_dates_are_proposals_with_wording():
    today = date(2026, 10, 10)
    ds = extract.dates("Journalist deadline 3pm today. Presentation night on 14 November.", today)
    by = {d["text"]: d for d in ds}
    assert by["3pm today"]["kind"] == "deadline" and by["3pm today"]["iso"] is None
    assert by["3pm today"]["needs_confirmation"]
    assert by["14 November"]["kind"] == "event"
    assert by["14 November"]["iso"] == "2026-11-14" and by["14 November"]["needs_confirmation"]
    explicit = extract.dates("Applications close 30/11/2026", today)[0]
    assert explicit["kind"] == "deadline" and explicit["iso"] == "2026-11-30"
    assert not explicit["needs_confirmation"]


def test_redact_removes_identifiers_and_known_personal_values():
    red = extract.redact("Jo Citizen at 1 Example St, 0412 345 678, jo@example.com, CRN 123456789A",
                         {"first_name": "Jo", "last_name": "Citizen", "address_line1": "1 Example St"})
    for leaked in ("Jo", "Citizen", "Example", "0412", "jo@example.com", "123456789A"):
        assert leaked not in red


def test_outcome_proposal():
    p = extract.outcome_proposal("Payment stopped. She wants it reinstated and back paid.")
    assert p and "reinstated" in p["text"]
