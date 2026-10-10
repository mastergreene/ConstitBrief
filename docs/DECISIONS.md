# Unresolved configuration decisions

These need an office decision or authorised access. The app runs with the conservative default shown, and nothing below has been invented.

| # | Decision | Why it matters | Current default in the app | Who / how to resolve |
|---|---|---|---|---|
| D1 | **Jotform notification routing**: the five email destinations and the conditions behind each | Handoff is only "complete" if the right team is notified. Overlapping notifications are possible. | Not modelled. ConstitBrief never sends email and never submits server-side, so the routing Jotform applies to a normal browser submission is untouched. | Jotform account owner: export **Settings → Emails** (each notification's recipients and conditions). Then run the synthetic routing test in `TEST_EVIDENCE.md`. |
| D2 | Which `typeA` option(s) each team owns | Needed to show staff where a handoff will land | The team suggestion is shown separately from the form option | Office manager, from D1 |
| D3 | Ownership of grants, events, donations, flags, congratulations ("proposed: Community") and of volunteer, parliamentary and ministerial work ("staff decide") | The brief confirms only four mappings | Shown as **proposed** or **staff to decide** in the UI | Office manager |
| D4 | Office-owned checklists for casework, parliamentary and ministerial referrals | Today's prompts are suggestions only and never block | All non-form items are tagged "Suggested prompt (not an office-verified requirement)" | Senior caseworker. Supply lists, which can then be encoded as `basis="office"` items. |
| D5 | Consent practice: when written consent or an authority is required, and how it is captured | The form has no consent field | A consent prompt appears as a suggestion for casework, and status is recorded only from what staff select | Office manager / privacy officer |
| D6 | **Analysis provider approval** (Jev on OpenRouter, or none) | Notes, even redacted, would go to OpenRouter / TypeSafe | `ANALYSIS_PROVIDER=rules`: nothing leaves the server | Office and privacy officer: review OpenRouter / TypeSafe data handling and retention. Jev is verified as a real model (`typesafe/jev-1.13`, Decisions API). |
| D7 | Drafting model for acknowledgement polish (`GENERATE_MODEL`) | Same data-flow question | Off (template drafts only) | As D6 |
| D8 | Draft retention period | Draft recovery vs holding sensitive notes | 72 hours (`DRAFT_RETENTION_HOURS`). Cleared immediately on "Finish & clear". | Privacy officer |
| D9 | Contact-detail prefill in the Jotform URL | Saves typing, but names and addresses land in browser history | Off (`JOTFORM_PREFILL_CONTACT=false`). Only the enquiry option is in the URL. | Office manager / privacy officer |
| D10 | Read-only Jotform API key for submission confirmation | Turns "reported by staff" into "confirmed in Jotform" | Off. Staff report the outcome themselves. | Jotform account owner. A read-only key is enough. |
| D11 | Form fixes: the unreachable "Party Member Inquiry" condition, no free-text field on "Invitation to an event", optional postcode | Invitation details can't be carried into the form | ConstitBrief flags "details with no form field" for staff to pass on separately | Form owner |
| D12 | How interactions that produce work for several teams are handled (one form per type, or one combined) | Avoid duplicates vs make sure each team is notified | One planned handoff per form option. Each needs its own explicit review and submission. Nothing is automatic. | Office manager |
| D13 | Long-term system of record (Swiftfox or other CRM), duplicate handling, retention | Out of scope for this phase | Jotform remains the destination. The record is portable JSON (`interactions.state`). | Office / IT |
| D14 | Hosting and identity: Tailscale-only, office SSO, MFA | Authentication strength | Local accounts with strong passwords on the tailnet | IT |
