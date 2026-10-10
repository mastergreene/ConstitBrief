# ConstitBrief product brief and implementation handoff

Version: 1.0 | Updated: 11 October 2026 | Status: requirements baseline for coder

## 1. Purpose

ConstitBrief helps electorate staff and MPs collect useful information while speaking with constituents and community members. Staff type natural-language notes during the conversation. A live assistant identifies the work involved, suggests the next questions, tracks missing information and prepares a clear handoff for the relevant team.

The aim is to reduce avoidable follow-up calls and incomplete referrals without distracting the officer from the conversation. AI suggests questions and actions; staff remain responsible for decisions and submission.

For the initial implementation, ConstitBrief should sit in front of the office's existing Jotform. Jotform remains the intake and email routing mechanism.

## 2. Confirmed requirements

| Area | Requirement |
| --- | --- |
| Users | Electorate staff and MPs |
| Input | Staff type notes while speaking; live transcription is not required |
| AI role | Suggest questions, classifications and actions; staff decide |
| Live interface | Full assistant panel with checklists, suggestions and case summaries |
| Coverage | All office workflows, including parliamentary and ministerial referrals |
| Initial handoff | Use the existing Jotform as the first-step guide and handoff mechanism |
| Routing | Preserve the existing five email destinations and conditional notification rules |
| Long-term destination | Undecided; recommend an approach after assessing current systems |

This brief consolidates the agreed requirements. It is not a verified assessment of the repository or live form. Previous conversation mentioned an existing Jotform integration; the coder must verify its implementation and behaviour before relying on it.

## 3. Product experience

1. Officer starts a new interaction and types notes in a prominent text area.
2. The assistant updates as the notes change, without requiring a chat message for every update.
3. It extracts stated facts, recognises one or more enquiry types and suggests a responsible team.
4. It shows the most useful next questions and a checklist of information already collected or still missing.
5. The officer can correct extracted details, change classifications, dismiss suggestions and add actions.
6. The officer reviews an editable summary, field mapping and proposed handoff.
7. Only an explicit staff action initiates submission. Jotform applies its existing email notification rules.
8. The app distinguishes a prepared handoff from a confirmed Jotform submission. Failed or uncertain submissions remain recoverable.

Example: “President of a local sporting club called about funding for equipment and wants Julie-Ann at their presentation night.” The assistant should identify community engagement, grant assistance and an invitation. It should suggest collecting the club name, contact details, project information, event date, venue and formal invitation. These example prompts are illustrative, not verified mandatory Jotform fields.

## 4. Workflows and classification

Support broad coverage from the first version. Prioritise implementation depth where verified office rules exist; expose other workflows through a useful general intake and manual handoff rather than omitting them or inventing rules.

| Workflow | Expected assistance |
| --- | --- |
| Constituent casework | Identify subject, requested outcome, relevant agency, missing details and appropriate casework questions |
| Community engagement | Capture organisation, contact person, issue, relationship and requested follow-up |
| Grants | Capture organisation or applicant, project, funding need, known program and deadline; suggest community or other ownership from verified rules |
| Events and invitations | Capture event details, organiser, requested attendance or role and response deadline |
| Communications and media | Capture outlet or contact, topic, request, deadline and follow-up needed |
| Administration and other enquiries | Prepare a general intake and flag uncertain ownership for staff review |
| Parliamentary matters | Capture issue, requested parliamentary action, relevant material and deadlines; staff confirm ownership |
| Ministerial referrals | Capture relevant portfolio or department, issue, requested outcome and referral requirements; staff approve any proposed referral |

Keep these concepts separate:

| Concept | Meaning | Example |
| --- | --- | --- |
| Responsible team | Office owner of the work | Community |
| Enquiry types | One or more types of work | Grant assistance, event invitation |
| Additional actions | Proposed tasks arising from the interaction | Request invitation, check funding options |
| Email destinations | Notifications configured within Jotform | Existing configured destinations |

Do not assume five email destinations means five teams. Do not invent a fifth team or hard-code addresses from assumptions.

Confirmed team-level guidance:

