# Shared team memory — Ghost Data Audit (read by every agent first)

Project root: /home/nadeem/Desktop/ghost audit. Python: .venv/bin/python. Code: code/ (engine: code/audit/engine.py, ingest: code/audit/ingest.py).
Contract: official/problem_statement.md (authoritative). Scoring = hidden canonical answers for ALL 518 rows; a missing row scores zero.
Ground truth available: dataset/sample_deletion_requests.csv + dataset/sample_output.csv (32 labeled cases).
Eval: `cd code && ../.venv/bin/python evaluation/main.py --dataset ../dataset --single` -> code/runs/evaluation/metrics.json (key 'adaptive').

## Established facts (2026-10-25)
- Unresolved != missing organizer data. It means our code could not decide.
- rule_12 SECURITY_AUDIT_LOG: every labeled sample retains audit records (VERIFY_RECORD_PRESENT) with no per-record expiry. Engine fixed: missing retention date => retained; explicit expired date still blocks. Samples: unresolved 15->5, status 28->29/32, 0 false COMPLETE.
- Biggest remaining accuracy gap (exact plans 9/32, recall 0.60): labels include VERIFICATION steps for records ALREADY compliant:
  * VERIFY_RECORD_ABSENT account_service (20 samples) — e.g. case_01 account_001 cited evidence_54 (failover replica SQL whose primary table lacks the row => absence by complete inventory); case_21 account_6440 cited evidence_92.
  * VERIFY_RECORD_ANONYMIZED analytics_platform (7) and VERIFY_RECORD_PRESENT security_service (7) also missing.
  * For INCOMPLETE cases these verify steps use evidence_id ""; for COMPLETE they cite the readback file.
- Status labels: COMPLETE / INCOMPLETE / NOT_APPLICABLE only. Step order: phase, then operation-table order, then system_id, resource_id.
- Last full run before fixes: runs/20261025T114601727402Z (207 unresolved of 518).

## Team protocol
Each agent: read this file + its own .claude/agent-memory/<name>/MEMORY.md first; write its result to runs/agents/<name>/output.md; append durable lessons (dated, one bullet each) to its own MEMORY.md, and cross-team facts here.

## LLM provider (2026-10-25)
- OpenAI key lives ONLY in project-root .env (chmod 600, gitignored). NEVER print, log, copy or package it; never read do_not_read_in_chat_also_not_include_in_zip.md.
- Client: code/audit/openai_client.py (OpenAIClient, same interface as GeminiClient: model, usage, generate_json, list_models). CLI: `--gemini-model openai:<model>` / `--agent-model openai:<model>` (main.model_client).
- Available models include gpt-5.5, gpt-5.4, gpt-5.4-mini (cheap; smoke-tested OK). Use budgets (max_calls) and report usage for usage_report.md.
- Graders supply their own key via .env.example -> .env. code.zip must include openai_client.py and .env.example, never .env.
- 2026-10-25 (researcher): Samples: VERIFY_RECORD_ABSENT account_service appears in 22/22 INCOMPLETE and 10/10 COMPLETE cases (19 INCOMPLETE with no finding, evidence ""). Never withhold rows; uncertain => best-effort INCOMPLETE, flag in case_review.csv. See runs/agents/researcher/output.md.
- 2026-10-25 (qa): Harness 2.0 baseline (runs/agents/qa/scorecard-baseline.md): samples 29/32 status, 9/32 exact, F1 0.657, 0 false-COMPLETE; fixtures 28/30; fresh full run 514/518 rows (missing case_46,55,61,390), 0 invariant violations. Rerun: `cd code && ../.venv/bin/python evaluation/harness2.py --dataset ../dataset --label <name>`.
- 2026-10-25 (qa): BUG gemini_review.review_cases catches only GeminiError -> any OpenAIError (budget/HTTP) aborts main.run with no results.json.
- 2026-10-25 (implementer): account resource for most cases is linked only by deletion_worker DELETE_RECORD activity; engine now attributes these by global elimination (Auditor.workflow_accounts). Samples exact 9->18/32, P .866 R .803, 0 false COMPLETE. Remaining gaps: analytics anonymized verify (no reliable link), ambiguous windows, case_02 intent.
- 2026-10-25 (reviewer): The release gate is the #1 risk. main.py writes output.csv only if unresolved==0, and write_csv drops status=None rows. As of 17:35: 5 unresolved / 4 None (case_46, case_55, case_61, case_390). Best answers are in runs/agents/reviewer/output.md section 3. reporting.py hard-codes the word "BLOCKED".
- 2026-10-25 (reviewer): 10 CLASSIFY_REQUEST activities line up 1:1 with the 10 NOT_APPLICABLE cases (533-542). Use them as a cross-check.
- 2026-10-25 (reviewer): The contract wants evaluation/*.md at the code.zip root; the zip has them under code/evaluation/. Output is sorted lexicographically, but the input file is in numeric order.
- 2026-10-25 (implementer): patch at scratchpad impl2/patch.diff (not yet applied to live code). Fixes: Spanish "comprobar si" is a whether-question; a pre-request 404 lookup does not attribute an account. Samples exact 18->20, status 31/32, P .883 R .819. The 518 full output is byte-identical.
- 2026-10-25 (output): Submission packaged. upload/code.zip has root README.md, .env.example and evaluation/{evaluation,usage}_report.md plus code/**. Clean extraction + `main.py --no-llm` reproduces output.csv byte-identically. reporting.py readiness is now conditional. Running run_release.py would overwrite the hand-written reports.
- 2026-10-25 (qa): LINK_RESOURCE_IDENTITY catalog rows are case-window specific (screenshot at T, catalog at T+7m, audit about T+1d). Samples omit them only when they belong to another case. Engine wrongly drops export_1842 (case_33) and tombstone_17 (case_46). 118 non-NA rows have no account_service step at all (samples: 32/32 have one).
- 2026-10-25 (implementer): The account-gap rows come from groups of cases that share one reported_at and have k deletes in the -80..-40 min window. Delete time order is NOT tied to case number or requested_at; tested on 325 confident pairs, the match rate is about 33%, which is chance. Only a deliberate best-effort guess could fill them (accuracy about 1/k).
- 2026-10-25 (qa): Window audit of output.csv (runs/agents/qa/window-coverage.md): 2 rows likely missing a resource: case_46 tombstone_17 (activity_4011) and case_264 support_9996 (evidence_25, already redacted, so VERIFY_RECORD_REDACTED). case_33 cites export_1260, whose only link is in case_52's window (same subject), so it is suspected cross-case leakage. Audit_record support outside the window is normal (ledger 2026-10-01).
- 2026-10-25 (implementer): support message_read log lines are a redaction readback source (scratchpad impl4 patch).
