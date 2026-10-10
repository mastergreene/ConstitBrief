"""Casework domain rules.

This module is the single source of truth for:
  * enquiry categories,
  * the intake form fields (rendered dynamically by the PWA via /api/meta),
  * which fields are mandatory before a matter can be escalated,
  * deterministic extraction of identifiers from free-text notes,
  * welfare / safety red flags.

Everything here is deterministic and works with no network access. The Jev
decision gate (services/jev.py) layers probabilistic judgement on top.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

# --------------------------------------------------------------------------- #
# Categories
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Category:
    id: str
    label: str
    short: str
    description: str  # also used as the Jev "choice" criterion
    domains: tuple[str, ...]
    keywords: tuple[str, ...]


CATEGORIES: tuple[Category, ...] = (
    Category(
        "services_australia",
        "Services Australia (Centrelink / Medicare)",
        "Centrelink",
        "Centrelink payments, debts, reviews, Medicare, Child Support or myGov linking.",
        ("servicesaustralia.gov.au", "my.gov.au"),
        (
            "centrelink", "medicare", "mygov", "my gov", "crn", "jobseeker", "pension",
            "age pension", "carer", "dsp", "disability support", "family tax", "ftb",
            "parenting payment", "youth allowance", "austudy", "rent assistance",
            "health care card", "concession card", "debt", "overpayment", "child support",
            "services australia", "payment suspended", "payment cancelled", "income test",
            "statutory declaration", "stat dec", "linking code",
        ),
    ),
    Category(
        "immigration",
        "Immigration & Visas",
        "Visas",
        "Visa applications, processing delays, bridging visas, citizenship, ministerial "
        "intervention or the Department of Home Affairs.",
        ("homeaffairs.gov.au",),
        (
            "visa", "immi", "immiaccount", "home affairs", "citizenship", "partner visa",
            "bridging", "subclass", "trn", "migration", "ministerial intervention",
            "deport", "removal", "detention", "sponsor", "parent visa", "protection visa",
            "skilled", "student visa", "visitor visa", "dha", "tribunal", "aat",
        ),
    ),
    Category(
        "ndis",
        "NDIS",
        "NDIS",
        "National Disability Insurance Scheme access, plans, reviews, reassessments, "
        "providers or plan management.",
        ("ndis.gov.au",),
        (
            "ndis", "plan review", "reassessment", "participant", "lac",
            "local area coordinator", "support coordinator", "plan manager", "access request",
            "ndia", "disability insurance", "sil", "sda", "core supports",
        ),
    ),
    Category(
        "aged_care",
        "MyAgedCare",
        "Aged care",
        "My Aged Care assessments, Support at Home / home care packages, residential "
        "aged care, aged care fees.",
        ("myagedcare.gov.au",),
        (
            "aged care", "my aged care", "myagedcare", "home care package", "hcp",
            "support at home", "acat", "aged care assessment", "residential care",
            "nursing home", "respite", "chsp", "aged care fees", "means test",
        ),
    ),
    Category(
        "ato_nbn_dva",
        "ATO / NBN / Veterans' Affairs",
        "ATO/NBN/DVA",
        "Tax and the ATO, superannuation, NBN or telecommunications connection problems, "
        "or Department of Veterans' Affairs claims.",
        ("ato.gov.au", "dva.gov.au"),
        (
            "ato", "tax", "tax return", "refund", "super", "superannuation", "abn", "gst",
            "nbn", "internet", "broadband", "phone line", "telstra", "optus",
            "dva", "veteran", "veterans", "gold card", "white card", "open arms", "adf",
            "defence", "military",
        ),
    ),
    Category(
        "flags_messages",
        "Constituent Flags & Congratulatory Messages",
        "Flags & msgs",
        "Requests for Australian, Aboriginal or Torres Strait Islander flags, portraits, or "
        "birthday and wedding anniversary congratulatory messages.",
        (),
        (
            "flag", "flags", "portrait", "birthday", "anniversary", "congratulat",
            "100th", "90th", "60th", "50th", "70th", "65th", "milestone", "message from the king",
            "governor-general", "centenarian",
        ),
    ),
    Category(
        "general",
        "General Inquiries",
        "General",
        "Anything else: local issues, state or council matters, policy views, events, or "
        "general information.",
        (),
        (),
    ),
)

CATEGORY_BY_ID = {c.id: c for c in CATEGORIES}
DEFAULT_CATEGORY = "general"

# --------------------------------------------------------------------------- #
# Intake form fields
# --------------------------------------------------------------------------- #

ALL = "*"


@dataclass(frozen=True)
class FormField:
    id: str
    label: str
    type: str = "text"  # text|tel|email|date|textarea|select|checkbox
    categories: tuple[str, ...] = (ALL,)
    placeholder: str = ""
    inputmode: str = ""
    autocomplete: str = ""
    options: tuple[str, ...] = ()
    group: str = "constituent"  # constituent|matter
    help: str = ""


FIELDS: tuple[FormField, ...] = (
    # --- Constituent ---
    FormField("first_name", "First name", autocomplete="given-name"),
    FormField("last_name", "Last name", autocomplete="family-name"),
    FormField("phone", "Mobile / phone", "tel", inputmode="tel", autocomplete="tel",
              placeholder="04xx xxx xxx"),
    FormField("email", "Email", "email", inputmode="email", autocomplete="email"),
    FormField("address_line1", "Street address", autocomplete="address-line1"),
    FormField("suburb", "Suburb", autocomplete="address-level2"),
    FormField("state", "State", "select",
              options=("QLD", "NSW", "VIC", "ACT", "TAS", "SA", "WA", "NT")),
    FormField("postcode", "Postcode", inputmode="numeric", autocomplete="postal-code",
              placeholder="41xx"),
    FormField("dob", "Date of birth", "date",
              categories=("services_australia", "immigration", "ndis", "aged_care",
                          "ato_nbn_dva")),
    # --- Matter: common ---
    FormField("consent_signed", "Signed privacy consent / authority received", "checkbox",
              group="matter",
              categories=("services_australia", "immigration", "ndis", "aged_care",
                          "ato_nbn_dva", "general"),
              help="Agencies will not discuss a constituent's matter without written consent."),
    FormField("agency_contacted", "Constituent has already tried the agency directly",
              "checkbox", group="matter",
              categories=("services_australia", "immigration", "ndis", "aged_care",
                          "ato_nbn_dva")),
    FormField("agency_ref", "Agency complaint / feedback reference", group="matter",
              categories=("services_australia", "immigration", "ndis", "aged_care",
                          "ato_nbn_dva")),
    FormField("desired_outcome", "What outcome are they seeking?", "textarea",
              group="matter",
              categories=("services_australia", "immigration", "ndis", "aged_care",
                          "ato_nbn_dva", "general")),
    # --- Services Australia ---
    FormField("crn", "Centrelink CRN", categories=("services_australia",),
              placeholder="123 456 789A", group="matter"),
    FormField("payment_type", "Payment / service involved", categories=("services_australia",),
              placeholder="e.g. Age Pension, JobSeeker, Medicare", group="matter"),
    FormField("decision_date", "Date of decision / letter", "date",
              categories=("services_australia", "ndis"), group="matter"),
    # --- Immigration ---
    FormField("dha_ref", "DHA Client ID / TRN / Application ID", categories=("immigration",),
              group="matter", help="Any one of these lets the office locate the file."),
    FormField("visa_subclass", "Visa subclass", categories=("immigration",),
              inputmode="numeric", placeholder="e.g. 820", group="matter"),
    FormField("lodgement_date", "Lodgement date", "date", categories=("immigration",),
              group="matter"),
    FormField("all_applicants_consent", "Consent covers every applicant on the application",
              "checkbox", categories=("immigration",), group="matter",
              help="Each adult applicant generally needs to sign their own consent."),
    # --- NDIS ---
    FormField("ndis_number", "NDIS number", categories=("ndis",), inputmode="numeric",
              placeholder="43xxxxxxx", group="matter"),
    FormField("ndis_issue", "NDIS issue type", "select", categories=("ndis",), group="matter",
              options=("Access request", "Plan reassessment / variation", "Review of decision",
                       "Provider or payment issue", "Other")),
    # --- Aged care ---
    FormField("aged_care_id", "My Aged Care ID", categories=("aged_care",), group="matter",
              placeholder="AC12345678"),
    FormField("assessment_status", "Assessment / service status", "select",
              categories=("aged_care",), group="matter",
              options=("Not yet registered", "Awaiting assessment", "Assessed - awaiting services",
                       "Receiving services", "Residential care", "Other")),
    FormField("representative", "Authorised representative (if any)", categories=("aged_care",),
              group="matter"),
    # --- ATO / NBN / DVA ---
    FormField("sub_type", "Agency", "select", categories=("ato_nbn_dva",), group="matter",
              options=("ATO", "NBN / telco", "DVA")),
    FormField("ato_ref", "ATO case / reference number (never a TFN)", categories=("ato_nbn_dva",),
              group="matter", help="Do not record Tax File Numbers anywhere."),
    FormField("nbn_rsp", "Internet provider (RSP)", categories=("ato_nbn_dva",), group="matter"),
    FormField("nbn_ticket", "Provider fault / ticket number", categories=("ato_nbn_dva",),
              group="matter"),
    FormField("dva_file_no", "DVA file number", categories=("ato_nbn_dva",), group="matter"),
    # --- Flags & messages ---
    FormField("request_type", "Request", "select", categories=("flags_messages",), group="matter",
              options=("Australian National Flag", "Aboriginal Flag", "Torres Strait Islander Flag",
                       "Portrait", "Birthday message", "Wedding anniversary message",
                       "Other congratulatory message")),
    FormField("organisation", "Organisation (if for a group / school)",
              categories=("flags_messages",), group="matter"),
    FormField("recipient_name", "Recipient name(s)", categories=("flags_messages",),
              group="matter"),
    FormField("milestone_date", "Milestone date", "date", categories=("flags_messages",),
              group="matter"),
)

FIELD_BY_ID = {f.id: f for f in FIELDS}


def fields_for(category: str) -> list[FormField]:
    return [f for f in FIELDS if ALL in f.categories or category in f.categories]


# --------------------------------------------------------------------------- #
# Mandatory-field requirements ("Ask Them Now")
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Requirement:
    key: str
    label: str
    ask: str  # what the caseworker says to the constituent
    fields: tuple[str, ...]
    mode: str = "any"  # any|all
    # Only applies when every listed field equals one of the values.
    when: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # Plain-English question for Jev: do the notes already cover this?
    notes_question: str = ""
    priority: int = 2  # 1 = cannot lodge without it


R = Requirement
REQUIREMENTS: dict[str, Requirement] = {
    r.key: r
    for r in (
        R("name", "Full name", "Can I confirm your first and last name?",
          ("first_name", "last_name"), "all", priority=1),
        R("contact", "Phone or email", "What's the best number or email to reach you on?",
          ("phone", "email"), priority=1),
        R("address", "Residential address",
          "And your home address, including suburb and postcode? (Confirms you're in Moreton.)",
          ("address_line1", "suburb", "postcode"), "all", priority=1),
        R("dob", "Date of birth", "What's your date of birth? The agency uses it to verify you.",
          ("dob",), priority=1),
        R("consent", "Signed privacy consent",
          "We'll need your written consent before the agency can talk to us — "
          "can you sign the form today? I can text or email it now.",
          ("consent_signed",), priority=1,
          notes_question="The notes say the constituent has signed or returned a privacy "
                         "consent or authority form."),
        R("tried_agency", "Agency contacted first",
          "Have you already raised this with the agency yourself? Any reference number?",
          ("agency_contacted", "agency_ref"),
          notes_question="The notes say the constituent has already contacted the agency "
                         "about this matter."),
        R("outcome", "Desired outcome", "What would a good outcome look like for you?",
          ("desired_outcome",), priority=1,
          notes_question="The notes clearly state what outcome the constituent wants."),
        # Services Australia
        R("crn", "Centrelink CRN",
          "Can you read me your Customer Reference Number? It's on any Centrelink letter — "
          "9 digits and a letter.", ("crn",), priority=1),
        R("payment", "Payment / service involved",
          "Which payment or service is this about?", ("payment_type",),
          notes_question="The notes name the specific Centrelink payment or Medicare service "
                         "involved."),
        R("decision_date", "Decision / letter date",
          "When did you get the decision or letter? (Review time limits can apply.)",
          ("decision_date",),
          notes_question="The notes give the date of the agency decision or letter."),
        # Immigration
        R("dha_ref", "DHA Client ID / TRN",
          "Can you find your Transaction Reference Number (TRN) or Client ID? It's in "
          "ImmiAccount or on the acknowledgement email.", ("dha_ref",), priority=1),
        R("visa_subclass", "Visa subclass", "Which visa did you apply for — do you know the "
          "subclass number?", ("visa_subclass",), priority=1),
        R("lodgement_date", "Lodgement date", "When was the application lodged?",
          ("lodgement_date",),
          notes_question="The notes state when the visa application was lodged."),
        R("all_consent", "Consent from all applicants",
          "Is anyone else on the application? Each adult will need to sign consent too.",
          ("all_applicants_consent",)),
        # NDIS
        R("ndis_number", "NDIS number", "What's the participant's NDIS number? It starts "
          "with 43.", ("ndis_number",), priority=1),
        R("ndis_issue", "NDIS issue type", "Is this about access, a plan change, or a review "
          "of a decision?", ("ndis_issue",)),
        # Aged care
        R("aged_care_id", "My Aged Care ID", "Do you have the My Aged Care ID? It's on letters "
          "from My Aged Care and starts with AC.", ("aged_care_id",), priority=1),
        R("assessment_status", "Assessment status", "Where are things up to — waiting for an "
          "assessment, or assessed and waiting for services?", ("assessment_status",)),
        # ATO / NBN / DVA
        R("sub_type", "Which agency", "Is this about tax, the NBN, or Veterans' Affairs?",
          ("sub_type",), priority=1),
        R("ato_ref", "ATO reference (no TFN)",
          "Do you have an ATO case or reference number? Please don't give me your TFN.",
          ("ato_ref",), when={"sub_type": ("ATO",)}),
        R("nbn_ticket", "Provider + fault ticket",
          "Who's your internet provider, and what's the fault ticket number they gave you?",
          ("nbn_rsp", "nbn_ticket"), "all", when={"sub_type": ("NBN / telco",)}),
        R("dva_file_no", "DVA file number", "What's your DVA file number?", ("dva_file_no",),
          when={"sub_type": ("DVA",)}, priority=1),
        # Flags & messages
        R("request_type", "What they're requesting", "What would you like — a flag, a portrait "
          "or a congratulatory message?", ("request_type",), priority=1),
        R("recipient", "Recipient / organisation",
          "Who is it for? (Organisation name, or the person celebrating.)",
          ("recipient_name", "organisation"), priority=1),
        R("milestone_date", "Milestone date",
          "What's the date of the birthday or anniversary? Messages need lead time.",
          ("milestone_date",), when={"request_type": ("Birthday message",
                                                      "Wedding anniversary message",
                                                      "Other congratulatory message")},
          priority=1),
    )
}

CATEGORY_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "services_australia": ("name", "contact", "address", "dob", "consent", "crn", "payment",
                           "decision_date", "tried_agency", "outcome"),
    "immigration": ("name", "contact", "address", "dob", "consent", "dha_ref", "visa_subclass",
                    "lodgement_date", "all_consent", "tried_agency", "outcome"),
    "ndis": ("name", "contact", "address", "dob", "consent", "ndis_number", "ndis_issue",
             "tried_agency", "outcome"),
    "aged_care": ("name", "contact", "address", "dob", "consent", "aged_care_id",
                  "assessment_status", "tried_agency", "outcome"),
    "ato_nbn_dva": ("name", "contact", "address", "sub_type", "ato_ref", "nbn_ticket",
                    "dva_file_no", "consent", "tried_agency", "outcome"),
    "flags_messages": ("name", "contact", "address", "request_type", "recipient",
                       "milestone_date"),
    "general": ("name", "contact", "address", "outcome"),
}


def _filled(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return bool(str(value).strip())


def requirement_applies(req: Requirement, data: dict[str, Any]) -> bool:
    for fid, allowed in req.when.items():
        if str(data.get(fid) or "") not in allowed:
            return False
    return True


def requirement_met(req: Requirement, data: dict[str, Any]) -> bool:
    checks = [_filled(data.get(f)) for f in req.fields]
    return all(checks) if req.mode == "all" else any(checks)


def evaluate_requirements(category: str, data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return every applicable requirement for the category with a met/missing status."""
    out = []
    for key in CATEGORY_REQUIREMENTS.get(category, CATEGORY_REQUIREMENTS[DEFAULT_CATEGORY]):
        req = REQUIREMENTS[key]
        if not requirement_applies(req, data):
            continue
        out.append(
            {
                "key": req.key,
                "label": req.label,
                "ask": req.ask,
                "fields": list(req.fields),
                "priority": req.priority,
                "met": requirement_met(req, data),
                "maybe_in_notes": False,
            }
        )
    return out


