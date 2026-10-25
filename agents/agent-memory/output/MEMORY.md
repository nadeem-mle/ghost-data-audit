# output memory

(append dated lessons; newest last)
- 2026-10-25: Decision by lead (user asked for full submission-format output): ship output.csv with ALL 518 rows sorted by case_id. Supported rows as-is; still-blocked rows use the engine's best plan (draft) and are listed in runs/agents/output/provisional_cases.csv. Never invent a 4th status. A case with no status at all -> INCOMPLETE with its best-supported findings, never empty COMPLETE.
- Header exactly: case_id,deletion_status,steps_json. Write to project-root output.csv and upload/output.csv.
- 2026-10-25: Final package built from runs/final-20261025T124654Z: 518 rows, 0 unresolved, output sha d626b8f2..., code.zip verified byte-identical on clean --no-llm replay. Package with `cd code && python package_submission.py --run-dir <final run>` (runs/LATEST is stale).
- 2026-10-25: code.zip MUST include code/prompts/document_classifications.json (cached LLM labels); without it, --no-llm cannot reproduce output. The packager previously allowlisted only .py/.md.
- 2026-10-25: Do NOT rerun run_release.py after the hand-written evaluation/usage reports: reporting.py regenerates and overwrites them.
