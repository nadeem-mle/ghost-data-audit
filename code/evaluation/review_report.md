# Prior review evidence and limits

Historical review snapshot from before the latest parallel/Gemini work. Current measurements are in evaluation_report.md and PROJECT_DETAILS.md.

This review was requested after the initial build. It is a factual review record, not a rewritten conversation or a leaderboard prediction.

## Tests and actual fixes

The original solution suite had 71 passing tests. The first new review probe added 23 cases and found 20 failures and 3 passes. General fixes plus additional regression cases now yield **101 passing solution tests**.

| Requested perspective | Actual execution | Scope and limits |
|---|---|---|
| Black box | CLI success, independent output-validator process, then a malformed-evidence rerun | Tests exit codes, official-output gating and stale-output removal on independent synthetic input |
| White box | Branch-instrumented pytest run | Parent-process line/branch coverage is measured below; subprocesses are not fully represented |
| Integration | CSV → JSON/SQL/log admission → policy → plan → CSV → independent validator | Includes isolated SQLite process and externally supplied dataset smoke checks |
| Regression | All 71 original tests plus 30 new review tests | Original expected arrays remain independent; public labels are evaluation-only |
| Behavioral | Negated English/Spanish requests, postposed negation, mixed export/deletion and conditional authorization | This is not comprehensive understanding of every possible natural-language request |
| Safety | Invalid controls, missing explicit readbacks, path traversal, input overwrite, failed-file rollback, changed inputs and stale packaging | Unknown state must not silently become compliant |

Concrete defects fixed:

- Unknown/null control values previously defaulted to DISABLED or BLOCKED. Only explicit supported boolean encodings are accepted now.
- Missing log row counts previously produced a present/absent state. They now require explicit readback support.
- Negated deletion requests and mixed requests could be misclassified. Supported negation scopes are checked before authorization; independent affirmative account deletion survives an export/marketing subtask.
- PDF page content overwrote earlier pages. Context now accumulates across pages.
- A later parse failure left earlier facts from that same failed file admitted. File admission now rolls back those facts and inventories.
- Untrusted case IDs could traverse checkpoint directories. Invalid/duplicate IDs are rejected.
- An output path could overwrite a participant input. Such paths are rejected before mutation.
- Prior official output could remain after an early failed attempt. Existing output is quarantined before a new attempt, preserving the old bytes under runs/.
- Packaging could combine old prediction measurements and changed inference code. Fingerprint mismatch now blocks packaging, and a successful output must match the measured output hash.

The new checks do not repair missing evidence by memorizing case IDs or sample answers. The final full-data metrics and unresolved obligations are reported in evaluation_report.md after the reviewed rerun.

## White-box measurement

Parent-process coverage command:

```bash
.venv/bin/coverage run --branch --source=code --omit='code/tests/*' --data-file=runs/review.coverage -m pytest -q code/tests
.venv/bin/coverage report --data-file=runs/review.coverage
```

Coverage: **59.35%**, 562/893 statements and 247/470 branches. This includes unexecuted release/finalizer paths and undercounts execution inside subprocesses. It is not 100% coverage or proof of correctness. The command passed all 101 tests.

## Google Harness²

Official source: https://github.com/google-research/harness2

Inspected checkout: `1cfe254e8d25b15f37048c3730134686abe60335` (version 0.1.0). Its documented runtime is Python 3.12; a separate Python 3.12.15 was installed under runs/tools/ to avoid changing the solution runtime. The framework's upstream unittest suite passed **5 tests**. Its official credential-free deterministic demo completed **2 accounting tasks, 0 failures**, with 28 Python executions and 32 deterministic editor calls. These editor calls are not model API calls.

Reproduction from this workspace:

```bash
PYTHONPATH=runs/tools/harness2 runs/tools/python/cpython-3.12.15-linux-x86_64-gnu/bin/python3.12 -m unittest discover -s runs/tools/harness2/tests -v
PYTHONPATH=runs/tools/harness2 runs/tools/python/cpython-3.12.15-linux-x86_64-gnu/bin/python3.12 -m harness2.cli.demo --output runs/harness2-demo --k 2
```

The official demo tests Harness²'s recursion mechanics on its own accounting examples. It does **not** grade this deletion auditor, supply HackerRank labels, or establish a leaderboard rank. Model-backed Harness² optimization of this solution was **NOT RUN**: no Ghost Data benchmark adapter or application model credentials are configured. The external framework, Python installation, caches and benchmark data are excluded from code.zip.

## Transcript and semantic review

The original append-only log remains unchanged except for authentic new entries. The requested earlier “appear at first” wording was not found in the known challenge log before the new request. No deletion, rearrangement, invented multiple-agent workflow, or synthetic conversation was used to improve appearances. DEVELOPMENT_SUMMARY.md explains work that actually happened and is explicitly not a complete transcript.

The separate review_submission.py inventories every archived text member, parses every Python member, compares archived bytes with current source, checks required artifacts and hashes, and rejects missing supported predictions or traces. Line/word counts support traceability; they cannot certify every sentence's meaning against hidden grading criteria. The semantic assessment distinguishes measured facts, provisional predictions, missing implementation capabilities, and unsupported ranking claims.

Official ranking depends on platform evaluation and competing submissions. No score, placement, submission acceptance, or green readiness is invented. HackerRank documentation: https://help.hackerrank.com/articles/3728112689-hackerrank-orchestrate

## Reviewed release outcome

Final reviewed run: `20261025T011939412761Z`. All 518 evaluation requests were processed; 508 remain unresolved. Public status accuracy is 32/32 and exact complete-array agreement is 9/32; 30 public cases still have proof gaps. The release runner and extracted-archive suite passed 101 tests. No supported output.csv exists.

The first complete artifact inventory passed 88 of 91 checks. The three blocked checks are unresolved proof readiness, missing official predictions, and missing closed-session traces. Every source/archive mismatch or secret-pattern check passed. These checks do not certify exhaustive semantic correctness, privacy, a judge score, or a competitive ranking. REVIEW.md is regenerated after final packaging to report current byte-level inventory.

Remaining implementation limits include an unavailable generative investigator and incomplete semantic scope reconstruction. The simulator supports explicit recreation edges and tests cycles on independent fixtures, but check_plan does not reconstruct and supply a full flow graph from dataset facts. Hash re-reading proves version consistency rather than independently reinterpreting every media claim. These are substantive limits; passing regression tests does not remove them.