# --------------------------------------------------------------------------- #
# Extraction from free-text notes
# --------------------------------------------------------------------------- #

_PHONE = re.compile(r"(?<![\d])(?:\+?61[ -]?|0)([2-478])(?:[ -]?\d){8}(?!\d)")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_CRN = re.compile(r"\b(\d{3})[ -]?(\d{3})[ -]?(\d{3})[ -]?([A-Za-z])\b")
_NDIS = re.compile(r"\b(43\d{7})\b")
_AGED_CARE_ID = re.compile(r"\b(AC\d{8})\b", re.I)
_TRN = re.compile(r"\b(?:TRN|transaction reference(?: number)?)[:#\s-]*([A-Z0-9]{8,14})\b", re.I)
_CLIENT_ID = re.compile(r"\b(?:client id|hap id|application id)[:#\s-]*([A-Z0-9]{6,14})\b", re.I)
_SUBCLASS = re.compile(r"\b(?:subclass|sc|visa)\s*#?\s*(\d{3})\b", re.I)
_DVA_FILE = re.compile(r"\b(?:dva(?: file)?(?: no\.?| number)?)[:#\s-]*([A-Z]{1,4}\d{4,7}[A-Z]?)\b",
                       re.I)
_POSTCODE = re.compile(r"\b(?:QLD|Qld|Queensland)\s*,?\s*(4\d{3})\b")
_TFN = re.compile(r"\b(?:TFN|tax file(?: number)?)(?:\s+(?:is|was|=))?[:#\s-]*(\d{3}[ -]?\d{3}[ -]?\d{2,3})\b",
                  re.I)
