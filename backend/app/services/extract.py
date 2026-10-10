"""Deterministic extraction from officer notes.

Everything returned here is a *proposal* with the exact note text that supports it.
Staff accept, edit or reject proposals; nothing is treated as fact automatically.

Deliberately NOT extracted: names, consent, eligibility. Dates are proposed with the
original wording and only resolved to a calendar date when the notes state one.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

# --------------------------------------------------------------------- identifiers --

_TFN = re.compile(
    r"\b(?:TFN|tax file(?: number)?)(?:\s+(?:is|was|=))?[:#\s-]*(\d{3}[ -]?\d{3}[ -]?\d{2,3})\b", re.I)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?<![\d])(?:\+?61[ -]?|0)[2-478](?:[ -]?\d){8}(?!\d)")
_CRN = re.compile(r"\b(\d{3})[ -]?(\d{3})[ -]?(\d{3})[ -]?([A-Za-z])\b")
_NDIS = re.compile(r"\b(43\d{7})\b")
_MAC = re.compile(r"\b(AC\d{8})\b", re.I)
_TRN = re.compile(r"\b(?:TRN|transaction reference(?: number)?|client id)[:#\s-]*([A-Z0-9]{8,14})\b", re.I)
_SUBCLASS = re.compile(r"\bsubclass\s*#?\s*(\d{3})\b", re.I)
_DVA = re.compile(r"\bDVA(?: file)?(?: no\.?| number)?[:#\s-]*([A-Z]{1,4}\d{4,7}[A-Z]?)\b", re.I)
_POSTCODE = re.compile(r"\b(?:QLD|Qld|Queensland)\s*,?\s*(4\d{3})\b")

PAYMENT_TYPES = (
    "Age Pension", "JobSeeker Payment", "JobSeeker", "Disability Support Pension", "Carer Payment",
    "Carer Allowance", "Family Tax Benefit", "Parenting Payment", "Youth Allowance", "Austudy",
    "ABSTUDY", "Rent Assistance", "Health Care Card", "Pensioner Concession Card",
    "Commonwealth Seniors Health Card", "Child Care Subsidy", "Paid Parental Leave",
)
_PAYMENT = re.compile(r"\b(" + "|".join(re.escape(p) for p in PAYMENT_TYPES) + r")\b", re.I)

IDENTIFIER_PATTERNS: tuple[tuple[str, re.Pattern[str], Any], ...] = (
    ("email", _EMAIL, lambda m: m.group(0)),
    ("phone", _PHONE, lambda m: re.sub(r"[ -]", "", m.group(0))),
    ("crn", _CRN, lambda m: f"{m.group(1)} {m.group(2)} {m.group(3)}{m.group(4).upper()}"),
    ("ndis_number", _NDIS, lambda m: m.group(1)),
    ("myagedcare_number", _MAC, lambda m: m.group(1).upper()),
    ("dha_reference", _TRN, lambda m: m.group(1).upper()),
    ("visa_subclass", _SUBCLASS, lambda m: m.group(1)),
    ("dva_number", _DVA, lambda m: m.group(1).upper()),
    ("postcode", _POSTCODE, lambda m: m.group(1)),
    ("payment_type", _PAYMENT, lambda m: next(p for p in PAYMENT_TYPES
                                               if p.lower() == m.group(1).lower())),
)


def contains_tfn(text: str) -> bool:
    return bool(_TFN.search(text or ""))


def redact_tfn(text: str) -> str:
    return _TFN.sub("[TFN removed]", text or "")


def _mask_tfn(text: str) -> str:
    """Blank TFNs out while keeping offsets stable, so evidence spans stay valid."""
    return _TFN.sub(lambda m: " " * len(m.group(0)), text)


def facts(notes: str) -> list[dict[str, Any]]:
    """Identifier proposals, each with evidence. Repeated identical values are merged."""
    text = _mask_tfn(notes or "")
    out: list[dict[str, Any]] = []
    taken: list[tuple[int, int]] = []
    for field_id, pattern, norm in IDENTIFIER_PATTERNS:
        for m in pattern.finditer(text):
            span = (m.start(), m.end())
            if any(s < span[1] and span[0] < e for s, e in taken):
                continue  # already claimed by an earlier, more specific pattern
            value = norm(m)
            existing = next((f for f in out if f["field"] == field_id and f["value"] == value), None)
            if existing:
                continue
            taken.append(span)
            out.append({"field": field_id, "value": value,
                        "evidence": {"start": span[0], "end": span[1], "text": notes[span[0]:span[1]]}})
    return out


# --------------------------------------------------------------------------- dates --

_MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
_ABS_DATE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|"
    r"july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b"
    r"(?:,?\s+(\d{4}))?", re.I)
_NUM_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")
_REL_DATE = re.compile(
    r"\b(today|tonight|tomorrow|this (?:morning|afternoon|evening|week|month)|"
    r"(?:next|this) (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|week|month)|"
    r"end of (?:the )?(?:day|week|month)|close of business|cob|"
    r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b", re.I)
_TIME = re.compile(r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm))\b", re.I)
_DEADLINE_CTX = re.compile(r"\b(deadline|due|by|before|closes?|closing|need(?:s|ed)? (?:it |an answer |a response )?by|"
                           r"no later than|until|cut-?off|rsvp)\b", re.I)
_EVENT_CTX = re.compile(r"\b(event|night|dinner|launch|presentation|ceremony|fete|gala|on the)\b", re.I)


def _resolve(day: int, month: int, year: int | None, today: date) -> tuple[str | None, bool]:
    """Return (iso, year_assumed). Year is assumed to be the next occurrence if not stated."""
    try:
        if year is not None:
            if year < 100:
                year += 2000
            return date(year, month, day).isoformat(), False
        d = date(today.year, month, day)
        if d < today:
            d = date(today.year + 1, month, day)
        return d.isoformat(), True
    except ValueError:
        return None, False


def dates(notes: str, today: date | None = None) -> list[dict[str, Any]]:
    """Dates and times mentioned in the notes, classified by nearby wording."""
    today = today or date.today()
    text = notes or ""
    found: list[dict[str, Any]] = []
    spans: list[tuple[int, int]] = []

    def add(m: re.Match[str], iso: str | None, year_assumed: bool, relative: bool) -> None:
        start, end = m.start(), m.end()
        # Extend to an adjacent time ("3pm today", "today at 3pm").
        after = re.match(r"\s*(?:at\s+)?" + _TIME.pattern, text[end:end + 14], re.I)
        before = re.search(_TIME.pattern + r"\s*(?:on\s+)?$", text[max(0, start - 14):start], re.I)
        if after:
            end += after.end()
        if before:
            start -= len(text[max(0, start - 14):start]) - before.start()
        if any(s < end and start < e for s, e in spans):
            return
        spans.append((start, end))
        # Context is limited to the same sentence.
        window = re.split(r"[.!?\n]", text[max(0, start - 45):start])[-1].lower()
        after_ctx = re.split(r"[.!?\n]", text[end:end + 25])[0]
        if _DEADLINE_CTX.search(window):
            kind = "deadline"
        elif _EVENT_CTX.search(window + " " + after_ctx):
            kind = "event"
        else:
            kind = "date"
        found.append({
            "text": text[start:end], "iso": iso, "kind": kind,
            "needs_confirmation": relative or year_assumed or iso is None,
            "evidence": {"start": start, "end": end, "text": text[max(0, start - 30):end + 10].strip()},
        })

    for m in _ABS_DATE.finditer(text):
        iso, assumed = _resolve(int(m.group(1)), _MONTHS[m.group(2)[:3].lower()],
                                int(m.group(3)) if m.group(3) else None, today)
        add(m, iso, assumed, False)
    for m in _NUM_DATE.finditer(text):
        iso, assumed = _resolve(int(m.group(1)), int(m.group(2)),
                                int(m.group(3)) if m.group(3) else None, today)
        add(m, iso, assumed, False)
    for m in _REL_DATE.finditer(text):
        add(m, None, False, True)
    for m in _TIME.finditer(text):
        if _DEADLINE_CTX.search(text[max(0, m.start() - 25):m.start()]):
            add(m, None, False, True)
    found.sort(key=lambda d: d["evidence"]["start"])
    return found


# ------------------------------------------------------------- summary proposals --

_OUTCOME_KW = re.compile(
    r"\b(wants?|would like|asking (?:for|us to|if)|requesting|hoping|"
    r"needs? (?:us|julie-ann|the office) to|seeking)\b", re.I)


def outcome_proposal(notes: str) -> dict[str, Any] | None:
    """The sentence containing the first 'wants / would like / asking for…' phrase."""
    text = notes or ""
    m = _OUTCOME_KW.search(text)
    if not m:
        return None
    # Expand to sentence boundaries (linear time, unlike a greedy regex).
    start = max(text.rfind(c, 0, m.start()) for c in ".!?\n") + 1
    ends = [i for i in (text.find(c, m.end()) for c in ".!?\n") if i != -1]
    end = min(ends) + 1 if ends else len(text)
    sentence = " ".join(text[start:end].split())[:300]
    return {"text": sentence, "evidence": {"start": start, "end": end, "text": sentence}}


def issue_proposal(notes: str) -> str:
    """First one or two sentences of the notes, as a starting point for the summary."""
    sentences = re.split(r"(?<=[.!?])\s+", " ".join((notes or "").split()))
    out = ""
    for s in sentences:
        if len(out) + len(s) > 280:
            break
        out = f"{out} {s}".strip()
    return out or " ".join((notes or "").split())[:280]


# --------------------------------------------------------------------- safety flags --

SAFETY_FLAGS = (
    ("self_harm", "Possible risk of self-harm",
     (r"suicid", r"kill (?:myself|himself|herself|themselves)", r"end (?:it all|my life)",
      r"self[- ]harm", r"don'?t want to (?:live|be here)"),
     (("Emergency", "000"), ("Lifeline", "13 11 14"), ("Suicide Call Back Service", "1300 659 467"))),
    ("family_violence", "Possible domestic or family violence",
     (r"domestic violence", r"\bdv\b", r"family violence", r"unsafe at home",
      r"afraid of (?:him|her|them|my partner)"),
     (("Emergency", "000"), ("DVConnect Womensline (Qld)", "1800 811 811"),
      ("1800RESPECT", "1800 737 732"))),
    ("homelessness", "Homeless or at risk",
     (r"homeless", r"sleeping (?:in (?:my|the|a) car|rough)", r"evict", r"nowhere to (?:live|stay)"),
     (("Qld Homeless Hotline", "1800 474 753"),)),
    ("financial_crisis", "No money or food",
     (r"no money", r"no food", r"can'?t (?:afford|pay) (?:food|rent)", r"\bhungry\b"),
     (("National Debt Helpline", "1800 007 007"), ("Ask Izzy", "askizzy.org.au"))),
)


def safety_flags(notes: str) -> list[dict[str, Any]]:
    text = (notes or "").lower()
    out = []
    for key, label, patterns, referrals in SAFETY_FLAGS:
        if any(re.search(p, text) for p in patterns):
            out.append({"key": key, "label": label,
                        "referrals": [{"name": n, "contact": c} for n, c in referrals]})
    return out


# ------------------------------------------------------------------- redaction --

PERSONAL_FIELDS = ("first_name", "last_name", "address_line1", "suburb", "email", "phone",
                   "organisation", "recipient_first", "recipient_last")


def redact(text: str, values: dict[str, Any] | None = None) -> str:
    """Remove identifiers (and any personal values already captured) before text leaves the server."""
    if not text:
        return ""
    for fid in PERSONAL_FIELDS:
        v = str((values or {}).get(fid) or "").strip()
        if len(v) >= 2:
            text = re.sub(r"(?<!\w)" + re.escape(v) + r"(?!\w)", f"[{fid.upper()}]", text, flags=re.I)
    text = _TFN.sub("[TFN]", text)
    text = _EMAIL.sub("[EMAIL]", text)
    text = _CRN.sub("[CRN]", text)
    text = _NDIS.sub("[NDIS_NO]", text)
    text = _MAC.sub("[MAC_NO]", text)
    text = _TRN.sub("[DHA_REF]", text)
    text = _DVA.sub("[DVA_NO]", text)
    text = _PHONE.sub("[PHONE]", text)
    text = re.sub(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", "[DATE]", text)
    return text
