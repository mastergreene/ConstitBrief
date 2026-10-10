# Moreton Casework Fast-Resolver

A mobile-first Progressive Web App for the Moreton electorate office. Caseworkers, staff and volunteers use it on the phone, at mobile offices or on the road.

* **Mode A: Resolve.** Type or dictate the call notes and tap **Triage**. The app shows matching standard advice, safety referrals when it detects risk words, and a live search scoped to official government sites. Copy the SMS or email and send it while the caller is still on the line.
* **Mode B: Escalate.** When representations are needed, the **Ask Them Now** card lists every mandatory detail that is still missing, with a script for asking each one. Identifiers found in the notes (CRN, TRN, NDIS number and so on) can be filled in with one tap. **Open in Jotform** then opens the Web OfficeOne form fully prefilled. The app also writes an acknowledgement signed "Team Moreton".

---

## Architecture

```
PWA (vanilla JS, no build step) ──HTTPS──> FastAPI (Python) ──> SQLite
  offline shell (service worker)               ├─ /api/triage    rules + Jev decision gate ──> OpenRouter Decisions API
  local autosave of the open call              ├─ /api/search    Brave / Google CSE, allow-listed gov domains
  offline checklist + Jotform link             ├─ /api/templates standard-response library (CRUD)
                                               ├─ /api/generate  template drafts (+ optional model polish via OpenRouter)
                                               ├─ /api/jotform   prefill URL builder
                                               └─ /api/cases     recent calls (auto-purged)
```

```
.
├── backend/
│   ├── app/
│   │   ├── main.py            FastAPI app; serves API and PWA
│   │   ├── config.py          env / .env settings
│   │   ├── db.py              SQLite schema, seeding, retention purge
│   │   ├── security.py        access-code middleware, CSP & security headers
│   │   ├── schemas.py         request models
│   │   ├── routers/api.py     all /api routes
│   │   └── services/
│   │       ├── rules.py       categories, form fields, mandatory fields, extraction, safety flags
│   │       ├── jev.py         TypeSafe Jev client (POST /api/alpha/decisions)
│   │       ├── triage.py      combines rules + Jev into one result
│   │       ├── search.py      scoped gov search, cache, contact directory
│   │       ├── templates.py   library storage + matching
│   │       ├── drafts.py      "Team Moreton" drafts
│   │       └── jotform.py     Jotform prefill builder
│   ├── seed/
│   │   ├── build_seed.py      source of the seed responses (edit here)
│   │   └── templates.json     generated seed data (19 responses)
│   └── tests/                 pytest suite (incl. JS/Python Jotform parity)
├── frontend/
│   ├── index.html  manifest.webmanifest  sw.js
│   ├── css/app.css            hand-written, light + dark, 48px+ touch targets
│   ├── js/                    app.js api.js store.js jotform.js requirements.js speech.js
│   └── icons/
├── scripts/run.sh  scripts/make_icons.py
├── Dockerfile  requirements.txt  .env.example
```

`backend/app/services/rules.py` is the single source of truth for fields and requirements. The PWA gets them from `/api/meta` and caches them, so the checklist and the Jotform link keep working offline.

### The Jev decision gate

`/api/triage` sends one request to `POST https://openrouter.ai/api/alpha/decisions` with model `typesafe/jev-1.13`. It asks these typed questions:

| Question | Primitive | Used for |
|---|---|---|
| `category` | choice over the 7 categories | auto-detecting the category |
| `needs_representation` | noul | Resolve vs Escalate recommendation |
| `urgency` | score (routine / time-sensitive / urgent) | urgency pill |
| `notes_cover__<item>` | noul per open checklist item | "Mentioned in notes – confirm" hints |

Jev is layered on top of a deterministic rules engine and never replaces it:

* **Deterministic.** Required fields come from the rules engine. Jev only adds "might be in the notes" hints.
* **Overrides.** A category the caseworker picks always wins over Jev's guess.
* **Fallback.** If there is no key, or the call times out (`JEV_TIMEOUT_SECONDS`, default 6s) or fails, triage falls back to rules only. The header shows which engine was used.

### Privacy by design

* **Data sent to Jev and the drafting model.** Both receive PII-redacted notes only.
  * The following are stripped before sending:
    * phone numbers and emails
    * CRN, NDIS, My Aged Care, TRN and DVA numbers
    * dates and TFNs
    * any name, street, suburb or other value already typed into a personal field
  * Drafts use a `{FIRST_NAME}` placeholder, and the real name is inserted locally afterwards.
  * **Limitation:** a name that appears *only* in the free-text notes can't be detected reliably, so keep third-party names out of the notes where you can.
