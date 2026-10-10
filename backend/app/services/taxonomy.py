"""Enquiry types, responsible teams and the staff-controlled record fields.

Three sources of truth are kept deliberately separate:

* FORM      - what the verified Jotform requires or offers (mapping/*.mapping.json).
              Only form-required fields can block a handoff.
* OFFICE    - office-owned checklists. None have been supplied yet, so every item here
              is marked basis="suggestion" and is never mandatory.
* MODEL     - suggestions from the analysis provider. Never mandatory, never facts.

Team ownership carries a basis too: "confirmed" (stated in the product brief),
"proposed" (reasonable default, needs office sign-off) or "staff" (staff must decide).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# --------------------------------------------------------------------------- teams --

TEAMS = {
    "constituent": "Constituent team",
    "community": "Community team",
    "comms": "Comms team",
    "administration": "Administration",
}

# --------------------------------------------------------------------- record fields --


@dataclass(frozen=True)
class RecordField:
    id: str
    label: str
    type: str = "text"  # text|textarea|tel|email|date|select|yesno
    sensitivity: str = "normal"  # normal|personal|identifier
    options: tuple[str, ...] = ()
    help: str = ""


F = RecordField
RECORD_FIELDS: tuple[RecordField, ...] = (
    # Contact
    F("first_name", "First name", sensitivity="personal"),
    F("last_name", "Last name", sensitivity="personal"),
    F("phone", "Phone", "tel", "personal"),
    F("email", "Email", "email", "personal"),
    F("address_line1", "Street address", sensitivity="personal"),
    F("address_line2", "Address line 2", sensitivity="personal"),
    F("suburb", "Suburb", sensitivity="personal"),
    F("state", "State", "select", "personal", ("QLD", "NSW", "VIC", "ACT", "TAS", "SA", "WA", "NT")),
    F("postcode", "Postcode", sensitivity="personal"),
    F("organisation", "Organisation"),
    F("contact_role", "Their role (e.g. club president)"),
    # Services Australia
    F("crn", "Centrelink CRN", sensitivity="identifier"),
    F("payment_type", "Payment type"),
    # Immigration
    F("dha_acknowledged", "Received DHA acknowledgement of submission?", "select", options=("Yes", "No")),
    F("migration_agent", "Using a migration agent?"),
    F("visa_subclass", "Type of visa / subclass"),
    F("dha_reference", "DHA reference (TRN / client ID)", sensitivity="identifier",
      help="Not a Jotform field. Only collect if the caseworker needs it."),
    # NDIS / aged care / ATO / DVA / NBN
    F("ndis_number", "NDIS participant number", sensitivity="identifier"),
    F("myagedcare_number", "My Aged Care number", sensitivity="identifier"),
    F("dob", "Date of birth", "date", "personal"),
    F("dva_number", "DVA number", sensitivity="identifier"),
    F("nbn_address_line1", "NBN street address", sensitivity="personal"),
    F("nbn_suburb", "NBN suburb", sensitivity="personal"),
    F("nbn_state", "NBN state", "select", "personal", ("QLD", "NSW", "VIC", "ACT", "TAS", "SA", "WA", "NT")),
    F("nbn_postcode", "NBN postcode", sensitivity="personal"),
    # Congratulations
    F("recipient_title", "Recipient title"),
    F("recipient_first", "Recipient first name", sensitivity="personal"),
    F("recipient_last", "Recipient last name", sensitivity="personal"),
    F("recipient_address_line1", "Recipient street address", sensitivity="personal"),
    F("recipient_suburb", "Recipient suburb", sensitivity="personal"),
    F("recipient_state", "Recipient state", "select", "personal", ("QLD", "NSW", "VIC", "ACT", "TAS", "SA", "WA", "NT")),
    F("recipient_postcode", "Recipient postcode", sensitivity="personal"),
    F("milestone", "Anniversary number (e.g. 60th wedding / 100th birthday)"),
    F("milestone_date", "Anniversary / birthday date", "date"),
    F("arrive_by_date", "Date the message should arrive", "date"),
    # Flags / donations / events / volunteers
    F("flag_reason", "Reason for flag request"),
    F("required_by_date", "Donation required by", "date"),
    F("event_name", "Event name"),
    F("event_location", "Event location / venue"),
    F("event_date", "Event date", "date"),
    F("event_time", "Event time"),
    F("speaking_requested", "Would they like Julie-Ann to speak?", "select", options=("Yes", "No")),
    F("rsvp_by", "Response needed by"),
    F("formal_invitation", "Formal invitation received?", "select", options=("Yes", "No", "Will send")),
    F("volunteer_interest", "How would they like to get involved?", "select",
      options=("I'm keen to help at a local event.", "I'm keen to host a yard sign.",
               "I'm keen to get involved.")),
    # Grants / projects
    F("project", "Project / what the funding is for"),
    F("funding_amount", "Funding sought"),
    F("grant_program", "Known grant program"),
    F("grant_deadline", "Grant / application deadline"),
    # Media
    F("outlet", "Media outlet"),
    F("media_topic", "Story topic"),
    F("media_deadline", "Media deadline"),
    # Parliamentary / ministerial
    F("parliamentary_action", "Requested parliamentary action (question, speech, petition…)"),
    F("portfolio", "Minister / portfolio / department"),
    F("relevant_material", "Relevant material provided"),
    F("action_deadline", "Deadline for action"),
    # Casework common
    F("agency_contacted", "Already raised with the agency?", "select", options=("Yes", "No", "Unsure")),
    F("consent_status", "Consent / authority status", "select",
      options=("Signed consent received", "Verbal only - form to be sent", "Not yet discussed",
               "Not required"),
      help="Record only what the constituent actually confirmed. Never inferred."),
)
FIELD_BY_ID = {f.id: f for f in RECORD_FIELDS}

# ------------------------------------------------------------------ enquiry types --


@dataclass(frozen=True)
class Suggestion:
    """An office-checklist item that is NOT a verified requirement."""

    key: str
    label: str
    question: str
    fields: tuple[str, ...]


@dataclass(frozen=True)
class EnquiryType:
    id: str
    label: str
    group: str  # casework|community|comms|parliamentary|admin
    form_option: str | None  # exact Jotform "How can we help you?" option, if one fits
    team: str | None
    team_basis: str  # confirmed|proposed|staff
    keywords: tuple[str, ...]
    suggestions: tuple[Suggestion, ...] = ()
    actions: tuple[str, ...] = ()
    form_option_basis: str = "verified"  # verified|staff (staff must pick the option)
    description: str = ""


S = Suggestion
OUTCOME = S("outcome", "Requested outcome", "What outcome are they hoping for?", ("@outcome",))
AGENCY_TRIED = S("agency_tried", "Agency already contacted",
                 "Have they already raised this with the agency? Any reference number?",
                 ("agency_contacted",))
CONSENT = S("consent", "Consent / authority (office practice)",
            "Has the constituent agreed, in writing, for the office to act on their behalf?",
            ("consent_status",))
ORG = S("organisation", "Organisation", "Which organisation are they calling on behalf of?",
        ("organisation",))
DEADLINE_Q = S("deadline", "Deadline", "Is there a deadline we need to work to?", ("@deadline",))

CASEWORK_COMMON = (OUTCOME, AGENCY_TRIED, CONSENT)

ENQUIRY_TYPES: tuple[EnquiryType, ...] = (
    # ---- Constituent casework (confirmed: Constituent team) ----
    EnquiryType("services_australia", "Services Australia (Centrelink / Medicare)", "casework",
                "Help with a Services Australia issue", "constituent", "confirmed",
                ("centrelink", "medicare", "mygov", "my gov", "crn", "jobseeker", "pension",
                 "carer payment", "disability support", "family tax", "parenting payment",
                 "youth allowance", "austudy", "rent assistance", "health care card",
                 "concession card", "child support", "services australia", "overpayment",
                 "payment stopped", "payment cancelled", "payment suspended"),
                CASEWORK_COMMON, ("Check whether a formal review has been requested",)),
    EnquiryType("immigration", "Immigration & visas", "casework",
                "Help with an Immigration issue", "constituent", "confirmed",
                ("visa", "immi", "immiaccount", "home affairs", "citizenship", "bridging",
                 "subclass", "migration", "deport", "detention", "sponsor", "protection visa",
                 "partner visa", "dha", "ministerial intervention"),
                CASEWORK_COMMON + (S("dha_ref", "DHA reference (optional)",
                                     "Do they have a TRN or client ID handy? (Optional.)",
                                     ("dha_reference",)),),
                ("Check processing time against published times before escalating",)),
    EnquiryType("ndis", "NDIS", "casework", "Help with an NDIS issue", "constituent", "confirmed",
                ("ndis", "ndia", "plan review", "plan reassessment", "participant",
                 "local area coordinator", "lac", "support coordinator", "plan manager",
                 "access request"),
                CASEWORK_COMMON),
    EnquiryType("aged_care", "My Aged Care", "casework", "Help with a MyAgedCare issue",
                "constituent", "confirmed",
                ("aged care", "my aged care", "myagedcare", "home care package",
                 "support at home", "acat", "aged care assessment", "nursing home",
                 "residential care", "respite"),
                CASEWORK_COMMON),
    EnquiryType("ato", "ATO / tax", "casework", "Help with an ATO issue", "constituent",
                "confirmed",
                ("ato", "tax return", "tax debt", "tax refund", "taxation", "superannuation",
                 "abn", "gst", "tax office"),
                CASEWORK_COMMON, ("Remind constituent not to share their TFN",)),
    EnquiryType("nbn", "NBN / telecommunications", "casework", "Help with an NBN issue",
                "constituent", "confirmed",
                ("nbn", "internet", "broadband", "phone line", "telstra", "optus", "fixed wireless",
                 "connection fault"),
                (OUTCOME, S("nbn_ticket", "Provider and fault reference",
                            "Who is their provider and what fault number were they given?",
                            ("@details",)))),
    EnquiryType("dva", "Veterans' Affairs", "casework", "Help with a Veterans Affairs issue",
                "constituent", "confirmed",
                ("dva", "veteran", "veterans", "gold card", "white card", "open arms",
                 "defence force", "adf"),
                CASEWORK_COMMON),
    EnquiryType("other_casework", "Other agency / casework", "casework",
                "Help with another Issue", "constituent", "proposed",
                ("passport", "department", "agency", "decision", "appeal", "complaint about",
                 "waiting months", "no response from"),
                CASEWORK_COMMON, form_option_basis="staff",
                description="Federal casework that has no dedicated form option."),
    # ---- Community ----
    EnquiryType("community_engagement", "Community engagement", "community",
                "Help with another Issue", "community", "confirmed",
                ("club", "association", "community group", "school", "church", "charity",
                 "not-for-profit", "nfp", "residents group", "sporting", "rotary", "lions"),
                (ORG, S("contact_role", "Contact's role", "What's their role in the organisation?",
                        ("contact_role",)),
                 S("follow_up", "Requested follow-up", "What would they like the office to do next?",
                   ("@outcome",))),
                form_option_basis="staff",
                description="Organisation relationship; no dedicated form option."),
    EnquiryType("grant", "Grant assistance", "community", "Grant Inquiries", "community",
                "proposed",
                ("grant", "grants", "funding", "fund", "funded", "volunteer grants",
                 "funding for", "apply for funding", "equipment funding"),
                (ORG, S("project", "Project", "What is the project or equipment?", ("project",)),
                 S("funding", "Funding sought", "Roughly how much funding are they after?",
                   ("funding_amount",)),
                 S("program", "Known program", "Do they have a particular grant program in mind?",
                   ("grant_program",)),
                 S("grant_deadline", "Grant deadline", "Is there an application deadline?",
                   ("grant_deadline",))),
                ("Check current funding options (do not promise funding)",)),
    EnquiryType("event_invitation", "Event invitation", "community", "Invitation to an event",
                "community", "proposed",
                ("invite", "invitation", "invited", "presentation night", "event", "launch",
                 "official opening", "opening", "ceremony", "fete", "gala", "dinner", "attend",
                 "come along", "guest speaker", "present the awards", "awards night"),
                (ORG, S("event_name", "Event name", "What's the event called?", ("event_name",)),
                 S("event_when", "Event date and time", "When is it, date and time?",
                   ("event_date", "event_time")),
                 S("venue", "Venue", "Where is it being held?", ("event_location",)),
                 S("role", "Requested role", "Would they like Julie-Ann to speak or present?",
                   ("speaking_requested",)),
                 S("formal_invite", "Formal invitation", "Can they send a formal invitation?",
                   ("formal_invitation",)),
                 S("rsvp", "Response deadline", "When do they need an answer by?", ("rsvp_by",))),
                ("Request a formal invitation", "Check Julie-Ann's diary (no attendance promised)")),
    EnquiryType("donation_sponsorship", "Donation / sponsorship request", "community",
                "Request a Donation/Sponsorship", "community", "proposed",
                ("donation", "donate", "sponsorship", "sponsor our", "raffle", "prize",
                 "auction item"),
                (ORG, S("required_by", "Required by", "When do they need it by?",
                        ("required_by_date",)))),
    EnquiryType("flag", "Flag request", "community", "Request a Flag", "community", "proposed",
                ("flag", "flags", "flagpole", "flag pole"),
                (S("flag_reason", "Reason", "What's the flag for?", ("flag_reason",)),
                 S("flag_size", "Size", "Large for a flag pole, or small for indoor display?",
                   ("@details",)))),
    EnquiryType("congratulations", "Congratulatory message", "community",
                "Request a Congratulations Message", "community", "proposed",
                ("birthday", "anniversary", "congratulat", "100th", "90th", "60th", "50th",
                 "milestone", "centenarian"),
                (S("recipient", "Recipient", "Who is the message for?",
                   ("recipient_first", "recipient_last")),
                 S("milestone", "Milestone", "Which birthday or anniversary is it?", ("milestone",)),
                 S("milestone_date", "Milestone date", "What's the date?", ("milestone_date",)),
                 S("arrive_by", "Arrive by", "When should the message arrive?",
                   ("arrive_by_date",))),
                ("Proof of age / marriage may be needed (form upload)",)),
    EnquiryType("volunteer", "Volunteer enquiry", "community", "Volunteer Inquiries", None,
                "staff",
                ("volunteer", "volunteering", "yard sign", "help out", "get involved",
                 "doorknock", "campaign"),
                (S("interest", "How they'd like to help", "How would they like to get involved?",
                   ("volunteer_interest",)),),
                description="Ownership not confirmed. May be campaign rather than electorate "
                            "office business; staff confirm."),
    # ---- Comms (confirmed) ----
    EnquiryType("media", "Communications & media", "comms", "Media Inquiries", "comms",
                "confirmed",
                ("journalist", "reporter", "media", "newspaper", "radio", "tv", "television",
                 "podcast", "interview", "comment", "story", "courier-mail", "abc", "outlet",
                 "editor", "press"),
                (S("outlet", "Outlet", "Which outlet are they from?", ("outlet",)),
                 S("topic", "Topic", "What is the story about?", ("media_topic",)),
                 S("request", "Request", "What are they asking for: comment, interview, photo?",
                   ("@details",)),
                 S("media_deadline", "Deadline", "What's their deadline?", ("media_deadline",))),
                ("Refer to Comms before the stated deadline",)),
    # ---- Parliamentary / ministerial (ownership: staff) ----
    EnquiryType("parliamentary", "Parliamentary matter", "parliamentary",
                "Help with another Issue", None, "staff",
                ("parliament", "question time", "question on notice", "petition", "speech",
                 "raise it in parliament", "senate", "estimates", "committee", "bill",
                 "legislation", "motion", "hansard", "vote on"),
                (S("parl_action", "Requested action",
                   "What would they like Julie-Ann to do in Parliament?",
                   ("parliamentary_action",)),
                 S("material", "Relevant material", "Is there material they can send through?",
                   ("relevant_material",)),
                 S("parl_deadline", "Deadline", "Is there a sitting date or deadline?",
                   ("action_deadline",))),
                ("Staff to confirm ownership and whether parliamentary action is appropriate",),
                form_option_basis="staff"),
    EnquiryType("ministerial", "Ministerial referral", "parliamentary",
                "Help with another Issue", None, "staff",
                ("minister", "ministerial", "write to the minister", "refer to the minister",
                 "portfolio", "minister's office"),
                (S("portfolio", "Minister / department", "Which Minister or department is it for?",
                   ("portfolio",)),
                 OUTCOME,
                 S("prior_contact", "Prior contact",
                   "Have they already contacted the department or Minister?", ("agency_contacted",)),
                 CONSENT),
                ("Prepare a ministerial referral for staff approval",),
                form_option_basis="staff"),
    # ---- Administration (confirmed) ----
    EnquiryType("admin", "General / administrative", "admin", "Help with another Issue",
                "administration", "confirmed",
                ("office hours", "opening hours", "appointment", "address of the office",
                 "contact details", "general enquiry", "information"),
                (OUTCOME,), form_option_basis="staff"),
)
TYPE_BY_ID = {t.id: t for t in ENQUIRY_TYPES}

# Keywords that are too common to identify a type on their own. They count half, so a type
# needs a stronger cue (or two weak ones) before it becomes an active suggestion.
WEAK_KEYWORDS = frozenset({
    "funding", "fund", "funded", "event", "opening", "attend", "dinner", "comment", "story",
    "media", "outlet", "information", "department", "agency", "decision", "club", "school",
    "church", "charity", "minister", "portfolio", "internet", "super", "speech", "bill",
    "committee", "vote on", "motion", "editor", "press", "launch", "flag", "flags", "sponsor our",
    "prize", "help out", "campaign", "complaint about", "appeal", "tv", "radio", "interview",
})


def suggested_team(type_ids: list[str]) -> dict[str, Any]:
    """Deterministic team suggestion from the (staff-approved or suggested) enquiry types."""
    if not type_ids:
        return {"team": "administration", "basis": "proposed",
                "rationale": "No specific enquiry type identified: general intake (Administration)."}
    primary = TYPE_BY_ID[type_ids[0]]
    if primary.team is None:
        return {"team": None, "basis": "staff",
                "rationale": f"Ownership for '{primary.label}' is not confirmed: staff to decide."}
    teams = {TYPE_BY_ID[t].team for t in type_ids if TYPE_BY_ID[t].team}
    rationale = f"'{primary.label}' work goes to the {TEAMS[primary.team]}."
    if len(teams) > 1:
        others = ", ".join(TEAMS[t] for t in sorted(teams - {primary.team}))
        rationale += f" Secondary work may involve: {others}."
    return {"team": primary.team, "basis": primary.team_basis, "rationale": rationale}


def meta() -> dict[str, Any]:
    return {
        "teams": TEAMS,
        "record_fields": [
            {"id": f.id, "label": f.label, "type": f.type, "sensitivity": f.sensitivity,
             "options": list(f.options), "help": f.help} for f in RECORD_FIELDS
        ],
        "enquiry_types": [
            {"id": t.id, "label": t.label, "group": t.group, "form_option": t.form_option,
             "form_option_basis": t.form_option_basis, "team": t.team,
             "team_basis": t.team_basis, "description": t.description,
             "suggestions": [{"key": s.key, "label": s.label, "question": s.question,
                              "fields": list(s.fields)} for s in t.suggestions],
             "actions": list(t.actions)}
            for t in ENQUIRY_TYPES
        ],
    }
