# qa memory

(append dated lessons; newest last)
- 2026-10-25: Existing harness assets: runs/harness2-demo (+ .txt), runs/harness2-tests.txt (5 tests OK), fixture builders in runs/edge-author/ (build_fixtures.py, build_group1-3.py, runner.py). Holdout tests: code/tests/test_holdout.py. Primary tests: `cd code && ../.venv/bin/python -m pytest -q tests`.
- Baseline samples after retention fix: status 29/32, exact 9/32, P=0.725 R=0.601, false_complete 0, wrongful_deletion 0, unresolved 5.
- 2026-10-25: Harness 2.0 = code/evaluation/harness2.py (+ tests/test_harness2.py, 6 tests). Run: `cd code && ../.venv/bin/python evaluation/harness2.py --dataset ../dataset --label <name>`; diffs vs runs/agents/qa/scorecard-latest.json. Whole run ~18 s (full 518 run is ~11 s, so always run fresh).
- 2026-10-25: Frozen 30 fixtures live at /home/nadeem/Desktop/ghost-audit-edge-cases (freeze.json); runs/edge-author only has builders. Baseline 28/30 (fail 24 screenshot-row state, 27 conditional NA withheld).
- 2026-10-25: Import evaluation/main.py via importlib under another name; plain `import main` from evaluation/ shadows code/main.py.
- 2026-10-25: --llm needs --llm-calls >= 3: gemini_review.review_cases only catches GeminiError, so OpenAIError budget exhaustion crashes run (reported).
- 2026-10-25: Raw-evidence verification of final output.csv (runs/agents/qa/prediction-verification.md): 20/25 correct, case_33 missing export_1842. Each LINK_RESOURCE_IDENTITY row is 7 minutes after one screenshot/PDF and keyed to ONE case window. Build a grep corpus (PNG text = runs/cache/<sha256>-rapidocr-1.4.4-v1.txt, PDF via pdftotext) to verify fast.
- 2026-10-25: Window-coverage audit (runs/agents/qa/window/window_coverage.py, ~8 s): identity-linked artifacts in [requested_at,audit_at] => labeled resources have P=1.00 R=0.61 on samples (accounts + audit_records are the misses by design). Screenshot OCR is whole-file and gives false positives from neighbour rows (other customers, look-alike emails), so always check flagged rows by hand.