* **Search queries.** Queries are built from the notes with identifiers removed. Capitalised words that aren't known policy terms are also removed (they are usually names). The caseworker can still see and edit the query before searching.
* **TFNs.** The app warns when a TFN is typed and redacts it from saved cases and Jotform notes. The ATO field asks for a case reference, never a TFN.
* **Saved cases.** Recent cases are purged after `CASE_RETENTION_DAYS` (default 30).
* **Service worker caching.** The service worker never caches triage, case or draft responses. Only the app shell, `/api/meta` and the template library are cached.
* **Access control.** `APP_ACCESS_TOKEN` gates every API route. Each device enters the code once.

---

## Setup

### Run locally

```bash
cp .env.example .env        # then fill in keys (all optional)
./scripts/run.sh            # creates .venv, installs deps, starts on http://127.0.0.1:8787
```

Or manually: `pip install -r requirements.txt && python -m backend.app.main`.
Or with Docker: `docker build -t casework . && docker run -p 8787:8787 -v casework-data:/data --env-file .env casework`.

### Configuration (`.env`)

| Variable | Purpose |
|---|---|
| `APP_ACCESS_TOKEN` | Shared office access code. **Set this before exposing beyond localhost.** |
| `OPENROUTER_API_KEY` | Enables the Jev decision gate (and draft polishing). |
| `JEV_MODEL` | Default `typesafe/jev-1.13`. `~typesafe/jev-latest` also works, but pinning keeps behaviour stable. |
| `GENERATE_MODEL` | Optional OpenRouter chat model for polishing drafts. Blank means template drafts only. |
| `BRAVE_API_KEY` *or* `GOOGLE_CSE_KEY` + `GOOGLE_CSE_CX` | Live gov search. Without one, search shows site-restricted search links and the contact directory instead. |
| `SEARCH_DOMAINS` | Allow-list. Results from other domains are dropped server-side. |
| `JOTFORM_TYPEA_MAP` | JSON mapping each category to the **exact** option text of the form's `typeA` dropdown (see below). |
| `CASE_RETENTION_DAYS` | Auto-purge for saved calls (default 30). |
| `OFFICE_PHONE`, `OFFICE_EMAIL` | Added under the "Team Moreton" sign-off if set. |

### Expose to staff phones

Service workers, home-screen install and the microphone all need **HTTPS**, except on `localhost`. A plain `http://192.168.x.x:8787` address will load, but it won't install or work offline.

**Tailscale (recommended).** You get HTTPS, there are no open ports, and only devices on the office tailnet can reach it.

1. In the Tailscale admin console, enable **MagicDNS** and **HTTPS certificates**.
2. On the machine running the app (leave `HOST=127.0.0.1`), run:
   ```bash
   tailscale serve --bg 8787
   ```
3. Staff install Tailscale on their phones and open `https://<machine>.<tailnet>.ts.net`.
   * **iOS:** Safari → Share → **Add to Home Screen**.
   * **Android:** Chrome → **Install app**.
4. Set `APP_ACCESS_TOKEN` as a second layer of protection.

**Local network only.** Put a TLS reverse proxy in front of the app (for example Caddy with an internal CA, or `mkcert`), set `HOST=127.0.0.1`, and point the proxy at port 8787. Don't use `tailscale funnel`, which would make the app public.

---

## Before go-live checklist

1. **Jotform field names.**
   * The prefill uses the parameter names in the brief: `name[first]`, `name[last]`, `phoneNumber120`, `email`, `address132[...]`, `typeA`, `crn`, `moreInformation`.
   * Open a generated link and confirm each field fills in.
   * If the phone field is a Jotform *phone* widget, it may need `phoneNumber120[full]`. Change it in `PARAMS` in `backend/app/services/jotform.py` **and** in `frontend/js/jotform.js`. The parity test will flag any mismatch.
2. **`typeA` values.** Jotform only accepts the dropdown's exact option text. Set `JOTFORM_TYPEA_MAP`, for example:
   `{"services_australia":"Centrelink","immigration":"Immigration","ndis":"NDIS","aged_care":"Aged Care","ato_nbn_dva":"Other Federal","flags_messages":"Flags / Messages","general":"General"}`
3. **Review every seed response.**
   * All 19 ship tagged **needs review / verify**. Check each against its source links, adjust it to office practice, then save it in **Library**, which marks it reviewed.
   * Pay particular attention to the flags program items and the milestone-message eligibility. Both carry `[STAFF: …]` notes.
   * Add the office's preferred local southside services to the referrals response.
4. **Office details.** Set `OFFICE_PHONE` and `OFFICE_EMAIL` so drafts include them.

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest backend/tests          # 29 tests; the Jotform parity test needs node
python backend/seed/build_seed.py       # regenerate templates.json after editing seeds
```

Seeds are only inserted when their slug is missing, so office edits are never overwritten. `POST /api/templates/reseed` adds new seeds to an existing database. Interactive API docs are at `/api/docs`.

**Design note.** The brief suggested Tailwind. The UI uses a small hand-written stylesheet instead, so there is no build step, no CDN dependency and nothing that breaks offline. It is also compatible with the strict Content-Security-Policy (`script-src 'self'`).
