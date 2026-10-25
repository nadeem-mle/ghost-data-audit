# Applied research: measured effect

Before: `20261025T113354483926Z`. After: `20261025T114601727402Z`. Same518 request rows,94 manifest inputs,15 policy rules and32 public labels. Prediction/input fingerprints are retained in each run. No organizer data, case-ID rules or guessed retention periods were added.

|Measure|Before|After|
|---|---:|---:|
|Unresolved full-data requests|442|207|
|Requests with no unresolved obligation in supplied scope|76|311|
|Public status matches|23/32|28/32|
|Public exact ordered plans|9/32|9/32|
|Public unresolved requests|28/32|15/32|
|Public false COMPLETE labels|0|0|
|Public wrongful deletion actions|0|0|
|Primary tests|204 passed|210 passed in 0.50s|

## General code correction

The official contract applies policy to relevant subject-linked resources. It does not explicitly require every case to expose an account ID. Removed the unconditional missing-account blocker. A search, export or retained record can now be audited without fabricating a separate account resource.

This is not an unrestricted closed-world absence assumption: no observations still yields unresolved, not empty COMPLETE; a resource explicitly linked by participant evidence still needs a cutoff-eligible state readback. Source failures, conflicting copies, retention uncertainty and unsafe input remain blocking. Scope limitations are recorded per case. Completion is bounded to the supplied participant evidence, not undisclosed production infrastructure.

Added six independent regressions for exact secondary-only plans, secondary-only verification, empty evidence, explicit missing links, cross-resource references and real CLI/independent-validator integration. Existing safety assertions were retained. All210 primary and archive tests passed.

## What improved, and what did not

236 previously blocked cases became supported under the revised supplied-evidence scope. 1 previously supported case became blocked by the stronger explicit-link check: `case_46` links a tombstone whose eligible state is not established. Net reduction: 235 unresolved cases. The new blocker is retained rather than hidden to improve the count.

Public status agreement improved, but exact arrays, step precision/recall and verification coverage did not improve. Removing an added assumption is a correctness change; a lower unresolved count alone does not establish better hidden accuracy or prove full plan completeness. Full-data labels are unavailable. The release remains BLOCKED with no official output.csv.

Retention joins across eligible observations of the same logical record were already implemented and were retained. Research did not supply a new applicable retention schedule or justify guessing an expiry from another record. A raw JSON/log key review found retention_until and retained_until, but no newly declared category-wide authoritative schedule. More broad web research will not manufacture case facts. The next useful work is targeted participant-evidence interpretation, retention applicability and linked-resource extraction.

## Remaining request blockers

203 requests have unresolved security-retention applicability; three explicit linked resources lack eligible state proof; one business document needs classification, one backup lacks an eligible explicit restore-control state and one legal hold lacks established applicability. Counts overlap. One case also has no eligible subject state observation. All207 blocked requests and exact reasons are exported in root pending_requests.csv and this run's case_review.csv.

The external30-scenario project remains stopped at the user's request; its holdout was not used. These six primary regressions do not claim to complete that cancelled evaluation. This final full-data attempt used0 provider calls. No additional challenge data was exported.
