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
from . import extract

log = logging.getLogger(__name__)

NAME_TOKEN = "{FIRST_NAME}"

AGENCY = {
    "services_australia": "Services Australia", "immigration": "the Department of Home Affairs",
    "ndis": "the NDIA", "aged_care": "My Aged Care", "ato": "the ATO",
    "nbn": "your provider and NBN Co", "dva": "DVA",
}

TOPIC = {
    "services_australia": "your Centrelink matter", "immigration": "your visa matter",
    "ndis": "your NDIS matter", "aged_care": "your aged care matter", "ato": "your tax matter",
    "nbn": "your internet connection", "dva": "your DVA matter", "grant": "your funding enquiry",
    "event_invitation": "your invitation", "donation_sponsorship": "your request",
    "flag": "your flag request", "congratulations": "your request for a congratulatory message",
    "media": "your media enquiry", "community_engagement": "your enquiry",
}

# Next-step wording per type. Never promises funding, agency outcomes or attendance.
NEXT_STEP = {
    "grant": "We'll look into what funding options may be available and come back to you. "
             "We can't guarantee funding, but we're happy to help you find the right program.",
    "event_invitation": "Thanks for thinking of Julie-Ann. We'll check her availability and "
                        "come back to you. If you can, please send a formal invitation with the "
                        "event details.",
    "media": "We've passed your request to our communications team.",
    "flag": "We've passed your request on and will be in touch.",
    "congratulations": "We've passed your request on and will be in touch.",
    "donation_sponsorship": "We've passed your request on and will be in touch.",
}

CASEWORK = {"services_australia", "immigration", "ndis", "aged_care", "ato", "nbn", "dva",
            "other_casework", "ministerial"}


def topic_for(type_id: str, data: dict[str, Any]) -> str:
    if type_id == "services_australia" and data.get("payment_type"):
        return f"your {str(data['payment_type']).strip()} matter"
    return TOPIC.get(type_id, "your enquiry")


def _signature() -> str:
    lines = ["Warm regards,", "", settings.office_signoff, settings.office_name]
    contact = " | ".join(x for x in (settings.office_phone, settings.office_email) if x)
    if contact:
        lines.append(contact)
    return "\n".join(lines)


def _referrals(flags: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    for f in flags:
        refs += [f"{r['name']}: {r['contact']}" for r in f["referrals"]]
    return list(dict.fromkeys(refs))


def acknowledgement(type_id: str, data: dict[str, Any], flags: list[dict[str, Any]]) -> dict[str, str]:
    topic = topic_for(type_id, data)
    consent_ok = data.get("consent_status") in ("Signed consent received", "Not required")
    paras = [f"Thanks so much for getting in touch with our office about {topic}."]
    if type_id in CASEWORK:
        agency = AGENCY.get(type_id, "the relevant agency")
        paras.append("Our team will look at how we can help.")
        if not consent_ok:
            paras.append(f"Before we can raise this with {agency}, we may need your written "
                         "consent, as agencies generally can't discuss your details with us "
                         "without it. We'll let you know if that's needed.")
        paras.append("Our office can't make decisions on behalf of an agency, but we'll keep "
                     "you updated.")
    else:
        paras.append(NEXT_STEP.get(type_id, "We've passed this on to the right person in our "
                                            "team and will be in touch."))
    if flags:
        paras.append("If you need support in the meantime:\n"
                     + "\n".join(f"• {r}" for r in _referrals(flags)))
    paras.append("If anything changes, just reply to this email or give us a call.")
    email = "\n\n".join([f"Hi {NAME_TOKEN},"] + paras + [_signature()])
    sms = f"Hi {NAME_TOKEN}, thanks for contacting our office about {topic}. We'll be in touch. - {settings.office_signoff}"
    subject = f"We've received {topic}"
    return {"subject": subject[0].upper() + subject[1:], "email": email, "sms": sms}


def resolution(type_id: str, data: dict[str, Any], tmpl: list[dict[str, Any]],
               flags: list[dict[str, Any]]) -> dict[str, str]:
    topic = topic_for(type_id, data)
    paras = [f"Thanks for chatting with our office today about {topic}. "
             "Here's the information we went through:"]
    for t in tmpl:
        paras.append(f"{t['title']}\n{t['body'].strip()}")
    if flags:
        paras.append("Support is also available:\n" + "\n".join(f"• {r}" for r in _referrals(flags)))
    paras.append("If you get stuck, just reply to this email or give us a call.")
    email = "\n\n".join([f"Hi {NAME_TOKEN},"] + paras + [_signature()])
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
        "Context (identifiers removed):\n" + extract.redact(notes, data)[:3000]
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


async def generate(type_id: str, data: dict[str, Any], notes: str,
                   tmpl: list[dict[str, Any]], polish_with_model: bool = True) -> dict[str, Any]:
    """Resolution email when approved guidance is selected, otherwise an acknowledgement."""
    flags = extract.safety_flags(notes)
    draft = resolution(type_id, data, tmpl, flags) if tmpl else acknowledgement(type_id, data, flags)
    engine = "template"
    if polish_with_model:
        polished = await polish(draft, notes, data)
        if polished:
            draft, engine = polished, "model"
    first = str(data.get("first_name") or "").strip()
    return {**_fill(draft, first), "engine": engine}
