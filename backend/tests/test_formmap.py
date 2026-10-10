"""The verified Jotform mapping: consistency with the live-form snapshot and URL safety."""
from urllib.parse import parse_qs, urlparse

import pytest

from backend.app.services import formmap, taxonomy

CONTACT = {"first_name": "Test", "last_name": "Synthetic", "phone": "0400000000",
           "email": "test@example.invalid", "address_line1": "1 Example St", "suburb": "Sunnybank",
           "state": "QLD", "postcode": "4109"}


def test_mapping_consistent_with_snapshot():
    assert formmap.check_consistency() == []


def test_every_form_option_has_a_branch_and_vice_versa():
    assert set(formmap.form_options()) == set(formmap.mapping()["branches"])


def test_required_fields_match_public_form():
    # Verified from the public form: name (first+last) and address (line1, city, state).
    req = {r["qid"]: set(r["fields"]) for r in formmap.required_record_fields("Help with an NDIS issue")}
    assert req == {"4": {"first_name", "last_name"}, "132": {"address_line1", "suburb", "state"}}
    congrats = {r["qid"] for r in formmap.required_record_fields("Request a Congratulations Message")}
    assert congrats == {"4", "132", "73"}  # recipient address only required in that branch


def test_build_rows_and_validation():
    out = formmap.build("Help with a Services Australia issue", {**CONTACT, "crn": "123 456 789A"},
                        {"issue": "Payment stopped", "outcome": "Payment restored"}, "CB-TEST01-1")
    assert out["valid"] and not out["errors"]
    by = {(r["qid"], r["sub"]): r for r in out["rows"]}
    assert by[("9", None)]["value"] == "Help with a Services Australia issue"
    assert by[("4", "first")]["value"] == "Test"
    assert by[("11", None)]["value"] == "123 456 789A"
    desc = by[("22", None)]["value"]
    assert "Payment stopped" in desc and "Requested outcome: Payment restored" in desc
    assert desc.endswith("ConstitBrief ref: CB-TEST01-1")


def test_missing_required_blocks():
    out = formmap.build("Grant Inquiries", {"first_name": "Test"}, {}, "CB-X-1")
    assert not out["valid"]
    assert "Name: Last name is required by the form" in out["errors"]
    assert any("Street address" in e for e in out["errors"])


def test_invalid_email_rejected():
    out = formmap.build("Grant Inquiries", {**CONTACT, "email": "not-an-email"}, {}, "CB-X-1")
    assert any("Email" in e for e in out["errors"])


def test_dates_split_for_jotform_and_unmapped_details_go_to_description():
    out = formmap.build("Request a Donation/Sponsorship",
                        {**CONTACT, "required_by_date": "2026-11-14", "organisation": "Example FC"},
                        {}, "CB-X-1")
    row = next(r for r in out["rows"] if r["qid"] == "89")
    assert row["parts"] == {"month": "11", "day": "14", "year": "2026"}
    desc = next(r for r in out["rows"] if r["qid"] == "87")["value"]
    assert "- Organisation: Example FC" in desc


def test_invitation_has_no_free_text_field_so_details_are_flagged():
    out = formmap.build("Invitation to an event", {**CONTACT, "event_name": "Presentation night"},
                        {"issue": "Club presentation night"}, "CB-X-1")
    assert out["description"] == ""
    assert ("Event name", "Presentation night") in out["unplaced_details"]
    assert any("no free-text field" in w for w in out["warnings"])


def test_invalid_choice_value_never_sent():
    out = formmap.build("Invitation to an event", {**CONTACT, "speaking_requested": "Maybe"}, {}, "x")
    assert next(r for r in out["rows"] if r["qid"] == "99")["value"] == ""


def test_unknown_option_refused():
    with pytest.raises(formmap.MappingError):
        formmap.build("Party Member Inquiry", CONTACT, {}, "x")  # condition exists, option doesn't


@pytest.mark.parametrize("contact", [False, True])
def test_url_never_carries_notes_or_identifiers(set_setting, contact):
    set_setting("jotform_prefill_contact", contact)
    values = {**CONTACT, "crn": "123 456 789A", "ndis_number": "431234567", "dob": "1950-01-01"}
    url = formmap.safe_url("Help with a Services Australia issue", values)
    qs = parse_qs(urlparse(url).query)
    assert qs["typeA"] == ["Help with a Services Australia issue"]
    flat = url + str(qs)
    for secret in ("123 456 789A", "123+456", "431234567", "1950", "moreInformation", "crn"):
        assert secret not in flat
    assert ("Synthetic" in str(qs)) is contact


def test_taxonomy_types_use_real_options():
    opts = set(formmap.form_options())
    for t in taxonomy.ENQUIRY_TYPES:
        assert t.form_option is None or t.form_option in opts