_CONSENT_YES = re.compile(r"\b(consent|authority)\b[^.\n]{0,40}\b(signed|received|returned|on file)\b",
                          re.I)

# Australian phone numbers as they appear on government pages (13 xx xx, 1300, 1800, landlines).
GOV_PHONE = re.compile(
    r"(?<![\d])(1[38]00[ ]?\d{3}[ ]?\d{3}|13\d[ ]?\d{3}|13[ ]?\d{2}[ ]?\d{2}|"
    r"\(0[2378]\)[ ]?\d{4}[ ]?\d{4}|0[2378][ ]?\d{4}[ ]?\d{4})(?!\d)"
)


def extract_fields(notes: str) -> dict[str, str]:
    """Pull identifiers out of notes so the caseworker doesn't have to retype them."""
    found: dict[str, str] = {}
    if not notes:
        return found
    text = _TFN.sub(" ", notes)  # never treat a TFN as anything else
    if m := _EMAIL.search(text):
        found["email"] = m.group(0)
    if m := _PHONE.search(text):
        found["phone"] = re.sub(r"[ -]", "", m.group(0))
    if m := _CRN.search(text):
        found["crn"] = f"{m.group(1)} {m.group(2)} {m.group(3)}{m.group(4).upper()}"
    if m := _NDIS.search(text):
        found["ndis_number"] = m.group(1)
    if m := _AGED_CARE_ID.search(text):
        found["aged_care_id"] = m.group(1).upper()
    if m := (_TRN.search(text) or _CLIENT_ID.search(text)):
        found["dha_ref"] = m.group(1).upper()
    if m := _SUBCLASS.search(text):
        found["visa_subclass"] = m.group(1)
    if m := _DVA_FILE.search(text):
        found["dva_file_no"] = m.group(1).upper()
    if m := _POSTCODE.search(text):
        found["postcode"] = m.group(1)
    if _CONSENT_YES.search(text) and not re.search(r"\b(not|no|hasn't|hasnt|yet to)\b[^.\n]{0,20}"
                                                   r"\b(signed|consent)", text, re.I):
        found["consent_signed"] = "true"
    return found


