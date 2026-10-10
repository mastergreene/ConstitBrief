"""Build a prefilled URL for the office's Jotform casework portal.

The PWA mirrors this logic in frontend/js/jotform.js so it works offline; keep
the two in step (tests/test_jotform.py pins the behaviour).
"""
from __future__ import annotations

from datetime import date
from typing import Any
from urllib.parse import urlencode

from ..config import settings
from . import rules

# Jotform query-parameter names on form 252413844700855.
PARAMS = {
    "first_name": "name[first]",
    "last_name": "name[last]",
    "phone": "phoneNumber120",
    "email": "email",
    "address_line1": "address132[addr_line1]",
    "suburb": "address132[city]",
    "state": "address132[state]",
    "postcode": "address132[postal]",
    "crn": "crn",
}
TYPE_PARAM = "typeA"
NOTES_PARAM = "moreInformation"

# Browsers and Jotform cope with long URLs, but stay well clear of ~8k limits on proxies.
MAX_URL_LENGTH = 7000

# Fields already sent as their own parameter, or not useful in the case notes.
_SKIP_IN_DETAILS = set(PARAMS) | {"category"}


def typea_value(category: str) -> str:
    mapping = settings.jotform_typea_map or {}
    if category in mapping:
        return str(mapping[category])
    cat = rules.CATEGORY_BY_ID.get(category)
    return cat.label if cat else ""


def _fmt(field_id: str, value: Any) -> str:
    f = rules.FIELD_BY_ID.get(field_id)
    if isinstance(value, bool) or (f and f.type == "checkbox"):
        return "Yes" if value in (True, "true", "on", "1", 1) else "Not confirmed"
    s = str(value).strip()
    if f and f.type == "date":
        try:
            return date.fromisoformat(s).strftime("%d/%m/%Y")
        except ValueError:
            return s
    return s


def compose_details(category: str, data: dict[str, Any], notes: str, urgency: str = "") -> str:
    lines = [f"Category: {rules.CATEGORY_BY_ID.get(category, rules.CATEGORY_BY_ID['general']).label}"]
    if urgency and urgency != "routine":
        lines.append(f"Urgency: {urgency.replace('_', ' ').upper()}")
    for f in rules.fields_for(category):
        if f.id in _SKIP_IN_DETAILS:
            continue
        v = data.get(f.id)
        if f.type == "checkbox":
            lines.append(f"{f.label}: {_fmt(f.id, v)}")
        elif rules._filled(v):
            lines.append(f"{f.label}: {_fmt(f.id, v)}")
    notes = rules.redact_tfn((notes or "").strip())
    if notes:
        lines += ["", "Notes:", notes]
    lines += ["", "(Prepared with the Moreton Casework Fast-Resolver)"]
    return "\n".join(lines)


def build_url(
    category: str, data: dict[str, Any], notes: str = "", urgency: str = ""
) -> dict[str, Any]:
    params: dict[str, str] = {}
    for fid, pname in PARAMS.items():
        v = data.get(fid)
        if rules._filled(v):
            params[pname] = str(v).strip()
    if "address132[state]" not in params and rules._filled(data.get("address_line1")):
        params["address132[state]"] = "QLD"
    if t := typea_value(category):
        params[TYPE_PARAM] = t

    details = compose_details(category, data, notes, urgency)
    base = settings.jotform_url
    truncated = False

    def make(det: str) -> str:
        return f"{base}?{urlencode({**params, NOTES_PARAM: det})}"

    url = make(details)
    if len(url) > MAX_URL_LENGTH:
        truncated = True
        marker = "\n[...notes truncated - paste the full notes into the form]"
        lo, hi = 0, len(details)
        while lo < hi:  # longest prefix that fits
            mid = (lo + hi + 1) // 2
            if len(make(details[:mid] + marker)) <= MAX_URL_LENGTH:
                lo = mid
            else:
                hi = mid - 1
        details = details[:lo] + marker
        url = make(details)
    return {"url": url, "params": {**params, NOTES_PARAM: details}, "truncated": truncated,
            "full_details": compose_details(category, data, notes, urgency)}
