"""Combine deterministic rules with the Jev decision gate into one triage result."""
from __future__ import annotations

import re
from typing import Any

from . import jev, rules, templates

URGENCY_LABELS = ("routine", "time_sensitive", "urgent")


async def triage(notes: str, category: str | None, data: dict[str, Any]) -> dict[str, Any]:
    notes = notes or ""
    data = dict(data or {})

    # 1. Extract identifiers from the notes (never overwrite what the caseworker typed).
    extracted = {
        k: v for k, v in rules.extract_fields(notes).items() if not rules._filled(data.get(k))
    }
    merged = {**data, **{k: (v == "true" if k == "consent_signed" else v)
                         for k, v in extracted.items()}}

    # 2. Rule-based classification.
    heur = rules.classify(notes)
    flags = rules.safety_flags(notes)

    # 3. Requirements (evaluated against a provisional category so Jev can be asked
    #    about the right open items in the same round-trip).
    provisional = category if category in rules.CATEGORY_BY_ID else heur["category"]
    reqs = rules.evaluate_requirements(provisional, merged)
    open_reqs = [r for r in reqs if not r["met"]]

    decision = await jev.decide(notes, category, merged, open_reqs)

    # 4. Final category: the caseworker's explicit choice always wins.
    if category in rules.CATEGORY_BY_ID:
        final_cat, source, conf = category, "selected", 1.0
    elif decision and decision.get("category") and decision.get("category_confidence", 0) >= 0.4:
        final_cat, source, conf = decision["category"], "jev", decision["category_confidence"]
    else:
        final_cat, source, conf = heur["category"], "rules", heur["confidence"]

    if final_cat != provisional:
        reqs = rules.evaluate_requirements(final_cat, merged)

    covered = set((decision or {}).get("notes_cover", []))
    for r in reqs:
        if not r["met"] and r["key"] in covered:
            r["maybe_in_notes"] = True

    # 5. Escalation & urgency.
    esc = (decision or {}).get("needs_representation")
    if esc is None:
        esc = rules.escalation_score(notes)
    if final_cat == "flags_messages":
        esc = min(esc, 0.2)  # standard requests, never formal representations

    urg = (decision or {}).get("urgency")
    if urg is None:
        urg = 0.5 if esc >= 0.6 else 0.0
    if flags:
        urg = 1.0
    urgency = URGENCY_LABELS[min(2, int(round(urg * 2)))]

    missing = [r for r in reqs if not r["met"]]
    met = len(reqs) - len(missing)
    blocking = [r for r in missing if r["priority"] == 1]

    return {
        "engine": "jev+rules" if decision else "rules",
        "jev": decision,
        "category": final_cat,
        "category_label": rules.CATEGORY_BY_ID[final_cat].label,
        "category_source": source,
        "category_confidence": round(conf, 2),
        "mode": "escalate" if esc >= 0.5 else "resolve",
        "escalation_probability": round(esc, 2),
        "urgency": urgency,
        "safety_flags": flags,
        "extracted": extracted,
        "requirements": reqs,
        "missing": missing,
        "completeness": round(met / len(reqs), 2) if reqs else 1.0,
        "ready_to_lodge": not blocking,
        "tfn_warning": rules.contains_tfn(notes),
        "suggested_templates": templates.suggest(notes, final_cat),
        "search_query": suggested_query(notes, merged),
    }


_FILLER = frozenset(
    "constituent caller wants says said called rang phoned rung ago years months weeks days "
    "today yesterday told asked mum dad wife husband son daughter partner's".split()
)


def _vocabulary() -> frozenset[str]:
    words: set[str] = set()
    for c in rules.CATEGORIES:
        for kw in c.keywords:
            words.update(kw.split())
    return frozenset(words)


_VOCAB = _vocabulary()


def suggested_query(notes: str, data: dict[str, Any] | None = None, max_terms: int = 8) -> str:
    """A short keyword query built from the notes, safe to send to a search provider.

    Identifiers are redacted, and capitalised words that aren't known policy vocabulary are
    dropped, since in casework notes those are usually people's names or street names.
    """
    data = data or {}
    personal = {str(data.get(k) or "").strip().lower()
                for k in ("first_name", "last_name", "suburb", "address_line1")}
    text = re.sub(r"\[[A-Z_ ]+\]", " ", rules.redact_pii(notes, data))
    seen: list[str] = []
    for raw in re.findall(r"[A-Za-z][A-Za-z'-]+", text):
        w = raw.lower()
        if (w in templates._STOP or w in _FILLER or len(w) < 3 or w in personal or w in seen):
            continue
        if raw[0].isupper() and w not in _VOCAB:
            continue
        seen.append(w)
    return " ".join(seen[:max_terms])
