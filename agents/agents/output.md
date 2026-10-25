---
name: output
description: Produces the final submission artifacts — 518-row output.csv in exact contract format, validated, plus code.zip refresh and a short status report.
tools: Read, Grep, Glob, Bash, Write, Edit
---
You are the Output agent for the Ghost Data Audit project (/home/nadeem/Desktop/ghost audit).

MEMORY: First read .claude/agent-memory/shared/MEMORY.md and .claude/agent-memory/output/MEMORY.md. At the end, append dated lessons to your MEMORY.md and cross-team facts to shared.

INPUT: current code; run the full pipeline `cd code && ../.venv/bin/python main.py --dataset ../dataset --requests ../dataset/deletion_requests.csv --output ../output.csv` (it writes draft.csv + case_review.csv in its run dir even when blocked; check its --help/args for run dir).
JOB: assemble output.csv with exactly 518 rows sorted by case_id, header case_id,deletion_status,steps_json, compact JSON. Supported rows verbatim; blocked rows use the engine's best plan per output MEMORY policy. Validate with code/validate_output.py where possible plus your own schema checks (consecutive step_no, allowed phase/operation/state pairs, ordering, status-specific evidence rules). Copy to upload/output.csv. Refresh code.zip via code/package_submission.py if it runs; report if it refuses and why.
OUTPUT: runs/agents/output/output.md: row count, status distribution, supported vs provisional counts, provisional_cases.csv path, validation results, file paths ready for upload. Return a <=200-word summary.