| Enquiry | Responsible team |
| --- | --- |
| Constituent casework | Constituent team |
| Community enquiries | Community team |
| Communications and media | Comms team |
| Other enquiries | Administration |

The actual form must determine how categories map to its five email destinations, including overlapping notifications. A grant keyword alone must not force an Administration route. Support multiple work types and staff-approved secondary actions without silently submitting duplicate forms.

## 5. Jotform is the initial workflow baseline

Inspect the contact form linked or embedded at https://julieanncampbell.com.au/ and any existing repository integration. Public access may reveal questions and conditional branches but not notification settings. Use authorised configuration or an office-provided export to verify the five email destinations and conditions. If unavailable, document the gap and keep that configuration unverified.

Create a versioned mapping containing:

- Form ID, field IDs, labels, input types and allowed values.
- Required fields and the conditions under which they become required.
- Category options and conditional question branches.
- Consent wording, declarations and attachment requirements.
- Known routing conditions and their verification status.
- ConstitBrief field-to-Jotform mapping and transformation rules.

Separate verified form requirements from additional office checklists and AI suggestions. A suggested immigration identifier, NDIS detail or document must not become compulsory merely because the model proposes it. Use the identifier required by the verified workflow and avoid asking for unnecessary sensitive information.

Retain existing email routing in Jotform. Do not build a parallel email sender for this phase.

Recommended integration: prepare a structured record and offer a secure, reviewed handoff into the existing form. Assess whether the existing integration supports prefill, embedding or server-side submission. Choose the simplest supported approach that preserves required fields, consent and notification behaviour. Do not put sensitive case notes or identifiers into public prefill URLs, browser history or analytics. If secure automated transfer is not available, provide a reviewable copy-and-complete fallback.

## 6. Live assistant behaviour

The assistant panel must show:

- Suggested responsible team and enquiry types, with a short rationale and uncertainty indicator.
- An editable summary of the issue and requested outcome.
- Relevant checklist items marked collected, missing, unclear or not applicable.
- A short prioritised list of questions to ask next.
- Suggested follow-up actions and relevant deadlines.
- A readiness status distinguishing mandatory gaps from optional improvements.

Suggestions must adapt to the conversation, avoid repeating answered questions and reflect corrections. Never infer names, consent, reference numbers, eligibility or deadlines as facts. Show contradictions for staff resolution. Keep staff edits authoritative; later model responses must not overwrite them silently.

Use an approved source or office playbook for procedural guidance. Identify the source where relevant. If no verified guidance exists, provide an intake question or recommend team review rather than fabricating advice. Do not promise grants, agency outcomes or MP attendance.

JEV or a comparable System 1 style model is the proposed approach for fast assistance, not a verified dependency. Confirm exactly which model or service is intended, its API, suitability and data handling before selecting it. Keep the provider configurable.

## 7. Interface and reliability

Use a clear two-panel layout on desktop: notes on the left, assistant on the right. On smaller screens, provide accessible switching between panels while preserving notes. Keep typing focus stable when suggestions update. Avoid constant reordering, flashing alerts and unnecessary scrolling.

Provide keyboard navigation, labelled fields, readable contrast, visible focus and status indicators that do not rely on colour alone. Screen-reader updates should be controlled rather than announcing every token.

Suggested performance target: useful updates within two seconds of a short typing pause under normal conditions. Measure actual latency and report limitations. Debounce requests, cancel or discard stale responses and show when analysis is updating. AI failure must not prevent typing, manual completion or review.

Use draft recovery appropriate to approved office data handling. Show whether a draft is saved. Do not default to indefinite browser storage of sensitive casework. Provide explicit new-interaction/reset behaviour so one person's information cannot leak into the next interaction.

## 8. Architecture and records

Prefer extending the current stack and working components. Separate:

1. Notes and staff-controlled structured record.
2. AI analysis returning schema-validated suggestions.
3. Deterministic required-field and routing validation based on verified configuration.
4. A Jotform adapter for mapping and approved handoff.

The model proposes; application code validates. Never let free-text model output execute referrals or send notifications.

