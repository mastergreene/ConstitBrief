"""Live assistant analysis.

Input:  the officer's notes + the staff-controlled state (values entered or accepted,
        rejected proposals, staff-chosen enquiry types, dismissed questions, N/A items).
Output: suggestions only - enquiry types, team, proposed facts with evidence, checklist
        status, next questions, actions, deadlines, contradictions and readiness.

Staff state is authoritative: a value the officer entered or accepted is never replaced;
if the notes later disagree, a contradiction is raised instead. Rejected proposals and
dismissed questions are not re-suggested.
"""
from __future__ import annotations

import re
import time
from typing import Any

from . import extract, formmap, taxonomy

MAX_QUESTIONS = 5


def _filled(v: Any) -> bool:
    return v is not None and str(v).strip() != ""


# ------------------------------------------------------------------ classification --

def _kw_regex(kw: str) -> re.Pattern[str]:
    return re.compile(r"(?<![a-z])" + re.escape(kw.strip()) + r"(?![a-z])", re.I)


_KW = {t.id: [(kw, _kw_regex(kw)) for kw in t.keywords] for t in taxonomy.ENQUIRY_TYPES}


def classify(notes: str) -> list[dict[str, Any]]:
    """Rule-based multi-label classification with evidence. Sorted strongest first."""
    out = []
    for t in taxonomy.ENQUIRY_TYPES:
        hits = []
        for kw, rx in _KW[t.id]:
            m = rx.search(notes or "")
            if m:
                hits.append({"keyword": kw, "start": m.start(), "end": m.end(),
                             "text": notes[m.start():m.end()]})
        if not hits:
            continue
        score = sum((0.5 if h["keyword"] in taxonomy.WEAK_KEYWORDS else 1.0)
                    + 0.5 * h["keyword"].count(" ") for h in hits)
        out.append({"id": t.id, "score": score, "raw": score, "evidence": hits[:4],
                    "sources": ["rules"]})
    # Umbrella / catch-all types rank below a specific type when both match.
    demote = {"community_engagement": 0.6, "admin": 0.5, "other_casework": 0.6}
    for c in out:
        c["score"] *= demote.get(c["id"], 1.0)
    out.sort(key=lambda c: -c["score"])
    for c in out:
        c["confidence"] = round(min(0.95, 0.35 + 0.18 * c["score"]), 2)
        c["rationale"] = "Matched " + ", ".join(f"“{h['text']}”" for h in c["evidence"][:3])
    return out


