"""Constituent communications in the office's voice, signed "Team Moreton".

The template engine is deterministic and always available. If GENERATE_MODEL is
set, the draft is additionally polished by a chat model on OpenRouter. The model
only ever sees placeholders ({FIRST_NAME}) and PII-redacted notes; real names are
substituted back in afterwards.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from ..config import settings
from . import rules

log = logging.getLogger(__name__)

NAME_TOKEN = "{FIRST_NAME}"

AGENCY = {
    "services_australia": "Services Australia",
    "immigration": "the Department of Home Affairs",
    "ndis": "the NDIA",
    "aged_care": "My Aged Care",
    "general": "the relevant agency",
}
SUB_AGENCY = {"ATO": "the ATO", "NBN / telco": "your provider and NBN Co", "DVA": "DVA"}

TOPIC = {
    "services_australia": "your Centrelink matter",
    "immigration": "your visa application",
    "ndis": "your NDIS matter",
    "aged_care": "your aged care matter",
    "ato_nbn_dva": "your enquiry",
    "flags_messages": "your request",
    "general": "your enquiry",
}

EMPATHY = {
    "services_australia": "We know how much a payment problem can affect everything else, "
                          "and we're here to help.",
    "immigration": "We know how stressful waiting on a visa can be for you and your family.",
    "ndis": "We know how important getting the right supports in place is.",
    "aged_care": "We know how important it is to get the right care sorted, for you and "
                 "your family.",
    "ato_nbn_dva": "We know these things can be frustrating to chase up on your own.",
    "general": "We're glad you reached out.",
}


def agency_for(category: str, data: dict[str, Any]) -> str:
    if category == "ato_nbn_dva":
        return SUB_AGENCY.get(str(data.get("sub_type") or ""), "the relevant agency")
    return AGENCY.get(category, "the relevant agency")


def topic_for(category: str, data: dict[str, Any]) -> str:
    if category == "services_australia" and data.get("payment_type"):
        return f"your {str(data['payment_type']).strip()} matter"
    if category == "immigration" and data.get("visa_subclass"):
        return f"your subclass {str(data['visa_subclass']).strip()} visa application"
    if category == "ato_nbn_dva":
        return {"ATO": "your tax matter", "NBN / telco": "your internet connection",
                "DVA": "your DVA matter"}.get(str(data.get("sub_type") or ""), "your enquiry")
    if category == "flags_messages" and data.get("request_type"):
        return f"your {str(data['request_type']).strip().lower()} request"
    return TOPIC.get(category, "your enquiry")


def _signature() -> str:
    lines = ["Warm regards,", "", settings.office_signoff, settings.office_name]
    contact = " | ".join(x for x in (settings.office_phone, settings.office_email) if x)
    if contact:
        lines.append(contact)
    return "\n".join(lines)


def _greeting(first: str) -> str:
    return f"Hi {first},"


def acknowledgement(category: str, data: dict[str, Any], flags: list[dict[str, Any]]) -> dict[str, str]:
    agency = agency_for(category, data)
    topic = topic_for(category, data)
    consent = bool(data.get("consent_signed")) and data.get("consent_signed") not in ("false", "0")
    paras = [
        f"Thanks so much for getting in touch with our office about {topic}. "
        + EMPATHY.get(category, EMPATHY["general"]),
    ]
    if category == "flags_messages":
        paras.append(
            "We've passed your request on to the team and we'll be in touch once it's ready. "
            "If there's a date you need it by, just let us know so we can do our best to "
            "make it happen."
        )
    else:
        if consent:
            paras.append(
                f"We've opened a case for you and will raise this directly with {agency} "
                "on your behalf."
            )
        else:
            paras.append(
                f"We've opened a case for you. Before we can raise this with {agency}, we'll "
                "need your signed privacy consent form — agencies can't discuss your details "
                "with us without it. As soon as it's back with us, we'll get things moving."
            )
        paras.append(
            "While our office can't make decisions on behalf of an agency, we'll make sure "
            "your matter gets looked at and we'll keep you updated every step of the way."
        )
    if flags:
        refs = []
        for f in flags:
            refs += [f"{r['name']}: {r['contact']}" for r in f["referrals"]]
        paras.append(
            "In the meantime, please don't hesitate to reach out for support:\n"
            + "\n".join(f"• {r}" for r in dict.fromkeys(refs))
        )
    paras.append("If anything changes, just reply to this email or give us a call.")
    email = "\n\n".join([_greeting(NAME_TOKEN)] + paras + [_signature()])

    if category == "flags_messages":
        sms_core = "thanks for your request - we've got it and will be in touch soon."
    elif consent:
        sms_core = f"thanks for calling about {topic}. We've opened a case and will raise it with {agency}."
    else:
        sms_core = (f"thanks for calling about {topic}. We've opened a case - please sign & return "
                    "the consent form so we can contact the agency for you.")
    sms = f"Hi {NAME_TOKEN}, {sms_core} - {settings.office_signoff}"
    subject = f"We've received {topic}" if category != "flags_messages" else "Thanks for your request"
    return {"subject": subject[0].upper() + subject[1:], "email": email, "sms": sms}


def resolution(category: str, data: dict[str, Any], tmpl: list[dict[str, Any]],
               flags: list[dict[str, Any]]) -> dict[str, str]:
    topic = topic_for(category, data)
    paras = [f"Thanks so much for chatting with our office today about {topic}. "
             "As promised, here's the information we went through:"]
    for t in tmpl:
        paras.append(f"{t['title']}\n{t['body'].strip()}")
    if flags:
        refs = []
        for f in flags:
            refs += [f"{r['name']}: {r['contact']}" for r in f["referrals"]]
        paras.append("Support is also available any time:\n"
                     + "\n".join(f"• {r}" for r in dict.fromkeys(refs)))
    paras.append("If you get stuck or it doesn't sort things out, just reply to this email or "
                 "give us a call — we're always happy to help.")
    email = "\n\n".join([_greeting(NAME_TOKEN)] + paras + [_signature()])
    sms_bits = " ".join(t["sms"].strip() for t in tmpl if t.get("sms"))
    sms = f"Hi {NAME_TOKEN}, thanks for calling. {sms_bits} - {settings.office_signoff}".strip()
    return {"subject": f"Information about {topic}", "email": email, "sms": sms}


def _fill(draft: dict[str, str], first: str) -> dict[str, str]:
    return {k: v.replace(NAME_TOKEN, first or "there") for k, v in draft.items()}


SYSTEM_PROMPT = """You polish constituent correspondence for an Australian federal \
electorate office (Moreton, Brisbane). Voice: warm, local, plain English, community-first, \
Australian spelling, never bureaucratic. Rules:
- Keep every fact, phone number, link and step from the draft. Add NO new facts, numbers, \
  timeframes, eligibility claims or promises of outcome.