Suggested record fields: interaction ID, officer, timestamps, original notes, contact details, organisation, issue, requested outcome, responsible team, enquiry types, extracted facts with note evidence, checklist status, deadlines, consent status, proposed actions, staff corrections, summary, mapping version, handoff status and Jotform submission reference when available. Adapt this to the repository's existing model.

Recommended initial destination: Jotform for completed intake and its existing notifications. Avoid creating a separate permanent case-management database in this phase unless required and agreed. Keep the record portable for later integration with Swiftfox or another office system. Long-term record ownership, retention, duplicate handling and CRM integration remain decisions to resolve.

## 9. Controls proportionate to casework

- Authenticate staff and MPs before accessing case information.
- Keep model and Jotform credentials server-side; exclude personal details from diagnostic logs and analytics.
- Send only information necessary for the approved AI task to the approved provider.
- Require explicit consent capture where the verified workflow requires it; never infer consent from participation in a call.
- Record staff approval and handoff outcome without unnecessarily duplicating sensitive notes.
- Treat typed notes and imported content as data, not instructions to override workflow rules.
- Prevent duplicate submissions on retries and double-clicks; preserve a recoverable state when confirmation is uncertain.

## 10. Acceptance scenarios

| Scenario | Required result |
| --- | --- |
| NDIS enquiry with incomplete details | Suggest casework ownership and relevant verified questions; expose missing details without inventing answers |
| Immigration enquiry | Use verified checklist and consent requirements; missing identifiers remain visibly missing |
| Sporting club grant request plus invitation | Recognise both work types, propose ownership and collect details for both |
| Journalist with a deadline | Suggest Comms and highlight the stated deadline |
| General administrative enquiry | Offer useful general intake and Administration routing |
| Parliamentary or ministerial request | Capture context and requested action; propose a staff-reviewed referral |
| Ambiguous or conflicting notes | Flag uncertainty, ask a targeted clarification and allow manual ownership |
| Staff correction followed by more typing | Retain correction; update dependent suggestions without overwriting approved values |
| Rapid typing and delayed model responses | Discard stale analysis and preserve input focus |
| AI unavailable | Continue manual intake and handoff without losing notes |
| Mandatory Jotform field missing | Explain the missing requirement and block invalid submission |
| Valid staff-approved submission | Map values correctly and retain existing Jotform notification behaviour |
| Submission retry or uncertain response | Avoid duplicate delivery and show accurate handoff status |
| New interaction | Clear the previous person's context and suggestions |

Verify routing using synthetic test records and controlled test notifications, not live constituent data or unapproved production recipients. A successful submission acknowledgement must not be presented as proof every email was delivered.

## 11. Coder assignment and deliverables

First assess the ConstitBrief repository against this brief. Read repository instructions, identify the stack and trace the current notes, AI, checklist, routing and Jotform flows. Do not assume that an integration or screen is complete merely because code exists.

Produce a concise gap assessment: requirement, existing evidence, working/partial/missing status, proposed change and priority. Preserve working functionality and propose the smallest coherent changes needed.

Then implement in this order:

1. Verify and document form mappings and workflow rules; isolate any unavailable notification configuration.
2. Complete the live notes and assistant experience, including editable facts and multiple enquiry types.
3. Add deterministic validation, staff overrides and reviewed handoff.
4. Verify existing Jotform routing in a controlled environment.
5. Address accessibility, latency, failure recovery and duplicate prevention.

Deliver updated code, this brief incorporated into the repository documentation, the verified form mapping, a list of unresolved configuration decisions and test evidence for the acceptance scenarios. Explain what is ready for pilot use and what remains blocked.

Do not treat unresolved details as a reason to stop all development. Continue with synthetic data and configurable rules, but do not claim that unverified production routing is complete.

## 12. Decisions still to verify

- Exact repository URL, branch and current implementation.
- Current Jotform ID, fields, conditional logic and five notification destinations.
- Whether secure prefill or direct submission preserves existing office workflows.
- Which model or service “JEV” refers to and the approved provider configuration.
- Office-owned checklists for casework, parliamentary and ministerial referrals.
- Approved draft persistence, retention and eventual system of record.
- How staff should handle interactions producing work for multiple teams.

These are verification tasks and configuration decisions, not permission for the coder to invent office processes.
