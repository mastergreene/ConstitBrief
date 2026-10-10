"""Capture a structural snapshot of the public Jotform so the field mapping can be verified.

    python scripts/snapshot_jotform.py                 # fetch live form, write snapshot
    python scripts/snapshot_jotform.py --check         # fetch live form, diff against committed snapshot
    python scripts/snapshot_jotform.py --html file.html  # parse a saved copy instead of fetching

The snapshot records what the PUBLIC form exposes: field ids, sub-input names, labels,
types, options, required flags, section membership and show/hide conditions. It cannot
see notification (email routing) settings - those need authorised Jotform access.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

FORM_ID = "252413844700855"
ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "backend" / "app" / "mapping" / f"form_{FORM_ID}.snapshot.json"


def _text(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def parse(src: str) -> dict:
    fields: list[dict] = []
    sections: dict[str, list[str]] = {}
    current_section = None
    tags = list(re.finditer(r'<(li|ul)\b([^>]*?)\bid="(id_|section_)(\d+)"([^>]*)>', src))
    for i, m in enumerate(tags):
        _, pre, kind, qid, post = m.groups()
        attrs = pre + post
        if kind == "section_":
            current_section = qid
            sections[qid] = []
            continue
        end = tags[i + 1].start() if i + 1 < len(tags) else len(src)
        blk = src[m.end():end]
        ftype = (re.search(r'data-type="([^"]+)"', attrs) or [None, ""])[1]
        cls = (re.search(r'class="([^"]+)"', attrs) or [None, ""])[1]
        label_m = re.search(r'id="label_%s"[^>]*>(.*?)</label>' % qid, blk, re.S)
        inputs = []
        for im in re.finditer(r"<(input|textarea|select)\b([^>]*)>", blk):
            a = im.group(2)
            name = re.search(r'name="([^"]+)"', a)
            if not name or not name.group(1).startswith(f"q{qid}_"):
                continue
            icls = (re.search(r'class="([^"]+)"', a) or [None, ""])[1]
            sub = re.search(r"\[([a-z_0-9]+)\]$", name.group(1))
            entry = {
                "name": name.group(1),
                "sub": sub.group(1) if sub else None,
                "required": "validate[required" in icls,
            }
            if entry not in inputs:
                inputs.append(entry)
        options = [html.unescape(o) for o in re.findall(r'<option value="([^"]+)"', blk)]
        if not options:
            options = [html.unescape(o) for o in
                       re.findall(r'type="(?:radio|checkbox)"[^>]*?value="([^"]*)"', blk)]
        if ftype == "control_button":
            continue
        field = {
            "qid": qid,
            "type": ftype,
            "label": _text(label_m.group(1)).rstrip(" *") if label_m else "",
            "required": "jf-required" in cls,
            "section": current_section,
            "inputs": inputs,
            "options": list(dict.fromkeys(options)),
        }
        if ftype == "control_text":
            field["text"] = _text(blk)[:600]
        fields.append(field)
        if current_section:
            sections[current_section].append(qid)

    conditions = []
    cm = re.search(r"JotForm\.setConditions\((\[.*?\])\);", src, re.S)
    if cm:
        for c in json.loads(cm.group(1)):
            conditions.append({
                "terms": [{"field": t.get("field"), "operator": t.get("operator"),
                           "value": t.get("value")} for t in c.get("terms", [])],
                "actions": [{"visibility": a.get("visibility"), "field": a.get("field")}
                            for a in c.get("action", [])],
            })
    # Sections before any section marker are "always shown" (common fields).
    return {"fields": fields, "sections": sections, "conditions": conditions}


def fetch() -> str:
    req = urllib.request.Request(f"https://form.jotform.com/{FORM_ID}",
                                 headers={"User-Agent": "ConstitBrief-form-snapshot"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def build(src: str) -> dict:
    parsed = parse(src)
    return {
        "form_id": FORM_ID,
        "form_title": "Web OfficeOne",
        "source": f"https://form.jotform.com/{FORM_ID} (public form HTML)",
        "captured_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "structure_sha256": hashlib.sha256(
            json.dumps(parsed, sort_keys=True).encode()).hexdigest(),
        "notification_routing": "NOT VISIBLE in public form - requires authorised Jotform access",
        **parsed,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", help="parse a saved HTML file instead of fetching")
    ap.add_argument("--check", action="store_true", help="diff live form against snapshot")
    args = ap.parse_args()
    src = Path(args.html).read_text(encoding="utf-8") if args.html else fetch()
    snap = build(src)
    if args.check:
        old = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        if old["structure_sha256"] == snap["structure_sha256"]:
            print("Form structure unchanged since", old["captured_at"])
            return 0
        print("FORM STRUCTURE CHANGED - review mapping before relying on handoff.")
        old_f = {f["qid"]: f for f in old["fields"]}
        new_f = {f["qid"]: f for f in snap["fields"]}
        for q in sorted(set(old_f) | set(new_f), key=int):
            if old_f.get(q) != new_f.get(q):
                print(f"  q{q}: {json.dumps(old_f.get(q))[:160]}\n     -> {json.dumps(new_f.get(q))[:160]}")
        if old["conditions"] != snap["conditions"]:
            print("  conditions changed")
        return 1
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {SNAPSHOT} ({len(snap['fields'])} fields, {len(snap['conditions'])} conditions)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
