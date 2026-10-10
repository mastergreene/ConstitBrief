# ConstitBrief

ConstitBrief is a live intake assistant for the Moreton electorate office. Staff and MPs type notes during a conversation. Without anyone having to send a chat message, the assistant then:
* identifies the work involved
* suggests a responsible team
* lists the next questions to ask
* tracks what's still missing
* prepares a reviewed handoff into the office's existing Jotform

The AI suggests and staff decide. Nothing is submitted automatically.

Documentation:
* `docs/PRODUCT_BRIEF.md`: requirements baseline (v1.0)
* `docs/GAP_ASSESSMENT.md`: repo vs brief, before and after
* `docs/JOTFORM_MAPPING.md`: verified field mapping (generated)
* `docs/DECISIONS.md`: unresolved configuration decisions
* `docs/TEST_EVIDENCE.md`: acceptance scenarios, latency, routing test procedure

## Pilot readiness

**Ready for a supervised pilot (synthetic data first, then real conversations):**
* Live notes → assistant: work types with evidence, team suggestion, next questions, checklist, readiness, dates and deadlines, contradictions, editable summary, follow-up actions.
* Staff edits are authoritative. Suggestions from the notes must be accepted, and names, consent, eligibility and deadlines are never inferred.
* Reviewed handoff into Jotform form `252413844700855`:
  * The field mapping has been checked against the live form.
  * Mandatory form fields block the handoff.
  * Duplicates are prevented.
  * "Opened" is clearly separated from "submitted" and "confirmed".
* Sign-in per user, short-lived server drafts, explicit "Finish & clear", no sensitive data in URLs, and no case data in browser storage beyond the current tab.
* Works with no AI provider at all (the default).

**Blocked or unverified. Don't claim these are complete:**
* **Email routing.** The five Jotform notification destinations and their conditions are not visible publicly (D1). ConstitBrief doesn't touch routing, because every submission goes through the real form. However, which team each option reaches hasn't been verified. Run the synthetic routing procedure in `docs/TEST_EVIDENCE.md` once the office provides access.
* **Ownership.** Team ownership for grants, events and other community requests is *proposed*. Parliamentary, ministerial and volunteer work is *staff to decide* (D3).
* **Checklists and consent.** Office checklists and consent practice haven't been supplied (D4, D5). All non-form prompts are labelled as suggestions and never block.
* **Guidance library.** The 19 seed entries are unreviewed and are **not shown to staff** until an admin approves each one.
* **AI provider.** Jev on OpenRouter is implemented and tested against the documented API, but it's off until the office approves the data flow (D6). Its latency hasn't been measured.

## How it works

```
Notes (staff) ──► /api/analyse ──► rules engine (always) ──► suggestions only
                      │                └─ optional Jev (OpenRouter), redacted notes, validated answers
Staff record (authoritative) ──► deterministic validation against the verified Jotform mapping
                      │
Review & hand off ──► field-by-field copy + form link (enquiry option only)
                      └─► staff submit in the real Jotform ──► Jotform's existing email routing
                           status: prepared → opened (not confirmed) → reported → confirmed*
* confirmed = reference found through an optional read-only Jotform API key
```

* **Why not submit server-side?** Jotform support states that API-created submissions don't trigger the form's email notifications. That would bypass the office's routing, and the brief rules out building a parallel email sender.
* **Mapping is verified, not typed in.** `scripts/snapshot_jotform.py` captures the live form's structure. The versioned mapping (`backend/app/mapping/*.mapping.json`) is checked against that snapshot when the app starts and in tests. `--check` reports form drift.
* **Three sources of requirements, kept apart.** These are form-required (can block), form-optional, and suggested prompts (never block). See `backend/app/services/taxonomy.py`.

```
backend/app/
  main.py, config.py, db.py, auth.py, security.py, manage.py, schemas.py
  routers/api.py
  mapping/        form snapshot + versioned field mapping
  services/
    taxonomy.py   enquiry types, teams, record fields, suggested prompts
    extract.py    identifier/date/outcome proposals with evidence, safety flags, redaction
    analysis.py   live assistant (staff state in, suggestions out)
    jev.py        optional TypeSafe Jev provider (Decisions API)
    formmap.py    mapping, validation, handoff rows, URL policy
    handoff.py    handoff state machine, duplicate guard, read-only verification
    templates.py, search.py, drafts.py   approved guidance, gov search, acknowledgement drafts
frontend/          vanilla JS app, no build step (index.html, css/app.css, js/app.js, js/api.js)
scripts/           snapshot_jotform.py, render_mapping_doc.py, make_icons.py, run.sh
tests/e2e/         browser acceptance scenarios (Playwright)
```

## Setup

```bash
cp .env.example .env              # defaults are conservative; see docs/DECISIONS.md
pip install -r requirements.txt   # or ./scripts/run.sh, which creates .venv and starts the server
python -m backend.app.manage add-user jsmith "Jo Smith" --role admin   # prompts for a password
python -m backend.app.manage add-user mp "Julie-Ann Campbell" --role mp
python -m backend.app.main        # http://127.0.0.1:8787
```

Roles:
* **staff:** intake and handoff.
* **mp:** the same as staff.
* **admin:** can also approve guidance library entries.

Other management commands are `list-users`, `set-password` (this ends the user's sessions), `deactivate` and `check-mapping`.

**Local development over plain HTTP:** set `COOKIE_SECURE=false`, or the session cookie won't be sent.

### Expose to staff (Tailscale recommended)

Keep `HOST=127.0.0.1`, enable MagicDNS and HTTPS certificates for the tailnet, then run:

```bash
tailscale serve --bg 8787        # https://<machine>.<tailnet>.ts.net (tailnet devices only)
```

Don't use `tailscale funnel`, because that makes the app public. Docker: `docker build -t constitbrief . && docker run -p 127.0.0.1:8787:8787 -v cb-data:/data --env-file .env constitbrief`.

## Data handling

* **Server drafts.** Notes and the staff record are held in a server draft that expires after `DRAFT_RETENTION_HOURS` (default 72). "Finish & clear" wipes it immediately. The handoff log keeps only references and status, with no notes or field values.
* **Browser.** The browser keeps the current draft in `sessionStorage` (this tab only) for crash recovery. The service worker caches the app shell, never API responses.
* **Data sent to an AI provider.** With an AI provider enabled, only redacted notes are sent. Identifiers, phone, email, dates, TFNs and any personal value already typed into the record are removed first. Names that appear *only* in free text can't be reliably detected.
* **Jotform URL.** The form link carries the enquiry option only. Contact prefill is a separate opt-in (D9).
* **TFNs.** TFNs trigger a warning and are stripped from handoff text.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest backend/tests                         # 60 tests
COOKIE_SECURE=false python -m backend.app.main &       # then, with a test user created:
BASE_URL=http://127.0.0.1:8787 USER_NAME=<user> PASS=<password> node tests/e2e/acceptance.mjs
python scripts/snapshot_jotform.py --check             # has the live form changed?
python scripts/render_mapping_doc.py                   # regenerate docs/JOTFORM_MAPPING.md
```
