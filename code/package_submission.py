"""Allowlisted, transactional packaging. Never manufactures transcripts or predictions."""
import argparse,hashlib,json,shutil,tempfile,zipfile,sys,re,os
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FORBIDDEN_NAMES={'.env','do_not_read_in_chat_also_not_include_in_zip.md'}
ARCHIVES={'.zip','.tar','.gz','.tgz','.7z','.rar','.zst'}
SECRET=re.compile(rb'(?:AIza[0-9A-Za-z_-]{30,}|sk-[A-Za-z0-9_-]{24,}|AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def scan(path):
    if SECRET.search(path.read_bytes()):raise ValueError('Possible secret; publication blocked: '+path.name)
def refresh_manifest(directory,run_dir,trace_status='PROVISIONAL: session must be closed and exported'):
    d=Path(directory);rd=Path(run_dir);summary=json.loads((rd/'summary.json').read_text())
    fp=json.loads((rd/'fingerprint.json').read_text())
    files=[p for p in d.iterdir() if p.is_file() and p.name!='MANIFEST.md']
    report_files=[ROOT/'code/evaluation/evaluation_report.md',ROOT/'code/evaluation/usage_report.md',ROOT/'code/interview_prep.md']
    text=f"# Release manifest\n\nRun: `{rd.name}`\n\nGenerated UTC: {datetime.now(timezone.utc).isoformat()}\n\nReadiness: {'READY EXCEPT TRANSCRIPTS' if summary['official_output_written'] else 'BLOCKED'}\n\nPrediction fingerprint: `{fp['fingerprint']}`\n\nContract checkout: `0eddbbd33f682eae0a2770d67412af8a3cf4af20` (see runs/contract.json).\n\nSource/input/config versions are bound in the run fingerprint. The offline predictor uses no generative label prompt; optional bounded advisory triage is recorded separately. Documentation-only changes are not inference runs.\n\nTrace status: {trace_status}\n\nLog cutoff: {datetime.fromtimestamp((d/'log.txt').stat().st_mtime,timezone.utc).isoformat() if (d/'log.txt').exists() else 'MISSING'}\n\nProcessed requests: {summary['requests']}; unresolved: {summary['unresolved']}.\n\n"+('Official output.csv written and validated (sha256 '+summary.get('output_sha256','')+').\n\n' if summary['official_output_written'] else 'No official prediction file exists for this blocked run. Unsupported diagnostic draft remains under the run directory as draft.csv and is excluded from upload/.\n\n')
    text+='## Artifact SHA-256\n\n'+''.join(f'- `{p.name}`: `{sha(p)}`\n' for p in sorted(files))
    text+='\n## Reports SHA-256\n\n'+''.join(f'- `{p.relative_to(ROOT)}`: `{sha(p)}`\n' for p in report_files)
    if (rd/'test-summary.txt').exists():text+='\nTests: '+(rd/'test-summary.txt').read_text().strip()+'\n'
    text+='\n## Prediction provenance\n\nFingerprint-file SHA-256: `'+sha(rd/'fingerprint.json')+'`\n\n'
    text+='| Prediction source | SHA-256 |\n|---|---|\n'+''.join(f'| {name} | `{value}` |\n' for name,value in sorted(fp['sources'].items()))
    text+='\nConfiguration: `'+json.dumps(fp['config'],sort_keys=True)+'`\n\n'
    text+='| Participant input | SHA-256 |\n|---|---|\n'+''.join(f'| {name} | `{value}` |\n' for name,value in sorted(fp['inputs'].items()))
    text+='\nPackage validation: archive contents inspected, secret-pattern scan passed, temporary extraction completed. '+('Full-data run completed with 0 unresolved; output.csv validated.\n' if summary['official_output_written'] else 'Clean reproduction is a smoke test plus supported synthetic fixtures; full-data run remains blocked, not claimed successful.\n')
    if (d/'log.txt').exists():
        headings=re.findall(r'^## \[(.*?)\]',(d/'log.txt').read_text(),re.M)
        if headings:text+='\nLast logged entry timestamp (session still provisional): '+headings[-1]+'\n'
    (d/'MANIFEST.md').write_text(text)

def package(run_dir=None):
    if run_dir is None:
        latest=ROOT/'runs/LATEST';assert latest.exists(),'Run code/run_release.py first';run_dir=ROOT/latest.read_text().strip()
    rd=Path(run_dir).resolve();summary=json.loads((rd/'summary.json').read_text())
    from audit.provenance import fingerprint
    frozen=json.loads((rd/'fingerprint.json').read_text())
    actual=fingerprint(ROOT/'dataset',frozen['config']['media'],frozen['config']['adaptive'])
    if actual['fingerprint']!=frozen['fingerprint']:raise ValueError('stale inference: source/input/config changed; rerun release before packaging')
    for name in ('evaluation_report.md','usage_report.md'):
        p=ROOT/'code/evaluation'/name;assert p.exists() and p.stat().st_size>500,'Missing complete report: '+name
    assert (ROOT/'code/interview_prep.md').exists(),'Interview missing'
    stage=Path(tempfile.mkdtemp(prefix='upload-stage-',dir=ROOT/'runs'))
    try:
        with zipfile.ZipFile(stage/'code.zip','w',zipfile.ZIP_DEFLATED) as z:
            readme=ROOT/'code/README.md';scan(readme);z.write(readme,'README.md')
            env_example=ROOT/'code/.env.example'
            if env_example.exists():scan(env_example);z.write(env_example,'.env.example')
            for name in ('evaluation_report.md','usage_report.md'):
                rp=ROOT/'code/evaluation'/name;scan(rp);z.write(rp,'evaluation/'+name)
            for p in sorted((ROOT/'code').rglob('*')):
                rel=p.relative_to(ROOT)
                if not p.is_file() or '__pycache__' in p.parts or '.pytest_cache' in p.parts or 'runs' in rel.parts:continue
                if p.name in FORBIDDEN_NAMES:continue
                cached_prompt=p.suffix=='.json' and rel.parts[:2]==('code','prompts')
                if p.suffix not in ('.py','.md') and p.name not in ('requirements.txt','.env.example') and not cached_prompt:continue
                assert not any(part in ('dataset','.venv','node_modules') for part in rel.parts)
                assert p.suffix not in ARCHIVES;scan(p);z.write(p,str(rel))
            # Development agent definitions and their memories (markdown only; scanned for secrets).
            for p in sorted((ROOT/'.claude').rglob('*.md')) if (ROOT/'.claude').exists() else []:
                rel=p.relative_to(ROOT/'.claude')
                if p.name in FORBIDDEN_NAMES:continue
                scan(p);z.write(p,str(Path('agents')/rel))
            for extra in ('CODEX_HANDOFF.md',):
                if (ROOT/extra).exists():scan(ROOT/extra);z.write(ROOT/extra,extra)
        with zipfile.ZipFile(stage/'code.zip') as z:
            assert z.testzip() is None
            names=z.namelist();assert 'README.md' in names and 'code/main.py' in names
            assert {'evaluation/evaluation_report.md','evaluation/usage_report.md','code/prompts/document_classifications.json'}<=set(names)
            assert not any(Path(n).name in FORBIDDEN_NAMES for n in names),'secret file in zip'
            assert all(not any(t in Path(n).parts for t in ('dataset','runs','__pycache__')) and Path(n).suffix not in ARCHIVES for n in names)
            with tempfile.TemporaryDirectory(prefix='ghost-clean-') as tmp:z.extractall(tmp)
        log=ROOT/'log.txt'
        if log.exists():scan(log);shutil.copyfile(log,stage/'log.txt')
        shutil.copyfile(ROOT/'code/interview_prep.md',stage/'INTERVIEW.md')
        if (ROOT/'PROJECT_DETAILS.md').exists():shutil.copyfile(ROOT/'PROJECT_DETAILS.md',stage/'PROJECT_DETAILS.md')
        if summary['official_output_written']:
            from validate_output import validate
            assert sha(ROOT/'output.csv')==summary['output_sha256'],'output differs from measured run'
            assert validate(ROOT/'dataset',ROOT/'output.csv')==summary['requests'];shutil.copyfile(ROOT/'output.csv',stage/'output.csv')
        # Unsupported predictions stay under runs/; never package them as upload files.
        text=f"""# Upload instructions

Readiness: **{'READY EXCEPT TRANSCRIPTS' if summary['official_output_written'] else 'BLOCKED'}**.

Code: built and tested; predictions: {summary['requests']} processed, {summary['unresolved']} unresolved. {'output.csv is validated and ready to upload.' if summary['official_output_written'] else 'The diagnostic draft stays under runs/ and must not be uploaded as predictions.'} Optional LLM steps are bounded; the prediction run itself used {summary.get('model_calls',0)} model calls.

Artifacts live at `{ROOT}/upload/`: code.zip, log.txt, INTERVIEW.md, MANIFEST.md, and {'output.csv' if summary['official_output_written'] else 'no prediction CSV (blocked)'}.

Rebuild (tested):

```bash
cd '{ROOT}'
.venv/bin/python code/run_release.py --dataset dataset
```

Submission: https://www.hackerrank.com/contests/hackerrank-orchestrate-october26/challenges/ghost-data-still-exists

Map code.zip to code, a validated output.csv to predictions, and log.txt to README's `chat_transcript` field. A separate agent-trace.zip is required by trace instructions; use the actual form's trace field or seek platform guidance if it differs. Never nest it inside code.zip.

Transcripts remain provisional. Exit/export the relevant challenge sessions first, then run the standalone command in runs/FINALIZE.sh. It refreshes transcripts and manifest without inference or reopening a session. Other planning/review chat exports must be supplied if used; none were supplied here.

Inspect MANIFEST.md before uploading. Confirm acceptance on the platform; then open INTERVIEW.md. Interview timing/camera requirements have not been verified and must be checked on the platform.
"""
        (stage/'UPLOAD.md').write_text(text)
        refresh_manifest(stage,rd)
        old=ROOT/'upload'
        if old.exists():
            backup=ROOT/'runs'/('older-upload-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));old.rename(backup)
            (backup/'STALE.md').write_text('Older release, not current. Retained during refresh.\n')
        stage.rename(old);print('Packaged',old,'readiness:', 'BLOCKED' if summary['unresolved'] else 'READY EXCEPT TRANSCRIPTS')
    except Exception:
        shutil.rmtree(stage,ignore_errors=True);raise
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run-dir');a=p.parse_args();package(a.run_dir)
