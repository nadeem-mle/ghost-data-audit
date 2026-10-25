"""Measured release workflow. A blocked prediction run still produces honest reports."""
import argparse,subprocess,sys,json,os,time
from pathlib import Path
from datetime import datetime,timezone
from main import run
from evaluation.main import evaluate
from evaluation.reporting import reports
from package_submission import package
ROOT=Path(__file__).resolve().parents[1]
def release(dataset,gemini_model=None):
    os.chdir(ROOT);d=Path(dataset).resolve()
    from audit.model import rows
    counts={name:len(rows(d/name)) for name in ('deletion_requests.csv','sample_deletion_requests.csv','deletion_rules.csv')}
    assert list(counts.values())==[518,32,15],f'Contract/input count disagreement: {counts}'
    run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');rd=ROOT/'runs'/run_id;rd.mkdir(parents=True)
    test=subprocess.run([sys.executable,'-m','pytest','-q','code/tests'],capture_output=True,text=True)
    (rd/'tests.txt').write_text(test.stdout+test.stderr);print(test.stdout)
    if test.returncode:return test.returncode
    (rd/'test-summary.txt').write_text(test.stdout.strip().splitlines()[-1])
    ablations=evaluate(d);start=time.monotonic()
    client=None
    if gemini_model:
        from audit.gemini import GeminiClient
        client=GeminiClient(gemini_model,max_calls=3,retries=0,max_output_tokens=2048,max_input_bytes=24000)
    results,store,summary=run(d,d/'deletion_requests.csv',ROOT/'output.csv',run_dir=rd,gemini_client=client)
    summary['elapsed_seconds']=time.monotonic()-start
    summary['run_id']=run_id;summary['test_summary']=test.stdout.strip().splitlines()[-1]
    (rd/'summary.json').write_text(json.dumps(summary,indent=2))
    (ROOT/'runs/LATEST').write_text(str(rd.relative_to(ROOT)))
    reports(ROOT,rd,ablations,results,store,summary)
    package(rd)
    # Full clean inference is intentionally not labelled successful when proof gaps block it.
    smoke=subprocess.run([sys.executable,'code/evaluation/clean_smoke.py','--archive','upload/code.zip','--dataset',str(d)],capture_output=True,text=True)
    (rd/'clean-smoke.txt').write_text(smoke.stdout+smoke.stderr);print(smoke.stdout)
    if smoke.returncode:return smoke.returncode
    return 2 if summary['unresolved'] else 0
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dataset',default='dataset');p.add_argument('--gemini-model');a=p.parse_args();sys.exit(release(a.dataset,a.gemini_model))
