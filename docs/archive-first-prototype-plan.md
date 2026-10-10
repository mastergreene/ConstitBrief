# Product Plan & Implementation Brief: Moreton Casework Fast-Resolver (PWA)

## 1. Executive Summary & Context
Build a mobile-first Progressive Web App (PWA) designed for an Australian Federal Electorate Office (Moreton / Julie-Ann Campbell MP). The tool will be used by caseworkers, staff, and volunteers on the phone, at mobile offices, or on the road.

The primary operational goal is **First Contact Resolution**. If an issue cannot be resolved on the spot, the secondary goal is **Zero Double-Handling**: gather every mandatory detail while the constituent is still on the line and prepare a 1-tap prefilled submission to the office's existing Jotform casework portal (`Web OfficeOne`).

---

## 2. Core User Workflows

### Mode A: First-Contact Resolution (Try to solve it now)
- Caseworker enters rough notes or speech-to-text from the constituent.
- System surfaces:
  1. Instant standard office advice (e.g. MyGov linking steps, statutory declaration requirements, energy rebates, concession card criteria).
  2. Real-time live policy search scoped to official Australian government domains (`homeaffairs.gov.au`, `servicesaustralia.gov.au`, `myagedcare.gov.au`, `ndis.gov.au`, `ato.gov.au`).
- Caseworker reads the answer aloud or taps "Copy SMS / Email" to send the resolution immediately.

### Mode B: Casework Escalation (When representation is unavoidable)
- If the issue requires formal representations to a Minister or agency (e.g. visa processing delays, Centrelink review of decision, NDIS plan disputes):
  1. **Jev Decision Gate:** System runs a low-latency System One evaluation (via OpenRouter TypeSafe Jev at `/api/alpha/decisions`) to determine missing mandatory fields.
  2. **"Ask Them Now" Card:** Displays a prominent checklist of missing items for the caseworker to ask before hanging up (e.g. "Ask for their CRN", "Ask for DHA Client ID / Transaction Ref", "Confirm they have signed a privacy consent release").
  3. **1-Tap JotForm Prefill:** Maps all collected constituent data directly into URL query parameters for the office Jotform (`https://form.jotform.com/252413844700855`). Tapping "Open in Jotform" opens the web form completely prefilled, ready for 1-click submission.
  4. **Draft Generator:** Generates a warm, local, community-first office acknowledgement in Jules' voice (signed "Team Moreton").

---

## 3. Key Features & Specifications

### 3.1 Mobile-First PWA Interface
- Clean, fast, one-handed mobile layout (large buttons, high contrast, offline-tolerant).
- Installable to iOS and Android home screens via Web App Manifest & Service Worker.
- Fast Category Filters:
  - Services Australia (Centrelink / Medicare)
  - Immigration & Visas
  - NDIS
  - MyAgedCare
  - ATO / NBN / Veterans' Affairs
  - Constituent Flags & Congratulatory Messages
  - General Inquiries

### 3.2 Live Gov Search
- Scoped search engine that queries live Australian government portals.
- Queries restricted to official government domains:
  - `site:servicesaustralia.gov.au`
  - `site:homeaffairs.gov.au`
  - `site:myagedcare.gov.au`
  - `site:ndis.gov.au`
  - `site:ato.gov.au`
- Returns snippet summaries, direct contact phone numbers, and source links.

### 3.3 Standard Responses & Knowledge Library
- Editable library of standard office responses and templates stored in local SQLite:
  - Standard Privacy & Consent Authorisation Pack
  - Immigration Ministerial Intervention Explainer & Reality Check
  - Australian Flag & Portrait Eligibility Guidelines
  - 50th / 60th / 100th Birthday & Anniversary Protocol
  - Local Food Relief, Housing, and Legal Referral Contacts
- One-tap "Insert into Draft" or "Copy to Clipboard".

### 3.4 JotForm Prefill Integration
- Target Form: `https://form.jotform.com/252413844700855`
- URL Parameter Mapping:
  - First Name: `name[first]`
  - Last Name: `name[last]`
  - Phone: `phoneNumber120`
  - Email: `email`
  - Address: `address132[addr_line1]`, `address132[city]`, `address132[state]`, `address132[postal]`
  - Enquiry Type: `typeA`
  - Centrelink CRN: `crn`
  - Notes / Case Details: `moreInformation`

---

## 4. Technical Architecture

- **Frontend:** Lightweight PWA (React + Tailwind or vanilla JS / HTML5) with responsive mobile UI, offline shell, and clipboard shortcuts.
- **Backend API:** Fast Python (FastAPI) or Node.js service:
  - Endpoint `/api/triage`: Evaluates input text using TypeSafe Jev (`model: typesafe/jev-1.13` on `https://openrouter.ai/api/alpha/decisions`) for instant classification and completeness scoring.
  - Endpoint `/api/search`: Real-time web search restricted to `.gov.au` domains.
  - Endpoint `/api/templates`: CRUD operations for standard responses.
  - Endpoint `/api/generate`: Generates constituent communications in Jules' voice.
- **Storage:** Local SQLite database for template storage, search cache, and recent case drafts.

---

## 5. What I Need You To Produce
1. **PWA Architecture & File Structure:** A clean, production-grade layout.
2. **Complete Source Code:**
   - The FastAPI backend (including Jev decision handler, live search, and Jotform URL builder).
   - The Frontend PWA (HTML, Tailwind CSS, JS logic, Service Worker, and Manifest).
3. **Seed Data:** Initial set of standard responses for Services Australia, Immigration, Flags, and MyAgedCare.
4. **Setup Instructions:** How to run locally and expose via Tailscale or local network.