def contains_tfn(text: str) -> bool:
    return bool(_TFN.search(text or ""))


def redact_tfn(text: str) -> str:
    return _TFN.sub("[TFN REMOVED - do not record TFNs]", text or "")


PERSONAL_FIELDS = ("first_name", "last_name", "address_line1", "suburb", "email", "phone",
                   "recipient_name", "organisation", "representative")


def redact_pii(text: str, data: dict[str, Any] | None = None) -> str:
    """Strip direct identifiers before text leaves the server for a third-party model.

    Pattern-based identifiers are always removed. Values the caseworker has typed into
    personal fields (name, street, suburb...) are also removed wherever they appear in the
    notes. Names that appear *only* in the notes cannot be reliably detected.
    """
    if not text:
        return ""
    for fid in PERSONAL_FIELDS:
        value = str((data or {}).get(fid) or "").strip()
        if len(value) >= 2:
            text = re.sub(r"(?<!\w)" + re.escape(value) + r"(?!\w)", f"[{fid.upper()}]", text,
                          flags=re.I)
    text = _TFN.sub("[TFN]", text)
    text = _EMAIL.sub("[EMAIL]", text)
    text = _CRN.sub("[CRN]", text)
    text = _NDIS.sub("[NDIS_NO]", text)
    text = _AGED_CARE_ID.sub("[MAC_ID]", text)
    text = _TRN.sub("TRN [REF]", text)
    text = _CLIENT_ID.sub("client id [REF]", text)
    text = _DVA_FILE.sub("DVA file [REF]", text)
    text = _PHONE.sub("[PHONE]", text)
    text = re.sub(r"\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b", "[DATE]", text)
    return text


