# reviewer memory

(append dated lessons; newest last)
- 2026-10-25: Test changes in scratch: `PYTHONPATH=code .venv/bin/python code/main.py --no-llm --run-dir <scratch> --output <scratch>/x.csv`, with the OCR cache copied to <scratch>/runs/cache. Store's cache path is relative to the current directory. To test eligibility variants, monkeypatch `model.Fact.eligible` in a script.
- 2026-10-25: Gold (sample_output) never cites a file captured after audit_at. Relaxing eligibility to observed_at-only made samples worse (FP 1->32). Later-captured files are useful only for discovering resources (blank-evidence VERIFY steps in INCOMPLETE cases).
- 2026-10-25: Accounts and anonymized analytics with no identifiers are linked only by deletion_worker jobs near reported_at: accounts about reported-60..75 min, analytics about reported-29 min, follow-up "received final result" jobs at reported+40..120 min. 437/518 full cases share reported_at, so the link needs elimination plus a tie-break.
- 2026-10-25: Unlinkable gold resources (in no evidence at all): account_004, audit_record_6645, audit_record_5569. Don't chase them.
