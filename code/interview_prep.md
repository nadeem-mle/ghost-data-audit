# Interview prep: Ghost Data Still Exists

## 60-second pitch
An offline, evidence-first deletion auditor. It parses all 94 evidence files into immutable timestamped facts, resolves current and historical identities, keeps only facts available at audit_at, and applies deletion_rules.csv through a small policy interpreter. It then emits findings, remediation and verification in contract order. Two independent checkers (a plan simulator and a raw-evidence validator) must pass before output.csv is written. LLMs are bounded and auditable: two-model agreement for document classification, cached and replayed offline, plus an advisory reviewer. The prediction run itself makes 0 model calls.

## Likely questions and our answers
- **How do you avoid trusting "COMPLETE" dashboards?** reported_status and activity results are claims. Only readbacks (SQL rows, JSON records, log state lines, screenshots) count as state, and an absence needs a complete table inventory.
- **Time travel?** Every fact has observed_at and available_at. Both must be ≤ audit_at, so later evidence can't change an earlier case.
- **Retention vs deletion?** RETAIN, REDACT and ANONYMIZE come from the rules CSV. The simulator asserts that no retained record is deleted. Wrongful deletion is 0 on the samples.
- **Biggest discovery?** "Unresolved" didn't mean missing data. Three over-strict assumptions blocked 442 → 207 → 5 → 0 cases: a mandatory account readback, a per-record retention date, and treating catalog links as blockers. Each was corrected only after checking it against the 32 labeled samples.
- **Where do LLMs help?** Business documents with no explicit state (a customer statement PDF). gpt-5.5 and gpt-5.4-mini must agree on the policy category. The result is cached against the file hash so runs are reproducible offline.
- **How did you validate?** Harness 2.0: 32 samples (status 31/32, exact 20/32, F1 0.849, 0 false COMPLETE), 30 hand-built edge fixtures (28/30), and 0 invariant violations across 518 rows. A QA agent re-checked 25 predictions against raw files, and an LLM reviewer's three "major" flags were refuted against raw evidence.
- **What's weak?** 118 rows lack an account verification step because nothing links the account id. Analytics records without subject identifiers are skipped rather than guessed. Both cost steps but not statuses.
- **Cost?** 0 model calls at prediction time. Development and QA LLM usage was about 30k tokens, under $0.10 (see evaluation/usage_report.md).
- **How was it built?** Codex built the base pipeline. Claude Code then ran five agents with persistent memories (researcher, implementer, qa, reviewer, output) in parallel. Each wrote its result to runs/agents/<name>/output.md, and improvements were accepted only when the samples strictly improved with no regressions.
