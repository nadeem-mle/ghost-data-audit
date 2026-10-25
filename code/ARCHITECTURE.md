# Architecture

```
dataset/ (requests, identities, audit log, activity, rules, 94 evidence files)
   │
   ▼
[1] Ingest (audit/ingest.py)          SQL→SQLite, JSON paths, logs, PDF text, OCR for images
   │   immutable Facts: source_id, location, system, resource, copy, category, state, time
   │   + replay of cached two-model LLM document classifications (prompts/document_classifications.json)
   ▼
[2] Intent (engine.intent)            deletion authorized? else NOT_APPLICABLE + []
   ▼
[3] Identity (engine.identity)        current + historical emails/phones/hashes, user_id
   ▼
[4] Resource closure                   subject-linked facts, cross-resource refs, workflow-attributed
   │                                   accounts, catalog links inside the case's request window
   ▼
[5] Cutoff filter                      only facts observed AND available at/before audit_at
   ▼
[6] Policy interpreter (engine.Policy) deletion_rules.csv conditions → DELETE/REDACT/ANONYMIZE/RETAIN/BLOCK/DISABLE
   ▼
[7] Planner                            findings → remediation (flows/restores first) → verification,
   │                                   contract order; COMPLETE cites proof, INCOMPLETE plans use ""
   ▼
[8] Independent checks                 simulate.py (apply plan to a copy, fixed point, no wrongful delete)
   │                                   validate_output.py (schema, order, citations ≤ audit_at,
   │                                   ledger-backed claims, raw-file hash recheck)
   ▼
output.csv  (written only when every row is supported and all checks pass)
```

Offline by default: the prediction run makes **0 model calls**. LLMs are used in three bounded, auditable places:

| Where | Model | Role | Effect on output |
|---|---|---|---|
| `classify_documents.py` | OpenAI gpt-5.5 + gpt-5.4-mini | classify context-only business documents against `deletion_rules.csv` | cached only when both models agree; replayed offline, bound to file sha256 |
| `evaluation/llm_review.py` | OpenAI | independent reviewer of finished predictions | advisory only, never edits output |
| `audit/investigator.py` | OpenAI or Gemini (`--agent-model`) | read-only tool-using investigator for one case | advisory; cannot mutate accepted proof |

Development used five Claude Code agents with persistent memories (`agents/` in this archive):
researcher (dated multi-source research), implementer (engine changes measured against samples),
qa (Harness 2.0: samples + 30 fixtures + 518-row invariants), reviewer (read-only gap analysis),
output (packaging and clean-extract reproduction).
