"""Write the requested project account from actual current measurements."""
from pathlib import Path
import json

def write(root):
    root=Path(root);rd=root/(root/'runs/LATEST').read_text().strip()
    summary=json.loads((rd/'summary.json').read_text());metrics=json.loads((root/'runs/evaluation/metrics.json').read_text())['adaptive']
    historical=root/'runs/20261025T013848009697Z/summary.json'
    previous=json.loads(historical.read_text()).get('gemini_review',{}) if historical.exists() else {}
    g=summary.get('gemini_review') or previous;u=g.get('usage',{});cost=(u.get('input_tokens',0)*.30+max(u.get('output_tokens',0),u.get('total_tokens',0)-u.get('input_tokens',0))*2.50)/1_000_000
    text=f'''# Ghost Data Audit — complete project account

## Actual readiness

**BLOCKED, not ready to submit.** Run `{rd.name}` processed {summary['requests']} requests; {summary['unresolved']} remain unresolved. No official output.csv was generated. The internal diagnostic draft is not a valid prediction submission. The current coding session and parallel-review traces remain provisional until session closure/export. No leaderboard rank, acceptance or hidden accuracy is claimed.

Measured tests: **{summary['test_summary']}**. Public-sample status match: **{metrics['status_correct']}/32**; complete ordered-plan match: **{metrics['exact_cases']}/32**; public cases with proof gaps: **{metrics['unresolved']}/32**. These numbers must be considered together: correct status labels do not establish complete evidence-backed plans. The six-test frozen holdout and independently specified synthetic arrays are included in the suite.

## Problem and boundary

The system audits whether an authorized deletion actually completed across account services, secondary identifiers, search, exports, support, analytics, backups and replicas. It is an offline evidence auditor and remediation planner. It does not connect to live business databases, delete records, log in to HackerRank, upload a submission, or certify physical erasure.

The participant contract is frozen at official commit `0eddbbd33f682eae0a2770d67412af8a3cf4af20`: 518 evaluation requests, 32 public requests, 15 policy rows and 94 evidence-manifest entries. Source/input/config hashes are recorded with each run. Organizer-only truth, hidden labels, generators and private review internals are not used. Public sample labels are loaded only after predictions for evaluation.

## Architecture and data flow

Participant files → typed immutable facts and coverage ledger → exact identity/resource retrieval → cutoff and physical-copy reconstruction → runtime policy obligations → bounded investigation → deterministic remediation/verification plan → independent checks → release gate → allowlisted packaging.

The implementation is Python with dataclasses, SQLite, local OCR and pytest. Optional Gemini reasoning directs scoped read-only investigation tools; the final measured full-data run remains an explicit offline baseline. It avoids a graph service or a runtime swarm. `audit/model.py` defines facts, UTC timestamps, operations and canonical ordering. Facts retain source IDs/locations, system/resource/copy identifiers, observed/available times, state, category and source payload.

`audit/ingest.py` indexes the whole manifest, parses CSV/JSON/text/logs/SQL, reads PDF text and runs packaged ONNX OCR on screenshots. It handles six observed log encodings and joins trace-correlated readbacks. Each source gets a coverage status. Failed files roll back partially admitted facts. Evidence paths must stay inside the dataset. Explicit labelled PDF retention dates are extracted without inventing a universal retention period.

`audit/safe_sql.py` loads snapshots in isolated processes with statement restrictions, SQLite authorizers, CPU/memory/query/time limits and a narrow function allowlist. Attachments, extensions and filesystem functions are rejected. Snapshot scope and replicas are tracked separately.

`audit/engine.py` interprets deletion authorization, resolves supported current/historical identifiers and hashes, expands resource selectors to a fixed point, filters evidence by both observation and availability cutoff, and reconstructs copy-specific state. Shared identifiers do not automatically merge people. A later clean primary cannot erase a different replica's surviving record. Unlinked anonymous records co-located in a file are diagnostics, not automatic subject obligations.

The small policy interpreter loads the CSV's actual condition/action values; rule IDs are provenance rather than behavior switches. Missing periods, conflicting classifications or unsupported retention conditions stay unresolved. Retained records and backups are protected. Internal states distinguish proven compliance, proven violations and unresolved obligations.

## Planning and independent verification

Plans distinguish findings, proposed remediation and final checks. Controls are ordered before record changes, while submitted arrays use the contract's phase/operation/system/resource ranking. Semantic duplicate steps are collapsed, with internal proof retained. Findings cite participant sources. INCOMPLETE actions and final checks have empty evidence IDs; COMPLETE checks require observed supporting sources. NOT_APPLICABLE has exactly an empty array.

`audit/simulate.py` tests state changes, retention, unrelated subjects, cycles and idempotency. `audit/flows.py` constructs a conservative subject-scoped graph from the admitted copies and obligations, and the plan checker passes its edges into simulation. Explicit source/destination links are distinguished from potential edges among known copies. Unknown endpoints remain coverage limits; the graph is a safety simulation, not invented observed topology or proof that every real-world route was discovered.

`validate_output.py` independently checks CSV/JSON schema, operation-state pairs, order, numbering, citation times, copy coverage, preserved categories and ledger/source binding. The parallel review fixed acceptance of forged observation times and categories. Source hashes are rechecked against raw files. Hash agreement proves version consistency; it is not a second full semantic interpretation of every image or sentence.

Official output is written atomically only when every row is supported and validation passes. Stale output is quarantined before a new attempt, unsafe output/checkpoint paths are rejected, and changed inference fingerprints block packaging. A case with unresolved proof and no proven violation now has no official status. It is withheld from draft.csv while all 518 cases remain in results.json and case_review.csv. Unknowns do not become fabricated INCOMPLETE findings or unsupported COMPLETE submissions.

## Gemini integration and measured use

An optional `audit/gemini.py` REST adapter reads a key from the environment or an in-memory argument. The user-specified credential was staged only under private runs/ storage; its value was not printed, logged or packaged. Requests use the fixed official Google HTTPS origin and an API-key header, with redirects rejected, bounded payload/response size, timeout, call budget, output cap and at most one retry. Mock tests exercise caps, retry accounting, unavailable credentials, HTTP failures, invalid JSON and secret-safe errors.

The direct current-model health probe succeeded on `gemini-3.5-flash-lite`, reporting 19 total tokens. A listed older Flash-Lite model returned 404; that failure is recorded. An earlier portfolio gateway request returned HTTP 403 and did not establish provider health.

`gemini_review.py` provides optional, bounded, evidence-grounded gap triage, wired through `main.py --gemini-model` and `run_release.py --gemini-model`. The user explicitly authorized sending up to three fictional challenge-case excerpts after automatic review requested payload-specific authorization. The separately measured advisory development phase in run `20261025T013848009697Z` reviewed **{g.get('cases_reviewed',0)} cases**, with **{g.get('successful_reviews',0)} schema/citation-validated responses**. Usage: **{u.get('input_tokens',0)} input, {u.get('output_tokens',0)} output, {u.get('total_tokens',0)} total tokens**, **{u.get('attempted_calls',0)} calls**. Paid-rate equivalent: **${cost:.8f}** using checked standard rates; actual billing tier/invoice is unavailable.

The model receives admitted, cutoff-filtered units and unresolved questions. Quotes must match their cited unit; invented source IDs or unsupported quotes are rejected. Model advice does not change facts, policy, labels or readiness. That historical advisory phase was attached to unchanged verified reconstruction. The current full offline run made **{summary.get("model_calls",0)} model calls**; historical tokens are not claimed as current inference. It cannot manufacture missing ownership links or retention dates.

## Model-directed tool agent

`audit/investigator.py` adds an opt-in observe/select-tool/observe loop. The model chooses typed read-only evidence tools and can follow up on the returned observations. The application enforces case scope, cutoff eligibility, bounded calls, repeated-query rejection and exact-source quote validation. The model cannot execute arbitrary commands, read sample labels, inspect unrelated files, select final CSV labels or override policy. The existing deterministic inspector remains the offline baseline.

See `code/evaluation/agent_architecture.md` for the requirements assessment, tool contract and current test evidence. The successful live synthetic test in `runs/tool-agent-live.json` selected two tools in three Gemini calls, reporting1,561 input,130 output and1,691 total tokens; missing proof was preserved. This is separate from challenge-case inference. The earlier authorization covered three challenge-case excerpts and does not imply an unbounded new export of the dataset.

## Testing and development review

The original suite had 71 passing tests. New black-box/behavioral probes found 20 failures among the first 23 added cases. General fixes covered unknown control values, missing readback counts, negated/mixed consent, lost PDF pages, partial-file fact leakage, checkpoint traversal, input overwrite, stale output and stale packaging. Later parallel work added retention-provenance boundaries, stronger independent-checker binding, PDF dates and bounded Gemini tests.

The current suite covers black-box subprocess CLI behavior, white-box branches, integration through output validation, public regression, frozen holdout, behavioral intent, source cutoff/copy checks, mutation/metamorphic safety and SQL/prompt-injection defenses. Passing tests do not imply exhaustive language/media coverage. The earlier parent-only coverage checkpoint was 59.35%. A later 174-test checkpoint instrumented subprocesses and measured 68% combined line/branch coverage; see runs/deep-coverage/report.txt. That checkpoint predates the newest additions. Historical checkpoint20261025T112332207630Z instrumented204 tests with public ablations and full-data/clean-archive execution and measured83% combined statement/branch coverage (runs/deep-coverage/final-report.txt); this is not exhaustive semantic correctness.

Google's official Harness² repository at `1cfe254e8d25b15f37048c3730134686abe60335` was inspected and run with separate Python 3.12.15. Its five upstream tests passed; its credential-free demo completed two accounting tasks without failures, with 28 Python executions and 32 deterministic editor calls. This was an upstream-framework smoke exercise, not a HackerRank benchmark of this auditor. Model-backed Harness² optimization of this solution was not run.

At the user's request, parallel development reviewers investigated evidence gaps, retention/checker behavior and the provider adapter. They did not form a runtime agent swarm or vote on labels. Helper exact runtime metadata was unavailable for some logging contexts, so no identities were invented. Complete identified structured exports still need post-session review/finalization.

## Results and remaining blockers

All {summary['requests']} requests are accounted for. {summary['unresolved']} unresolved requests prevent release. Removing blanket co-location blockers reduced the prior 508 unresolved count without inventing ownership. The research-based scope correction removed the unconditional account-resource requirement while retaining explicit linked-resource readback and nonempty-proof checks. Current scope diagnostics refer only to the supplied evidence and do not certify undisclosed real-world systems. Remaining gaps include retention applicability, explicit linked-resource readbacks, document classification and restore controls. These are unresolved implementation/evidence interpretations, not a proven count of missing organizer inputs. The conservative graph is now integrated into plan checks, but cannot discover missing ownership or routes from nothing. Gemini's grounded triage explains missing proof but cannot replace it.

The full set is unlabeled, so its accuracy and false-completion rate are not measurable. Public sample status/array metrics above and the independent fixture results are the actual validation evidence. The internal draft is deliberately partial when official labels are unsupported and fails the full-input case-set requirement; case_review.csv and results.json retain every request. Even a separately validated supported subset is diagnostic and is not a 518-row submission. It stays under runs/ and is excluded from upload/.

## Files and reproduction

- `code/main.py`: main auditor CLI.
- `code/audit/`: ingestion, state/identity/policy, SQL isolation, simulation, provenance, optional Gemini transport.
- `code/tests/`: independent expectations, holdout and regression/safety tests.
- `code/evaluation/evaluation_report.md`: public metrics, custom cases, ablations and actual failures.
- `code/evaluation/usage_report.md`: final-run provider usage and attributable cost limits.
- `code/evaluation/review_report.md`: earlier review evidence and limitations.
- `code/evaluation/agent_architecture.md`: model-directed loop design and requirements assessment.
- `code/evaluation/ocr_review.md`: OCR release research, measured screenshot extraction and limits.
- `code/evaluation/research_application.md`: scope correction, before/after measures and remaining work.
- `code/interview_prep.md`: short guide generated from actual implementation/results.
- `code/DEVELOPMENT_SUMMARY.md`: authored factual summary, not a complete transcript replacement.
- `code/review_submission.py` and root `REVIEW.md`: archive/text inventory and readiness review.
- `runs/{rd.name}/`: current fingerprints, all 518 case checkpoints, case_review.csv, coverage, partial internal draft, tests and summary. Historical Gemini triage and live synthetic tool tests have separately identified run files. Do not upload this directory.
- `upload/`: current allowlisted submission-preparation artifacts; incomplete predictions and credentials are excluded.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r code/requirements.txt
.venv/bin/python -m pytest -q code/tests
.venv/bin/python code/evaluation/main.py --dataset dataset
.venv/bin/python code/run_release.py --dataset dataset
# Optional: set GEMINI_API_KEY securely in this shell before enabling provider calls.
.venv/bin/python code/run_release.py --dataset dataset --gemini-model gemini-3.5-flash-lite
.venv/bin/python code/review_submission.py
```

## Submission mapping and finalization

Official page: https://www.hackerrank.com/contests/hackerrank-orchestrate-october26/challenges/ghost-data-still-exists

| Local artifact | Submission purpose | Current status |
|---|---|---|
| `upload/code.zip` | Code ZIP | Built; includes code, tests, README and Markdown reports |
| `upload/output.csv` | Prediction CSV | Not generated: proof readiness blocked |
| `upload/log.txt` | README's chat_transcript field | Authentic append-only log; provisional until session closure |
| `upload/agent-trace.zip` | Separate trace ZIP field/instructions | Not finalized; never nest in code.zip |
| `upload/INTERVIEW.md` | Preparation for the interview | Local guide; do not substitute it for a required upload field |
| `upload/UPLOAD.md`, `upload/MANIFEST.md` | Local instructions and version/checksum record | Review before any upload |

The actual platform form determines field names; no upload endpoint is invented. Confirm acceptance on the platform only after all gates clear. After exiting/exporting the identified challenge sessions, run `bash runs/FINALIZE.sh` to refresh transcript copies and manifest without changing predictions. Review privacy and include all relevant challenge-session exports. Interview timing/camera requirements must be checked on the platform.

The current result is **BLOCKED**, not submitted or ranked. Production would additionally need authorized live inventories/readbacks, monitored restore controls, operational rollback and repeated re-auditing.
'''
    path=root/'PROJECT_DETAILS.md';path.write_text(text)
    # Mirror the same requested document into the code allowlist for reviewer access.
    (root/'code/PROJECT_DETAILS.md').write_text(text)
    return path
if __name__=='__main__':print(write(Path(__file__).resolve().parents[1]))
