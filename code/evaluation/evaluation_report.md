# Evaluation report — Ghost Data Audit

Final prediction run: `runs/final-20261025T124654Z` (`python3 code/main.py --dataset dataset --output output.csv --no-llm`).
Result: 518/518 rows, 0 unresolved, `validate_output.py` OK, official output written.
output.csv SHA-256: `d626b8f296f8896a92cfa7a7d5c1e0b909c8e34aef3debb1e35e2b89c7606e9b`.
Status distribution: INCOMPLETE 355, COMPLETE 153, NOT_APPLICABLE 10.

Measurements come from Harness 2.0 (`code/evaluation/harness2.py`, scorecard `final-v3`, generated 2026-10-25T12:47Z) using the same code as the final run. To reproduce:
`cd code && python3 evaluation/harness2.py --dataset ../dataset --label <name>`.

Hidden-test accuracy has not been measured. The numbers below are for the 32 public labeled samples, 30 frozen team-made fixtures, and structural invariants on all 518 requests.

## 1. Case-level status accuracy (32 labeled samples)

| Metric | Value |
|---|---:|
| Status accuracy | **31/32 (96.9%)** |
| False COMPLETE (a COMPLETE predicted when the truth is INCOMPLETE) | **0** |
| Wrongful deletion (a delete/anonymize step on a retained record) | **0** |
| Unresolved in the isolated sample run | 1 (case_04; truth COMPLETE) |

Confusion (truth -> predicted): COMPLETE -> COMPLETE 9; COMPLETE -> unresolved 1; INCOMPLETE -> INCOMPLETE 22.
The one miss is conservative. They are never reported as a wrong COMPLETE. In the full 518 run, every case gets a status (0 unresolved).

## 2. Step-level accuracy (samples)

| Metric | Value |
|---|---:|
| Exact full plan match (status + every step) | **20/32** |
| Step precision | **0.883** |
| Step recall | **0.819** |
| Step F1 | **0.849** |
| Step TP / FP / FN | 158 / 21 / 35 |
| Verification coverage (all labeled verify steps present) | 20/32 |

## 3. Field-level accuracy (samples, 193 step keys compared)

| Field | Correct / compared | Accuracy |
|---|---:|---:|
| step_no | 158/193 | 0.819 |
| phase | 179/193 | 0.927 |
| system_id | 179/193 | 0.927 |
| resource_id | 179/193 | 0.927 |
| operation | 179/193 | 0.927 |
| state | 179/193 | 0.927 |
| evidence_id | **179/193** | 0.927 |

step_no accuracy is lower because a step missing earlier in a plan shifts the numbering of every step after it.

## 4. Sequence (ordering) accuracy

| Metric | Value |
|---|---:|
| Canonical ordering (phase, then operation-table order, then system_id, resource_id) | **32/32** |
| Ordering match when the predicted step set equals the labeled set | **18/18** |

## 5. Remaining sample failure signatures

| Signature | # | Cases |
|---|---:|---|
| missing VERIFY_RECORD_ANONYMIZED analytics_platform (cited) | 7 | case_03, 04, 21, 25, 26, 27, 28 |
| missing VERIFY_RECORD_ABSENT account_service (cited) | 3 | case_02, 04, 28 |
| missing VERIFY_RECORD_ABSENT account_service (empty evidence) | 3 | case_08, 23, 29 |
| missing VERIFY_RECORD_PRESENT security_service (empty evidence) | 2 | case_18, 20 |
| status COMPLETE -> unresolved | 2 | case_02, 04 |
| extra VERIFY_RECORD_ABSENT account_service | 1 | case_17 |

The largest remaining gap is verification of analytics records that are already anonymized. The data offers no reliable subject link for them, so the engine does not invent one.

## 6. Team-made evaluation cases (more than three)

- **30 frozen edge-case fixtures** in an external, read-only copy (`ghost-audit-edge-cases`, freeze violations: none). Result: **28/30 pass**.
  - Fixture 24 fails: expected COMPLETE, got INCOMPLETE. The engine reported a search_service copy that the fixture treats as already handled. This is a conservative failure.
  - Fixture 27 fails: expected NOT_APPLICABLE, got unresolved. A conditional authorization needs semantic review.
  - The fixtures cover backups, legal holds, retention expiry, replicas, catalog-only links, NOT_APPLICABLE classification, tombstones, hashed identifiers, cycles and ambiguous windows.
- **`code/tests/test_holdout.py`**: independently specified holdout cases. They are never built from sample labels and check the full step array: clean tombstone redaction, linkable hash mutation leading to ANONYMIZE, and cycle and retained-source simulation.
- **Full unit/integration suite**: `python3 -m pytest -q code/tests`: **221 passed**.

## 7. Full 518-request invariants

