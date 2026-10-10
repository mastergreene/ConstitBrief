"""Jotform adapter: verified field mapping, deterministic validation, handoff rows.

The mapping (mapping/*.mapping.json) is hand-authored and versioned; the snapshot
(mapping/*.snapshot.json) is generated from the live public form by
scripts/snapshot_jotform.py. `check_consistency()` runs at import time, so a mapping that
references a field, sub-input or option that isn't on the form fails loudly.

URL policy: only the enquiry-type option (and, if the office opts in, contact details)
may ever be put into a Jotform URL. Case notes, descriptions and identifiers never are.
"""
from __future__ import annotations

import json
import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from ..config import settings
from . import taxonomy

MAPPING_DIR = Path(__file__).resolve().parents[1] / "mapping"
FORM_ID = "252413844700855"

# Record fields that may appear in a URL when JOTFORM_PREFILL_CONTACT=true.
CONTACT_PREFILL_QIDS = {"4", "120", "5", "132"}


class MappingError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def mapping() -> dict[str, Any]:
    return json.loads((MAPPING_DIR / f"jotform_{FORM_ID}.mapping.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def snapshot() -> dict[str, Any]:
    return json.loads((MAPPING_DIR / f"form_{FORM_ID}.snapshot.json").read_text(encoding="utf-8"))


def _snap_fields() -> dict[str, dict[str, Any]]:
    return {f["qid"]: f for f in snapshot()["fields"]}


def form_options() -> list[str]:
    return list(_snap_fields()[mapping()["type_field"]["qid"]]["options"])


def check_consistency() -> list[str]:
    """Return problems between mapping, snapshot and taxonomy (empty list = consistent)."""
    problems: list[str] = []
    snap = _snap_fields()
    m = mapping()
    options = set(form_options())

    def check_entry(entry: dict[str, Any], section: str | None) -> None:
        qid = entry["qid"]
        f = snap.get(qid)
        if not f:
            problems.append(f"q{qid} not on form")
            return
        if f["section"] != section:
            problems.append(f"q{qid} is in section {f['section']}, mapping says {section}")
        rec = entry.get("record")
        if isinstance(rec, dict):
            subs = {i["sub"] for i in f["inputs"]}
            for sub, rid in rec.items():
                if sub not in subs:
                    problems.append(f"q{qid} has no sub-input [{sub}]")
                if rid not in taxonomy.FIELD_BY_ID:
                    problems.append(f"q{qid}[{sub}] maps to unknown record field {rid}")
        elif isinstance(rec, str) and rec not in taxonomy.FIELD_BY_ID:
            problems.append(f"q{qid} maps to unknown record field {rec}")
        if entry["transform"] == "choice":
            rf = taxonomy.FIELD_BY_ID.get(rec) if isinstance(rec, str) else None
            if rf and rf.options and not set(rf.options) <= set(f["options"]):
                problems.append(f"q{qid} options {f['options']} don't cover {rf.options}")

    for e in m["common"]:
        check_entry(e, None)
    for option, branch in m["branches"].items():
        if option not in options:
            problems.append(f"branch '{option}' is not a form option")
        for e in branch["fields"]:
            check_entry(e, branch["section"])
        shown = {a["field"] for c in snapshot()["conditions"] for a in c["actions"]
                 if any(t["value"] == option for t in c["terms"])}
        if branch["section"] not in shown:
            problems.append(f"no condition shows section {branch['section']} for '{option}'")
    for t in taxonomy.ENQUIRY_TYPES:
        if t.form_option and t.form_option not in options:
            problems.append(f"enquiry type {t.id} uses unknown form option '{t.form_option}'")
    return problems


_problems = check_consistency()
if _problems:  # pragma: no cover - guarded by tests
    raise MappingError("Jotform mapping is inconsistent with the snapshot: " + "; ".join(_problems))


# ------------------------------------------------------------------------ values --

def _filled(v: Any) -> bool:
    return v is not None and str(v).strip() != ""


def _fmt_date_text(iso: str) -> str:
    try:
        return date.fromisoformat(iso).strftime("%d/%m/%Y")
    except ValueError:
        return iso


def _date_parts(iso: str) -> dict[str, str] | None:
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        return None
    return {"month": f"{d.month:02d}", "day": f"{d.day:02d}", "year": str(d.year)}


SUB_LABELS = {"first": "First name", "last": "Last name", "addr_line1": "Street address",
              "addr_line2": "Street address line 2", "city": "City / suburb",
              "state": "State", "postal": "Postcode", "month": "Month", "day": "Day",
              "year": "Year"}


def _entries(option: str) -> list[tuple[dict[str, Any], str | None]]:
    m = mapping()
    out = [(e, None) for e in m["common"]]
    branch = m["branches"].get(option)
    if branch:
        out += [(e, branch["section"]) for e in branch["fields"]]
    return out


def _label(entry: dict[str, Any]) -> str:
    return entry.get("label_override") or _snap_fields()[entry["qid"]]["label"]


def _required_subs(qid: str) -> set[str | None]:
    f = _snap_fields()[qid]
    return {i["sub"] for i in f["inputs"] if i["required"]}


def compose_description(option: str, values: dict[str, Any], summary: dict[str, str],
                        extras: list[tuple[str, str]], ref: str) -> str:
    """Free-text field content: summary, requested outcome, details with no form field, ref."""
    parts = []
    if summary.get("issue"):
        parts.append(summary["issue"].strip())
    if summary.get("outcome"):
        parts.append(f"Requested outcome: {summary['outcome'].strip()}")
    if extras:
        parts.append("Other details:\n" + "\n".join(f"- {k}: {v}" for k, v in extras))
    parts.append(f"ConstitBrief ref: {ref}")
    return "\n\n".join(parts)


def mapped_record_fields(option: str) -> set[str]:
    out: set[str] = set()
    for e, _ in _entries(option):
        rec = e.get("record")
        if isinstance(rec, dict):
            out |= set(rec.values())
        elif isinstance(rec, str):
            out.add(rec)
    return out


def build(option: str, values: dict[str, Any], summary: dict[str, str], ref: str,
          extra_lines: list[tuple[str, str]] | None = None) -> dict[str, Any]:
    """Field-by-field handoff rows in form order, plus validation."""
    if option not in form_options():
        raise MappingError(f"'{option}' is not an option on the form")
    mapped = mapped_record_fields(option)
    extras: list[tuple[str, str]] = []
    for f in taxonomy.RECORD_FIELDS:
        v = values.get(f.id)
        if _filled(v) and f.id not in mapped and f.id not in ("consent_status",):
            extras.append((f.label, _fmt_date_text(v) if f.type == "date" else str(v).strip()))
    extras += extra_lines or []
    description = compose_description(option, values, summary, extras, ref)

    rows: list[dict[str, Any]] = [{
        "qid": mapping()["type_field"]["qid"], "sub": None, "label": mapping()["type_field"]["label"],
        "value": option, "required": False, "kind": "choice", "section": None,
    }]
    has_description = False
    for entry, section in _entries(option):
        qid, t = entry["qid"], entry["transform"]
        label = _label(entry)
        req_subs = _required_subs(qid)
        if t in ("fullname", "address"):
            for sub, rid in entry["record"].items():
                v = values.get(rid)
                if sub == "state" and not _filled(v) and any(
                        _filled(values.get(r)) for r in entry["record"].values()):
                    v = "QLD"
                rows.append({"qid": qid, "sub": sub, "label": f"{label}: {SUB_LABELS[sub]}",
                             "value": str(v).strip() if _filled(v) else "", "required": sub in req_subs,
                             "kind": "text", "section": section, "record_field": rid})
        elif t == "date_mdy":
            parts = _date_parts(str(values.get(entry["record"]) or ""))
            rows.append({"qid": qid, "sub": None, "label": label,
                         "value": f"{parts['day']}/{parts['month']}/{parts['year']}" if parts else "",
                         "parts": parts, "required": bool(req_subs), "kind": "date",
                         "section": section, "record_field": entry["record"]})
        elif t == "date_text":
            v = values.get(entry["record"])
            rows.append({"qid": qid, "sub": None, "label": label,
                         "value": _fmt_date_text(str(v)) if _filled(v) else "",
                         "required": bool(req_subs), "kind": "text", "section": section,
                         "record_field": entry["record"]})
        elif t == "description":
            has_description = True
            rows.append({"qid": qid, "sub": None, "label": label, "value": description,
                         "required": bool(req_subs), "kind": "textarea", "section": section})
        elif t == "upload":
            rows.append({"qid": qid, "sub": None, "label": label, "value": "",
                         "required": bool(req_subs), "kind": "upload", "section": section,
                         "note": entry.get("note", "Attach in Jotform")})
        else:  # text / choice
            v = values.get(entry["record"])
            if t == "choice" and _filled(v) and v not in _snap_fields()[qid]["options"]:
                v = ""  # never send a value the form would reject
            rows.append({"qid": qid, "sub": None, "label": label,
                         "value": str(v).strip() if _filled(v) else "", "required": bool(req_subs),
                         "kind": t, "section": section, "record_field": entry["record"]})

    errors = [f"{r['label']} is required by the form" for r in rows
              if r["required"] and r["kind"] != "upload" and not r["value"]]
    email = values.get("email")
    if _filled(email) and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", str(email).strip()):
        errors.append("Email address doesn't look valid (the form checks email format)")
    warnings = []
    if not has_description:
        warnings.append("This form option has no free-text field: the summary, requested outcome "
                        "and other details below can't be included in the submission and the "
                        "handoff reference can't be recorded.")
    uploads = [r["label"] for r in rows if r["kind"] == "upload"]
    if uploads:
        warnings.append("Attach files in Jotform if needed: " + "; ".join(uploads))
    return {
        "form_option": option,
        "rows": rows,
        "description": description if has_description else "",
        "unplaced_details": [] if has_description else (
            ([("Summary", summary["issue"])] if summary.get("issue") else [])
            + ([("Requested outcome", summary["outcome"])] if summary.get("outcome") else [])
            + extras),
        "errors": errors,
        "warnings": warnings,
        "valid": not errors,
        "mapping_version": mapping()["mapping_version"],
    }


def required_record_fields(option: str) -> list[dict[str, Any]]:
    """Form-required items for an option as checklist entries (record field ids)."""
    out = []
    for entry, _ in _entries(option):
        subs = _required_subs(entry["qid"])
        if not subs:
            continue
        rec = entry.get("record")
        fields = [rec[s] for s in subs if isinstance(rec, dict) and s in rec] if isinstance(rec, dict) \
            else ([rec] if isinstance(rec, str) else [])
        out.append({"qid": entry["qid"], "label": _label(entry), "fields": fields})
    return out


def optional_record_fields(option: str) -> list[dict[str, Any]]:
    out = []
    for entry, section in _entries(option):
        rec = entry.get("record")
        if entry["transform"] in ("description", "upload") or rec is None:
            continue
        req = _required_subs(entry["qid"])
        if isinstance(rec, dict):
            for sub, rid in rec.items():
                if sub in req or sub in ("addr_line2", "state"):
                    continue
                label = f"{_label(entry)}: {SUB_LABELS[sub]}" if req else _label(entry)
                out.append({"qid": entry["qid"], "label": label, "fields": [rid], "section": section})
        elif not req:
            out.append({"qid": entry["qid"], "label": _label(entry), "fields": [rec],
                        "section": section})
    # Merge sub-fields of the same optional compound field (e.g. a whole optional address).
    merged: dict[str, dict[str, Any]] = {}
    for o in out:
        key = f"{o['qid']}|{o['label']}"
        if key in merged:
            merged[key]["fields"] += o["fields"]
        else:
            merged[key] = dict(o)
    return list(merged.values())


def safe_url(option: str, values: dict[str, Any]) -> str:
    """Form URL carrying only the enquiry option (and contact details if the office opted in)."""
    params: dict[str, str] = {}
    if settings.jotform_prefill_type:
        params["typeA"] = option
    if settings.jotform_prefill_contact:
        rows = build(option, values, {}, "x")["rows"]
        for r in rows:
            if r["qid"] in CONTACT_PREFILL_QIDS and r["value"] and r["qid"] != "9":
                key = {"4": "name", "120": "phoneNumber120", "5": "email", "132": "address132"}[r["qid"]]
                params[f"{key}[{r['sub']}]" if r["sub"] else key] = r["value"]
    base = f"https://form.jotform.com/{settings.jotform_form_id}"
    return f"{base}?{urlencode(params)}" if params else base


def summary_for_docs() -> dict[str, Any]:
    m = mapping()
    return {
        "mapping_version": m["mapping_version"],
        "form_id": m["form_id"],
        "form_url": m["form_url"],
        "snapshot_captured_at": snapshot()["captured_at"],
        "verification": m["verification"],
        "options": form_options(),
        "known_form_issues": m["known_form_issues"],
    }
