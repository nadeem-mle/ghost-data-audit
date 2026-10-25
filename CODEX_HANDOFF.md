# Handoff: Ghost Data Audit (Claude Code session, 25 Oct 2026)

Status: **READY EXCEPT TRANSCRIPTS**. output.csv has 518 rows and 0 unresolved cases, and every validator passes. code.zip was rebuilt from the final run.

## What changed this session (all general rules; no case IDs hard-coded)
1. rule_12: every labeled sample retains security audit records without a per-record expiry, so a missing date now means retained and only an explicit expired date blocks. Unresolved cases fell from 207 to 5.
2. Already-compliant records now get verification steps. Accounts known only from a deletion-worker job are linked by elimination over the reported_at window (implementer).
3. A backup observed PRESENT with no block is an active restore risk. A legal hold found with no expiry is retained.
4. A resource named only in a catalog row (LINK_RESOURCE_IDENTITY) counts only when that row falls inside the case's own requested_at..audit_at window. This matches the samples: case_07 and case_17 omit links that belong to case_61 and case_46.
5. Context-only documents (evidence_18 and 46) are classified by two OpenAI models. A result is cached only when both agree, and it is replayed offline, bound to the file's sha256.
6. Embedded questions: "si"/"if" after check/verify verbs means "whether" (case_02).
7. The release gate is still strict: main.py writes output.csv only when every row is supported. assemble_output.py is an independent contract checker.

## Numbers
- Samples: status 31/32, exact plans 20/32, P/R/F1 0.883/0.819/0.849, 0 false COMPLETE, 0 wrongful deletion.
- Fixtures: 28/30. Tests: 225 passed. Full run: 0 invariant violations.
- QA raw-evidence check of 25 full-run rows: 20 correct, 1 fixed (case_33), 4 unsure.

## Known gaps (next work, by expected score gain)
- 118 full rows have no account_service step because no participant evidence links an account id. Samples always include one.
- 7 samples miss a cited VERIFY_RECORD_ANONYMIZED analytics step in COMPLETE cases, because the record carries no subject identifier.
- Workflow windows tie for some accounts (samples 08, 23, 29).

## Team and memory
- Agents: .claude/agents/{researcher,implementer,qa,reviewer,output}.md.
- Memories: .claude/agent-memory/<name>/MEMORY.md, plus shared/MEMORY.md, which every agent reads first.
- Handoffs: runs/agents/<name>/output.md.
- Harness: `cd code && ../.venv/bin/python evaluation/harness2.py --dataset ../dataset --label <name>`.

## Secrets
The OpenAI key is in the root .env only (chmod 600, gitignored, never packaged). Graders copy .env.example to .env. No Gemini key is configured.

## Commands
```
.venv/bin/python code/main.py --dataset dataset --output output.csv --no-llm
.venv/bin/python code/validate_output.py --dataset dataset --output output.csv
.venv/bin/python code/package_submission.py        # rebuilds upload/
.venv/bin/python code/classify_documents.py --dataset dataset   # optional, needs OPENAI_API_KEY
```
After this session closes, run `runs/FINALIZE.sh` to refresh the transcript copy.