def merge_model(types: list[dict[str, Any]], model: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not model:
        return types
    by_id = {t["id"]: t for t in types}
    for tid, p in (model.get("types") or {}).items():
        if tid not in taxonomy.TYPE_BY_ID:
            continue
        if tid in by_id:
            by_id[tid]["confidence"] = round(max(by_id[tid]["confidence"], min(0.95, p)), 2)
            by_id[tid]["sources"].append("model")
        elif p >= 0.6:
            types.append({"id": tid, "score": p, "raw": 1.0, "confidence": round(min(0.9, p), 2),
                          "evidence": [], "sources": ["model"],
                          "rationale": f"Suggested by the analysis model (p={p:.2f}); no keyword match"})
    types.sort(key=lambda c: -c["confidence"])
    return types


# ------------------------------------------------------------------------ checklist --

def _value_present(field_id: str, values: dict[str, Any], state: dict[str, Any]) -> bool:
    if field_id == "@outcome":
        return _filled((state.get("summary") or {}).get("outcome"))
    if field_id == "@details":
        return _filled((state.get("summary") or {}).get("issue"))
    if field_id == "@deadline":
        return bool(state.get("deadlines_accepted"))
    return _filled(values.get(field_id))


def build_checklist(type_ids: list[str], values: dict[str, Any], state: dict[str, Any],
                    pending_fields: set[str], conflict_fields: set[str],
                    model_cover: set[str]) -> list[dict[str, Any]]:
    na = set(state.get("not_applicable") or [])
    items: list[dict[str, Any]] = []
    seen_fields: set[tuple[str, ...]] = set()

    def add(key: str, label: str, fields: list[str], basis: str, type_id: str, question: str) -> None:
        sig = tuple(sorted(fields))
        if sig in seen_fields:
            return
        seen_fields.add(sig)
        if key in na:
            status = "not_applicable"
        elif fields and all(_value_present(f, values, state) for f in fields):
            status = "unclear" if set(fields) & conflict_fields else "collected"
        elif set(fields) & (pending_fields | conflict_fields) or key in model_cover:
            status = "unclear"
        else:
            status = "missing"
        items.append({"key": key, "label": label, "fields": fields, "basis": basis,
                      "type_id": type_id, "status": status, "question": question})

    for i, tid in enumerate(type_ids):
        t = taxonomy.TYPE_BY_ID[tid]
        if t.form_option:
            for r in formmap.required_record_fields(t.form_option):
                add(f"form:{r['qid']}", r["label"], r["fields"], "form_required", tid,
                    _form_question(r["label"], r["fields"]))
            if i == 0:  # optional form fields only for the primary handoff
                for r in formmap.optional_record_fields(t.form_option):
                    add(f"form:{r['qid']}:{','.join(r['fields'])}", r["label"], r["fields"],
                        "form_optional", tid, _form_question(r["label"], r["fields"]))
        for s in t.suggestions:
            add(f"{tid}:{s.key}", s.label, list(s.fields), "suggestion", tid, s.question)
    return items


_QUESTIONS = {
    ("first_name", "last_name"): "Can I confirm your first and last name?",
    ("address_line1", "state", "suburb"): "What's your home address, including suburb? "
                                          "(The office can only act for Moreton residents.)",
    ("phone",): "What's the best phone number to reach you on?",
    ("email",): "Do you have an email address we can use?",
    ("postcode",): "And the postcode?",
}


def _form_question(label: str, fields: list[str]) -> str:
    q = _QUESTIONS.get(tuple(sorted(fields)))
    if q:
        return q
    return f"Can you tell me the {label.rstrip('?').lower()}?" if not label.endswith("?") else label


# --------------------------------------------------------------------------- main --

def analyse(notes: str, state: dict[str, Any], model: dict[str, Any] | None = None) -> dict[str, Any]:
    t0 = time.perf_counter()
    state = state or {}
    values: dict[str, Any] = dict(state.get("values") or {})
    rejected: dict[str, list[str]] = state.get("rejected") or {}

    # Enquiry types: staff choice wins; otherwise suggestions.
    suggested = merge_model(classify(notes), model)
    rejected_types = set((state.get("types") or {}).get("rejected") or [])
    suggested = [s for s in suggested if s["id"] not in rejected_types]
    staff_types = [t for t in ((state.get("types") or {}).get("selected") or [])
                   if t in taxonomy.TYPE_BY_ID]
    active_types = staff_types or _active_from_suggestions(suggested)
    if not active_types:
        active_types = ["admin"]

    uncertain = False
    clarify = None
    if not staff_types:
        if not suggested or all(s.get("raw", 1.0) < 1.0 and "model" not in s["sources"]
                                for s in suggested):
            uncertain = True
            clarify = "What is the main thing they'd like the office to help with?"
        elif len(eligible := [s for s in suggested if s.get("raw", 1.0) >= 1.0
                              or "model" in s["sources"]]) > 1:
            a, b = eligible[0], eligible[1]
            ga, gb = taxonomy.TYPE_BY_ID[a["id"]].group, taxonomy.TYPE_BY_ID[b["id"]].group
            if ga != gb and b["confidence"] >= a["confidence"] - 0.1:
                uncertain = True
                clarify = (f"Is this mainly about {taxonomy.TYPE_BY_ID[a['id']].label.lower()} or "
                           f"{taxonomy.TYPE_BY_ID[b['id']].label.lower()}? (Both may need follow-up.)")

    # Proposed facts (identifiers) with evidence; staff values are authoritative.
    proposals, contradictions = [], []
    by_field: dict[str, list[dict[str, Any]]] = {}
    for f in extract.facts(notes):
        by_field.setdefault(f["field"], []).append(f)
    for fid, found in by_field.items():
        staff_v = values.get(fid)
        distinct = {f["value"] for f in found}
        if len(distinct) > 1:
            contradictions.append({
                "field": fid, "label": taxonomy.FIELD_BY_ID[fid].label,
                "message": f"Notes mention more than one {taxonomy.FIELD_BY_ID[fid].label}: "
                           + ", ".join(sorted(distinct)),
                "evidence": [f["evidence"] for f in found]})
        for f in found:
            if f["value"] in (rejected.get(fid) or []):
                continue
            if _filled(staff_v):
                if _norm(staff_v) != _norm(f["value"]):
                    contradictions.append({
                        "field": fid, "label": taxonomy.FIELD_BY_ID[fid].label,
                        "message": f"Notes say {f['value']} but the record has {staff_v}",
                        "evidence": [f["evidence"]]})
                continue
            if len(distinct) == 1:
                proposals.append({**f, "label": taxonomy.FIELD_BY_ID[fid].label})
    pending_fields = {p["field"] for p in proposals}
    conflict_fields = {c["field"] for c in contradictions}

    # Dates & deadlines.
    accepted_dl = {d.get("source") or d.get("text") for d in state.get("deadlines_accepted") or []}
    dismissed_dl = set(state.get("deadlines_dismissed") or [])
    dates = [d for d in extract.dates(notes)
             if d["text"] not in accepted_dl and d["text"] not in dismissed_dl]

    # Summary proposals (only offered while the officer hasn't written their own).
    summary = state.get("summary") or {}
    summary_proposal = {
        "issue": None if _filled(summary.get("issue")) else (extract.issue_proposal(notes) or None),
        "outcome": None if _filled(summary.get("outcome")) else extract.outcome_proposal(notes),
    }

    # Pseudo-fields mentioned in the notes but not yet confirmed by staff count as "unclear".
    if any(d["kind"] == "deadline" for d in dates):
        pending_fields.add("@deadline")
    if summary_proposal["outcome"]:
        pending_fields.add("@outcome")
    if summary_proposal["issue"]:
        pending_fields.add("@details")
    model_cover = set((model or {}).get("covered") or [])
    checklist = build_checklist(active_types, values, state, pending_fields, conflict_fields,
                                model_cover)

    # Next questions.
    dismissed_q = set(state.get("dismissed_questions") or [])
    questions: list[dict[str, Any]] = []

    def q(key: str, text: str, reason: str, basis: str) -> None:
        if key not in dismissed_q and all(x["key"] != key for x in questions):
            questions.append({"key": key, "text": text, "reason": reason, "basis": basis})

    for c in contradictions:
        q(f"conflict:{c['field']}", f"Can you confirm the {c['label']}?", c["message"], "contradiction")
    for d in dates:
        if d["kind"] == "deadline":
            q(f"deadline:{d['text']}", f"Confirm the deadline (“{d['text']}”): exact date and time?",
              "A deadline was mentioned", "deadline")
    for it in checklist:
        if it["status"] == "unclear" and it["basis"] == "form_required":
            q(it["key"], f"Confirm: {it['question']}", "Mentioned in notes but not confirmed", it["basis"])
    if clarify:
        q("clarify:type", clarify, "Enquiry type is uncertain", "clarification")
    for basis in ("form_required", "suggestion", "form_optional"):
        for it in checklist:
            if it["status"] == "missing" and it["basis"] == basis and it["type_id"] == active_types[0]:
                q(it["key"], it["question"], _reason(it), basis)
    for it in checklist:
        if it["status"] == "missing" and it["basis"] != "form_optional":
            q(it["key"], it["question"], _reason(it), it["basis"])
    questions = questions[:MAX_QUESTIONS]

    # Actions (suggested; staff approve).
    dismissed_a = set(state.get("dismissed_actions") or [])
    actions = []
    for tid in active_types:
        for a in taxonomy.TYPE_BY_ID[tid].actions:
            key = f"{tid}:{a}"
            if key not in dismissed_a:
                actions.append({"key": key, "text": a, "type_id": tid})
    if len(active_types) > 1:
        actions.append({"key": "multi:handoffs", "type_id": active_types[0],
                        "text": "More than one type of work: decide whether each needs its own "
                                "handoff (nothing is submitted automatically)"})

    # Readiness per proposed handoff.
    team = taxonomy.suggested_team(active_types)
    handoffs, seen_opts = [], set()
    for tid in active_types:
        t = taxonomy.TYPE_BY_ID[tid]
        if not t.form_option or t.form_option in seen_opts:
            continue
        seen_opts.add(t.form_option)
        req = [i for i in checklist if i["basis"] == "form_required"
               and (i["type_id"] == tid or i["key"] in {"form:4", "form:132"})]
        missing = [i["label"] for i in req if i["status"] != "collected"]
        optional = [i["label"] for i in checklist if i["type_id"] == tid
                    and i["basis"] != "form_required" and i["status"] in ("missing", "unclear")]
        handoffs.append({"type_id": tid, "form_option": t.form_option,
                         "form_option_basis": t.form_option_basis,
                         "mandatory_missing": missing, "optional_missing": optional,
                         "ready": not missing})

    return {
        "enquiry_types": [{**s, "label": taxonomy.TYPE_BY_ID[s["id"]].label} for s in suggested[:5]],
        "active_types": active_types,
        "types_source": "staff" if staff_types else "suggested",
        "uncertain": uncertain,
        "team": team,
        "proposals": proposals,
        "contradictions": contradictions,
        "dates": dates,
        "summary_proposal": summary_proposal,
        "checklist": checklist,
        "questions": questions,
        "actions": actions,
        "handoffs": handoffs,
        "ready": bool(handoffs) and handoffs[0]["ready"],
        "safety_flags": extract.safety_flags(notes),
        "tfn_warning": extract.contains_tfn(notes),
        "engine": "rules+model" if model else "rules",
        "timing_ms": round((time.perf_counter() - t0) * 1000, 1),
    }


UMBRELLA = {"community_engagement": "community", "admin": "admin", "other_casework": "casework"}


def _active_from_suggestions(suggested: list[dict[str, Any]]) -> list[str]:
    """Top suggestions, minus catch-all types when a specific type of the same group exists."""
    ids = [s["id"] for s in suggested if s.get("raw", 1.0) >= 1.0 or "model" in s["sources"]]
    groups = {taxonomy.TYPE_BY_ID[i].group for i in ids if i not in UMBRELLA}
    keep = [i for i in ids if not (i in UMBRELLA and taxonomy.TYPE_BY_ID[i].group in groups)]
    return keep[:3]


def _norm(v: Any) -> str:
    return re.sub(r"[\s-]", "", str(v)).upper()


def _reason(item: dict[str, Any]) -> str:
    return {"form_required": "Required by the Jotform",
            "form_optional": "Asked on the Jotform (optional)",
            "suggestion": "Suggested prompt (not an office-verified requirement)"}[item["basis"]]
