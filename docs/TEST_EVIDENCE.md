# Acceptance test evidence

Run on 10 October 2026 against synthetic data only. No live constituent data was used, and no request reached the real Jotform: the browser suite intercepts `form.jotform.com`.

* **Backend:** `python -m pytest backend/tests` → **60 passed, 1 warning**
* **Browser:** `node tests/e2e/acceptance.mjs` (Chromium, real server, desktop 1360×900 plus mobile 390×844) → **16/16 scenarios passed**
* **Form drift check:** `python scripts/snapshot_jotform.py --check` → "Form structure unchanged"

## Scenario → evidence (brief §10)

| Scenario | Required result | Browser (e2e) | Backend tests | Result |
|---|---|---|---|---|
| NDIS enquiry with incomplete details | Casework ownership; verified questions; missing details exposed, nothing invented | NDIS enquiry with incomplete details | `test_analysis::test_ndis_incomplete` | Pass |
| Immigration enquiry | Verified checklist and consent; missing identifiers stay visibly missing | Immigration enquiry… | `test_immigration_identifier_optional_and_consent_not_inferred` | Pass. The DHA reference is a visible *optional* prompt because the form has no identifier field. |
| Sporting club grant + invitation | Both work types, ownership proposed, details for both | Sporting club… (2 planned handoffs) | `test_sporting_club_grant_plus_invitation` | Pass. Ownership is "proposed: Community", pending D3. |
| Journalist with a deadline | Suggest Comms, highlight the stated deadline | Journalist with a deadline | `test_journalist_deadline` | Pass |
| General administrative enquiry | General intake and Administration routing | General administrative enquiry | `test_general_admin`, `test_grant_keyword_alone_does_not_force_admin` | Pass. Administration is the *team*; the email destination depends on D1. |
| Parliamentary or ministerial request | Capture context, staff-reviewed referral | Parliamentary / ministerial… | `test_parliamentary_and_ministerial_need_staff_ownership` | Pass |
| Ambiguous or conflicting notes | Flag uncertainty, targeted clarification, manual ownership | Ambiguous or conflicting notes | `test_ambiguous_and_conflicting` | Pass |
| Staff correction then more typing | Correction retained; no silent overwrite | Staff correction followed by more typing | `test_staff_values_authoritative_and_contradiction_raised`, `test_rejected_proposal_not_resuggested…` | Pass |
| Rapid typing, delayed model responses | Discard stale analysis, keep focus | Rapid typing… (first response delayed 2.5 s) | `test_analyse_endpoint_echoes_seq` | Pass |
| AI unavailable | Manual intake and handoff continue, notes kept | AI unavailable… (every analysis request aborted) | `test_ai_unavailable_falls_back_to_rules` | Pass |
| Mandatory Jotform field missing | Explain and block | Mandatory Jotform field missing blocks submission | `test_missing_required_blocks`, `test_missing_mandatory_blocks_opening` | Pass |
| Valid staff-approved submission | Correct mapping; existing notification behaviour kept | Valid staff-approved submission… | `test_build_rows_and_validation`, `test_url_never_carries_notes_or_identifiers` | **Partial.** Mapping verified. Notification behaviour can't be verified yet (see below). |
| Retry / uncertain response | No duplicate delivery, accurate status | Valid staff-approved submission… (duplicate warning) | `test_valid_lifecycle_and_duplicate_prevention`, `test_staff_can_report_not_submitted`, `test_verification_finds_reference` | Pass |
| New interaction | Clear previous context | New interaction clears the previous person | `test_clear_interaction_wipes_content_but_keeps_handoff_log` | Pass |

Additional controls are covered by `test_api.py`: sign-in required, login throttling, cookie flags, CSRF header, other officers can't see drafts, draft expiry, unknown fields dropped, admin-only library approval, Jev request redaction and Jev answer validation.

## Latency

* Server analysis (rules): 2–17 ms for typical notes; about 17 ms for 4,000 characters (`test_fast`).
* Measured in the browser: **669 ms** from the end of typing to updated suggestions, of which 650 ms is the deliberate debounce. The target is under 2 s.
* With `ANALYSIS_PROVIDER=jev` the rules result still arrives first, and the model result is merged when it lands (timeout `JEV_TIMEOUT_SECONDS`, default 3 s). **Jev latency hasn't been measured**, because no OpenRouter key was available in this environment.

## Browser run output

```
latency: 669 ms after typing stopped (debounce 650 ms included); status "Up to date · 12 ms"
PASS  Sign-in required before any case information                                321 ms
PASS  Sporting club grant request plus invitation                                1169 ms
PASS  Rapid typing and delayed responses: stale analysis discarded, focus kept   5384 ms
PASS  NDIS enquiry with incomplete details                                        997 ms
PASS  Immigration enquiry: identifiers stay visibly missing, not compulsory      1026 ms
PASS  Journalist with a deadline                                                 1018 ms
PASS  General administrative enquiry                                              940 ms
PASS  Parliamentary / ministerial request: staff-reviewed referral               1018 ms
PASS  Ambiguous or conflicting notes                                              995 ms
PASS  Staff correction followed by more typing                                   1739 ms
PASS  Mandatory Jotform field missing blocks submission                          1053 ms
PASS  Valid staff-approved submission maps values; retry does not duplicate      1072 ms
PASS  AI unavailable: manual intake and handoff continue                         1239 ms
PASS  New interaction clears the previous person                                  460 ms
PASS  Mobile: panel switching preserves notes                                     941 ms
PASS  Latency: useful update within 2 s of a typing pause                         880 ms

16/16 scenarios passed
```