From a fresh run of the final code: 518 requests, 518 results, 518 rows, 0 missing rows, 0 unresolved, **0/518 cases with invariant violations**, and no file-level violations. The checks are: consecutive step_no; allowed phase/operation/state pairs; canonical ordering; FINDING steps cite evidence; REMEDIATION steps have empty evidence; INCOMPLETE verifications have empty evidence; COMPLETE has no findings or remediations; NOT_APPLICABLE has an empty plan; and no deletion of retained records.

## 8. Failures found and improvements made

Unresolved cases on the full dataset dropped **442 -> 207 -> 5 -> 0** across iterations.

1. **rule_12 security-audit retention.** Every labeled sample keeps SECURITY_AUDIT_LOG records (VERIFY_RECORD_PRESENT) and gives no per-record expiry. A missing retention date now means the record is retained. An explicit expired date still blocks. Sample unresolved went from 15 to 5, and status accuracy from 28 to 29 out of 32.
2. **Verification of compliant records.** Labels include VERIFY steps for records that are already compliant, such as VERIFY_RECORD_ABSENT on account_service in 32/32 samples. These steps are now emitted with the readback evidence for COMPLETE cases and with empty evidence for INCOMPLETE cases.
3. **Workflow account attribution.** Most account resources are linked only through deletion_worker DELETE_RECORD activity. The engine now attributes them by global elimination (`Auditor.workflow_accounts`). Exact plans went from 9 to 18 out of 32, and recall from 0.60 to 0.80.
4. **Backups.** A backup that is still PRESENT is treated as a restore risk, so the case is INCOMPLETE with a restore-check plan rather than COMPLETE.
5. **Legal hold.** When a hold is FOUND, the record is retained (VERIFY_RECORD_PRESENT) and is never deleted.
6. **Catalog-only links.** A resource that appears only in the data catalog does not count as proof that subject data exists. It is no longer turned into a finding without a record-level source.
7. **LLM document classification.** evidence_18 is classified as USER_EXPORT (rule_09) and evidence_46 as SUPPORT_ATTACHMENT (rule_06). Both were classified by two OpenAI models (gpt-5.5 and gpt-5.4-mini), and a label is accepted only when the two models agree. The result is cached in `code/prompts/document_classifications.json` with each document's SHA-256 and is replayed offline. This resolved the last unresolved cases.
8. **Release gate.** Rows were previously dropped when the status was None. Combined with the fixes above, the final run has 0 None statuses and writes all 518 rows.

Sample scores between the baseline and final scorecards: exact 9 -> 20, F1 0.657 -> 0.849, evidence-id 159 -> 179, status 29 -> 31. No sample got worse.

## Final-round improvements (after the final-v3 scorecard)

- Spanish/English embedded questions: "si"/"if" after check/verify/know verbs read as "whether", not a condition (fixed sample case_02's status).
- A pre-request "not found" profile lookup no longer attributes that account to the subject (removed an extra step in sample case_17).
- Catalog links count only inside the case's own request window (requested_at..audit_at). This matches the labels: samples omit catalog resources linked in other cases' windows. Full run: case_33 now reports export_1842 from evidence_18 (two-model OpenAI classification USER_EXPORT, cached for offline replay).
- An independent raw-evidence verification of 25 full-run predictions found 20 correct, 1 fixed here (case_33), 4 uncertain, 0 false COMPLETE, 0 future citations. It also refuted 3 "major" flags from a gpt-5.4-mini reviewer (the reviewer mis-read claimed status as predicted status).
- Known remaining gap: 118 full-run rows have no account_service step because no account id is linked by any participant evidence. This costs steps but not statuses.

## Metamorphic labeled evaluation: 1,024 cases

`code/evaluation/metamorphic.py` builds 32 variants of the participant dataset. Each variant shuffles the row order of user_identities, user_audit_log, system_activity, evidence_files and the sample requests. Row order carries no meaning, so every variant keeps the organizers' sample labels as ground truth. The script reruns the whole pipeline for each variant (32 × 32 = 1,024 labeled cases, 2 min 17 s).

| Metric | Value |
|---|---:|
| Status accuracy | 992/1024 (96.9%) |
| Exact full plans | 640/1024 |
| Step precision / recall | 0.883 / 0.819 |
| False COMPLETE · wrongful deletion | 0 · 0 |
| Cases whose answer changed with row order | 0 |

Every variant scored exactly 31/32 statuses and 20/32 exact plans, so the pipeline is deterministic and has no row-order bugs. This tests robustness, not new ground truth; the labels are the same 32.

## Window-coverage audit of all 518 rows

Concept learned from the data: each case's own artifacts are created inside its requested_at..audit_at window. On the samples this concept has precision 1.00 and recall 0.61; the misses are accounts linked only through deletion_worker rows and audit records captured after the window. Applied to the full run, it flagged 2 rows likely missing a step (case_46 tombstone_17; case_264, an already-redacted support message). We investigated 4 more flags; all were false positives from screenshots that show other customers. A cross-validated search for a rule linking the 128 rows without an account step found none better than chance, so those rows are left as they are rather than guessed.