- Keep the literal placeholder {FIRST_NAME} exactly as written.
- Keep the sign-off block exactly as written.
- The SMS must stay under 320 characters.
Return only JSON: {"subject": str, "email": str, "sms": str}."""


async def polish(draft: dict[str, str], notes: str, data: dict[str, Any] | None = None,
                 client: httpx.AsyncClient | None = None) -> dict[str, str] | None:
    if not (settings.openrouter_api_key and settings.generate_model):
        return None
    user = (
        "Context (identifiers removed):\n" + rules.redact_pii(notes, data)[:3000]
        + "\n\nDraft to polish:\n" + json.dumps(draft)
    )
    own = client is None
    client = client or httpx.AsyncClient(timeout=25)
    try:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}",
                     "X-Title": "Moreton Casework Fast-Resolver"},
            json={
                "model": settings.generate_model,
                "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                             {"role": "user", "content": user}],
                "response_format": {"type": "json_object"},
                "temperature": 0.4,
            },
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        match = re.search(r"\{.*\}", content, re.S)
        out = json.loads(match.group(0) if match else content)
        if not all(isinstance(out.get(k), str) and out[k].strip() for k in ("subject", "email", "sms")):
            return None
        if settings.office_signoff not in out["email"]:
            return None  # the model dropped the sign-off; don't trust the rest either
        return {k: out[k] for k in ("subject", "email", "sms")}
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
        log.warning("Draft polishing failed, using template draft: %s", exc)
        return None
    finally:
        if own:
            await client.aclose()


async def generate(kind: str, category: str, data: dict[str, Any], notes: str,
                   tmpl: list[dict[str, Any]], polish_with_model: bool = True) -> dict[str, Any]:
    flags = rules.safety_flags(notes)
    if kind == "resolution" and tmpl:
        draft = resolution(category, data, tmpl, flags)
    else:
        draft = acknowledgement(category, data, flags)
    engine = "template"
    if polish_with_model:
        polished = await polish(draft, notes, data)
        if polished:
            draft, engine = polished, "model"
    first = str(data.get("first_name") or "").strip()
    return {**_fill(draft, first), "engine": engine}
