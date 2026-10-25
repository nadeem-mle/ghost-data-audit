# implementer memory

(append dated lessons; newest last)
- 2026-10-25: Most labeled account_service verify steps have NO identifier link; only a deletion_worker DELETE_RECORD activity (resource ID only). Linked via global elimination (window reported_at-90m..+15m, result==reported_status map, identifier-compatible); 26/32 right, 0 wrong. Analytics ANONYMIZE jobs are NOT discriminative (tried; 4 wrong) — don't.
- 2026-10-25: Workflow-linked = weak: never delete without subject identifier; unobserved => future VERIFY "" only in INCOMPLETE, blocks COMPLETE.
- 2026-10-25: diff helper: scratchpad diff.py; eval takes ~2s; full main.py --no-llm run ~1 min.
- 2026-10-25: intent(): "check if"/"comprobar si" is an embedded question; skip the conditional guard when if/si follows a check/verify/know verb (case_02 fixed).
- 2026-10-25: Pre-request not-found lookups (state ABSENT, rows=0, observed < requested_at) must not seed subject resources (case_17 account_6523). Samples exact 18->20, no full-run row changes.
- 2026-10-25: full main.py --no-llm takes ~13s now; compare output sha256 plus run-dir results.json to count changed rows.
- 2026-10-25: Missing-account rows (128 in full run) are reported_at GROUPS (2-3 cases share reported_at) with equal-count deletion_worker DELETE_RECORDs at about -70/-60/-50 min. Ordering by case number, requested_at asc/desc matches confident assignments only ~1/3 (random); no identifier link in neighbouring activities or user_audit_log. Samples have offsets -75..-44 min (all unique reported_at). Result != reported status in 2/32 samples (case_06, case_08 PARTIAL->SUCCESS).
- 2026-10-25: Log event 'message_read' (5 lines, all message_text=[REDACTED]) was unparsed; impl4 patch adds SUPPORT_MESSAGE REDACTED fact -> only case_264 gains VERIFY_RECORD_REDACTED support_9996. Samples unchanged. case_46 tombstone_17 has no state fact anywhere in parsed corpus (not fixed).