# --------------------------------------------------------------------------- #
# Heuristic classification & escalation signals
# --------------------------------------------------------------------------- #

ESCALATION_SIGNALS = (
    "review", "appeal", "delay", "delayed", "waiting", "months", "refused", "rejected",
    "cancelled", "suspended", "debt", "overpayment", "ministerial", "intervention",
    "complaint", "complain", "no response", "not responded", "escalate", "urgent",
    "hardship", "stuck", "lost", "overdue", "unfair", "wrong decision", "cut off",
)

RESOLVE_SIGNALS = (
    "how do i", "how to", "where do i", "what is", "am i eligible", "eligibility",
    "phone number", "contact", "form", "link", "linking", "apply for", "information",
)


def classify(notes: str) -> dict[str, Any]:
    text = (notes or "").lower()
    scores: dict[str, float] = {}
    for cat in CATEGORIES:
        score = 0.0
        for kw in cat.keywords:
            if re.search(r"(?<![a-z])" + re.escape(kw) + r"(?![a-z])", text):
                score += 1.0 + 0.25 * kw.count(" ")
        scores[cat.id] = score
    best = max(scores, key=scores.get) if any(scores.values()) else DEFAULT_CATEGORY
    total = sum(scores.values())
    confidence = scores[best] / total if total else 0.0
    return {"category": best, "confidence": round(confidence, 2), "scores": scores}


