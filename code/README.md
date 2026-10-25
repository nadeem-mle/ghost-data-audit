# Ghost Data Audit

An offline evidence auditor and simulated remediation planner. It never deletes live data. For each deletion request, it reconstructs every copy of the subject's data from the supplied evidence and writes `case_id,deletion_status,steps_json`. The status is one of COMPLETE, INCOMPLETE or NOT_APPLICABLE, and steps_json holds an ordered FINDING / REMEDIATION / VERIFICATION plan.

The final submitted run (`--no-llm`) produced all 518 rows with 0 unresolved, and `validate_output.py` passed. Measured results are in `evaluation/evaluation_report.md`. Token usage and cost are in `evaluation/usage_report.md`. Both reports are also included under `code/evaluation/`.

## Setup

Requires Python 3.10+ and Linux (tested). Place the participant `dataset/` folder next to `code/` at the archive root. The dataset is not included in this zip.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r code/requirements.txt
cp code/.env.example .env      # only needed for optional LLM steps; then set OPENAI_API_KEY in .env
```

Never commit or zip `.env`.

## Run (reproduces the submitted output.csv; offline, 0 model calls)

```bash
python3 code/main.py --dataset dataset --output output.csv --no-llm
python3 code/validate_output.py --dataset dataset --output output.csv
python3 -m pytest -q code/tests
```

(Use `.venv/bin/python` in place of `python3` if you installed into the venv.) `--no-llm` replays the cached two-model document classifications in `code/prompts/document_classifications.json`, so no API key is needed. `main.py` exits with code 2 and writes no output.csv if any case is unresolved. Per-case JSON, `draft.csv` and `case_review.csv` are written under `runs/<run-id>/`.

## Optional: refresh the LLM document classifications (needs OPENAI_API_KEY)

```bash
python3 code/classify_documents.py --dataset dataset --models openai:gpt-5.5,openai:gpt-5.4-mini
```

Two models classify each document that cannot be classified by rules. A label is used only when both models agree. Results are cached with the document SHA-256 so that later `--no-llm` runs replay them offline.

## Evaluation

```bash
cd code && python3 evaluation/harness2.py --dataset ../dataset --label check
```

This runs the scorecard: 32 labeled samples, 30 team-made fixtures, and full-518 invariants. The fixtures live in a frozen external copy (`../ghost-audit-edge-cases`) that is not in this zip, so in a clean checkout use `pytest` (which includes the `test_holdout.py` team cases) and `evaluation/main.py --dataset ../dataset --single` instead.

## How it works

`audit/ingest.py` reads the entire manifest, confines paths to the dataset, parses structured observations, joins log lines through trace IDs, retains PDF pages and OCR regions, and records source coverage. `model.py` keeps immutable facts and separate observation/availability times. `engine.py` performs exact identifier retrieval, cutoff filtering, resource closure, copy-specific reconstruction, runtime policy interpretation, proof-ledger construction, and canonical planning. It never imports sample outputs. Policy IDs are provenance, not behavior selectors.

`safe_sql.py` loads only snapshot DDL/DML in an isolated process. SQLite authorizers, statement restrictions, resource limits and timeouts reject attachments, arbitrary functions and filesystem access. `simulate.py` checks final simulated states, cycles, retention and idempotency; this simulation does not create observations or evidence IDs. `validate_output.py` independently checks wire schema, enum/state pairs, temporal citations, plan coverage and retention protection.

The bounded investigator performs read-only targeted source inspection, with an eight-call cap and repeated-query detection. The deterministic inspector can be supplemented by optional Gemini gap triage or the model-directed tool loop in audit/investigator.py. Quotes must match the supplied case/time-scoped source unit; advisory text does not change facts or release eligibility. An LLM is not allowed to select final labels or supply unsupported evidence.

## Known limitations

Some readbacks omit their lookup subject; anonymous records lack prior ownership links; several business documents do not expose contract resource IDs or explicit restore controls. The auditor records these gaps instead of deriving resource IDs from user IDs, timestamps, names or sample labels. It cannot certify completeness of all evidence scope. Conditions without supplied follow-up treatment, missing required retained records, and same-time conflicts remain unresolved. Current retention support is deliberately conservative and does not implement unsupplied expired-record policy.

Screenshot parsing uses application content, header/row geometry and exact identifiers. It does not comprehensively interpret every business UI or every possible language. OCR confidence is a routing aid, not proof. Transport retry/accounting have mocked tests, and direct Gemini/gap-triage results are recorded separately. The optional model-directed investigator searches already admitted facts; it does not implement unrestricted semantic extraction or automatically admit new model claims. No hidden-label accuracy, live deletion, upload acceptance, deadline, or interview timing is claimed.

## Artifacts and transcripts

The release runner creates measured Markdown evaluation/usage reports and the interview guide, then refreshes an allowlisted upload directory. `log.txt` is authentic append-only session history. It is provisional until the coding session closes. Run the generated `runs/FINALIZE.sh` afterward to copy only explicitly identified relevant traces and refresh transcript hashes. Review any staged trace for privacy and include other challenge planning/review sessions if used. The finalizer never starts a new AI session or changes predictions.

The official contract is frozen under `official/`; its unmodified README is preserved. Recheck upstream before release without silently changing inputs.

## Model-directed read-only tools

Set `GEMINI_API_KEY` securely in the environment; never hardcode a credential.
The model selects `search_identifiers`, `trace_resource`, `read_evidence`, or
`inspect_conflict`, observes the result, and chooses a follow-up or finish.
Each tool has an exact argument schema. Sources remain subject/cutoff scoped;
there is no arbitrary SQL, shell, filesystem or label-writing tool.
The loop allows at most eight tools and nine model calls, repeated-query
termination, and a 90-second budget checked between calls (a pending call can
last up to the transport timeout). Results are stored in tool-agent.json.
Grounded observations remain review evidence and cannot clear proof blockers.

```bash
# Live test sends only locally authored synthetic demo data:
.venv/bin/python code/agent_demo.py --model gemini-3.5-flash-lite
# Opt-in actual case investigation; sends scoped evidence to Google:
.venv/bin/python code/main.py --dataset dataset --agent-model gemini-3.5-flash-lite --agent-case case_01 --run-dir runs/agent-case
```

The full release defaults to the offline baseline. Historical three-case Gemini
triage and live synthetic tool testing are separate measured phases, not claims
of model-directed investigation over all 518 requests. See
evaluation/agent_architecture.md and evaluation/ocr_review.md.

## Scope correction after current-practice review

The auditor applies obligations to cutoff-eligible subject-linked resources in
the supplied participant evidence. It does not require a fictional account ID
in every case. Every explicitly linked resource still needs eligible state
proof; absent observations cannot produce an empty COMPLETE certificate.
The per-case scope diagnostic states this boundary. This does not certify a
complete inventory of undisclosed real-world systems. Retention remains based
on supplied applicable evidence; web guidance never supplies a missing expiry.
See evaluation/research_application.md for the measured before/after result.