Screenshots: `docs/evidence/`.

## Backend tests (60 passed, 1 warning)

```
backend/tests/test_analysis.py::test_sporting_club_grant_plus_invitation
backend/tests/test_analysis.py::test_ndis_incomplete
backend/tests/test_analysis.py::test_immigration_identifier_optional_and_consent_not_inferred
backend/tests/test_analysis.py::test_journalist_deadline
backend/tests/test_analysis.py::test_general_admin
backend/tests/test_analysis.py::test_grant_keyword_alone_does_not_force_admin
backend/tests/test_analysis.py::test_parliamentary_and_ministerial_need_staff_ownership
backend/tests/test_analysis.py::test_ambiguous_and_conflicting
backend/tests/test_analysis.py::test_staff_values_authoritative_and_contradiction_raised
backend/tests/test_analysis.py::test_rejected_proposal_not_resuggested_and_dismissed_question_hidden
backend/tests/test_analysis.py::test_staff_types_override_suggestions
backend/tests/test_analysis.py::test_not_applicable_respected
backend/tests/test_analysis.py::test_ready_when_mandatory_captured
backend/tests/test_analysis.py::test_safety_flags_and_tfn_warning
backend/tests/test_analysis.py::test_fast
backend/tests/test_api.py::test_api_requires_sign_in
backend/tests/test_api.py::test_login_rejects_bad_password_and_throttles
backend/tests/test_api.py::test_session_cookie_flags
backend/tests/test_api.py::test_csrf_header_required_for_writes
backend/tests/test_api.py::test_logout_ends_session
backend/tests/test_api.py::test_security_headers
backend/tests/test_api.py::test_interaction_save_conflict_and_isolation
backend/tests/test_api.py::test_clear_interaction_wipes_content_but_keeps_handoff_log
backend/tests/test_api.py::test_expired_drafts_purged
backend/tests/test_api.py::test_unknown_record_fields_dropped
backend/tests/test_api.py::test_analyse_endpoint_echoes_seq
backend/tests/test_api.py::test_ai_unavailable_falls_back_to_rules
backend/tests/test_api.py::test_missing_mandatory_blocks_opening
backend/tests/test_api.py::test_valid_lifecycle_and_duplicate_prevention
backend/tests/test_api.py::test_staff_can_report_not_submitted
backend/tests/test_api.py::test_other_officer_cannot_touch_handoff
backend/tests/test_api.py::test_verification_finds_reference
backend/tests/test_api.py::test_verification_unavailable_without_key
backend/tests/test_api.py::test_unknown_form_option_rejected
backend/tests/test_api.py::test_guidance_only_shows_approved_and_only_admin_edits
backend/tests/test_api.py::test_jev_request_is_redacted_and_typed
backend/tests/test_api.py::test_jev_response_validated
backend/tests/test_api.py::test_generate_ack_makes_no_promises
backend/tests/test_extract.py::test_identifier_proposals_have_evidence
backend/tests/test_extract.py::test_never_extracts_names_or_consent
backend/tests/test_extract.py::test_tfn_never_becomes_another_identifier
backend/tests/test_extract.py::test_dates_are_proposals_with_wording
backend/tests/test_extract.py::test_redact_removes_identifiers_and_known_personal_values
backend/tests/test_extract.py::test_outcome_proposal
backend/tests/test_formmap.py::test_mapping_consistent_with_snapshot
backend/tests/test_formmap.py::test_every_form_option_has_a_branch_and_vice_versa
backend/tests/test_formmap.py::test_required_fields_match_public_form
backend/tests/test_formmap.py::test_build_rows_and_validation
backend/tests/test_formmap.py::test_missing_required_blocks
backend/tests/test_formmap.py::test_invalid_email_rejected
backend/tests/test_formmap.py::test_dates_split_for_jotform_and_unmapped_details_go_to_description
backend/tests/test_formmap.py::test_invitation_has_no_free_text_field_so_details_are_flagged
backend/tests/test_formmap.py::test_invalid_choice_value_never_sent
backend/tests/test_formmap.py::test_unknown_option_refused
backend/tests/test_formmap.py::test_url_never_carries_notes_or_identifiers[False]
backend/tests/test_formmap.py::test_url_never_carries_notes_or_identifiers[True]
backend/tests/test_formmap.py::test_taxonomy_types_use_real_options
backend/tests/test_search_drafts.py::test_search_filters_to_allowed_domains
backend/tests/test_search_drafts.py::test_search_without_provider_gives_links
backend/tests/test_search_drafts.py::test_polish_never_sees_names
```

## Routing verification procedure (blocked: needs Jotform account access)

The brief requires routing to be verified with synthetic records and controlled notifications. That couldn't be done here, because notification settings aren't public and only the office can create a safe test target.

1. In Jotform, **clone** form 252413844700855, including its email notifications.
2. On the clone, replace every notification recipient with controlled test mailboxes, one per original destination. Record the mapping.
3. In a staging deployment set `JOTFORM_FORM_ID=<clone id>`. Cloned forms keep the same field IDs. Run `python scripts/snapshot_jotform.py --check` against the clone's HTML to confirm.
4. For each of the 15 `typeA` options, run a synthetic interaction ("Test Synthetic, 1 Example St") through ConstitBrief. Review the mapping, open the form, submit it, then report "submitted".
5. Record which test mailbox(es) received each notification, including any overlap. Compare against D1.
6. Optionally set a read-only `JOTFORM_API_KEY` for the clone and use "Check Jotform for this reference" to confirm each submission.
7. A submission acknowledgement is **not** proof of delivery, so check the mailboxes themselves.