def escalation_score(notes: str) -> float:
    text = (notes or "").lower()
    esc = sum(1 for s in ESCALATION_SIGNALS if s in text)
    res = sum(1 for s in RESOLVE_SIGNALS if s in text)
    if esc == 0 and res == 0:
        return 0.5
    return round(esc / (esc + res), 2)


# --------------------------------------------------------------------------- #
# Welfare / safety red flags
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SafetyFlag:
    key: str
    label: str
    patterns: tuple[str, ...]
    referrals: tuple[tuple[str, str], ...]


SAFETY_FLAGS: tuple[SafetyFlag, ...] = (
    SafetyFlag(
        "self_harm", "Possible risk of self-harm",
        (r"suicid", r"kill (?:myself|himself|herself|themselves)", r"end (?:it|my life)",
         r"self[- ]harm", r"don'?t want to (?:live|be here)", r"no reason to live"),
        (("Emergency", "000"), ("Lifeline", "13 11 14"), ("Suicide Call Back Service", "1300 659 467"),
         ("MensLine", "1300 78 99 78")),
    ),
    SafetyFlag(
        "family_violence", "Possible domestic / family violence",
        (r"domestic violence", r"\bdv\b", r"family violence", r"abusive", r"hits? me",
         r"threaten", r"unsafe at home", r"afraid of (?:him|her|them|my partner)"),
        (("Emergency", "000"), ("DVConnect Womensline (Qld)", "1800 811 811"),
         ("1800RESPECT", "1800 737 732"), ("DVConnect Mensline (Qld)", "1800 600 636")),
    ),
    SafetyFlag(
        "homelessness", "Homeless or at risk",
        (r"homeless", r"sleeping (?:in (?:my|the|a) car|rough)", r"evict", r"nowhere to (?:live|stay|go)",
         r"couch ?surf"),
        (("Qld Homeless Hotline", "1800 474 753"), ("Ask Izzy", "askizzy.org.au"),
         ("Salvation Army", "13 72 58")),
    ),
    SafetyFlag(
        "financial_crisis", "No money / food",
        (r"no money", r"no food", r"can'?t (?:afford|pay) (?:food|rent|bills)", r"\bhungry\b",
         r"payment (?:stopped|cut off|suspended)", r"disconnect"),
        (("Centrelink crisis / urgent payments", "132 850"),
         ("National Debt Helpline", "1800 007 007"), ("Ask Izzy", "askizzy.org.au")),
    ),
    SafetyFlag(
        "removal", "Imminent visa expiry / removal / detention",
        (r"deport", r"removal", r"detention", r"visa (?:expires|expiring|has expired)",
         r"bridging visa (?:expires|expiring|ending)", r"unlawful"),
        (("Home Affairs Global Service Centre", "131 881"),
         ("Legal Aid Queensland", "1300 65 11 88")),
    ),
)


def safety_flags(notes: str) -> list[dict[str, Any]]:
    text = (notes or "").lower()
    out = []
    for flag in SAFETY_FLAGS:
        if any(re.search(p, text) for p in flag.patterns):
            out.append(
                {
                    "key": flag.key,
                    "label": flag.label,
                    "referrals": [{"name": n, "contact": c} for n, c in flag.referrals],
                }
            )
    return out


# --------------------------------------------------------------------------- #
# Metadata for the frontend
# --------------------------------------------------------------------------- #


def meta() -> dict[str, Any]:
    return {
        "categories": [
            {"id": c.id, "label": c.label, "short": c.short, "domains": list(c.domains)}
            for c in CATEGORIES
        ],
        "fields": [
            {**asdict(f), "categories": list(f.categories), "options": list(f.options)}
            for f in FIELDS
        ],
        "requirements": {
            k: {
                "key": r.key,
                "label": r.label,
                "ask": r.ask,
                "fields": list(r.fields),
                "mode": r.mode,
                "when": {fk: list(v) for fk, v in r.when.items()},
                "priority": r.priority,
            }
            for k, r in REQUIREMENTS.items()
        },
        "category_requirements": {k: list(v) for k, v in CATEGORY_REQUIREMENTS.items()},
    }
