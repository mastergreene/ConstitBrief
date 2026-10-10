from backend.app.services import rules


def test_extracts_identifiers_from_notes():
    notes = ("Caller ph 0412 345 678, email jo@example.com, CRN 123 456 789a, "
             "NDIS 431234567, TRN: EGO1234567 subclass 820, lives Coopers Plains QLD 4108, "
             "consent form signed")
    got = rules.extract_fields(notes)
    assert got["phone"] == "0412345678"
    assert got["email"] == "jo@example.com"
    assert got["crn"] == "123 456 789A"
    assert got["ndis_number"] == "431234567"
    assert got["dha_ref"] == "EGO1234567"
    assert got["visa_subclass"] == "820"
    assert got["postcode"] == "4108"
    assert got["consent_signed"] == "true"


def test_negated_consent_is_not_extracted():
    assert "consent_signed" not in rules.extract_fields("consent not yet signed")


def test_tfn_is_never_mistaken_for_crn_or_phone():
    got = rules.extract_fields("TFN 123 456 789 please help")
    assert "crn" not in got and "phone" not in got
    assert rules.contains_tfn("my tax file number is 123456789")
    assert "123" not in rules.redact_tfn("TFN: 123 456 789")


def test_redact_pii_removes_identifiers():
    red = rules.redact_pii("Call 0412 345 678 or a@b.com, CRN 123456789A, AC12345678, 01/02/1980")
    for leaked in ("0412", "a@b.com", "123456789A", "AC12345678", "1980"):
        assert leaked not in red


def test_classify_picks_obvious_category():
    assert rules.classify("Centrelink cancelled her JobSeeker payment")["category"] == "services_australia"
    assert rules.classify("partner visa waiting in ImmiAccount")["category"] == "immigration"
    assert rules.classify("NDIS plan reassessment cut supports")["category"] == "ndis"
    assert rules.classify("needs a home care package, My Aged Care")["category"] == "aged_care"
    assert rules.classify("school wants an Australian flag")["category"] == "flags_messages"
    assert rules.classify("noise from the neighbours")["category"] == "general"


def test_safety_flags():
    keys = {f["key"] for f in rules.safety_flags("She is homeless and has no food")}
    assert keys == {"homelessness", "financial_crisis"}
    assert rules.safety_flags("wants a flag for the school") == []


def test_requirements_conditional_on_subtype():
    reqs = rules.evaluate_requirements("ato_nbn_dva", {"sub_type": "DVA"})
    keys = {r["key"] for r in reqs}
    assert "dva_file_no" in keys and "ato_ref" not in keys and "nbn_ticket" not in keys


def test_requirements_met_logic():
    data = {"first_name": "Jo", "last_name": "Citizen", "email": "jo@example.com",
            "address_line1": "1 Main St", "suburb": "Sunnybank", "postcode": "4109",
            "desired_outcome": "info"}
    reqs = rules.evaluate_requirements("general", data)
    assert all(r["met"] for r in reqs)
    data["postcode"] = ""
    assert not next(r for r in rules.evaluate_requirements("general", data) if r["key"] == "address")["met"]


def test_every_category_requirement_references_real_fields():
    for keys in rules.CATEGORY_REQUIREMENTS.values():
        for k in keys:
            for f in rules.REQUIREMENTS[k].fields:
                assert f in rules.FIELD_BY_ID, f
