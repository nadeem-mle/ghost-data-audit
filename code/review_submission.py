"""Independent artifact inventory and readiness review; never predicts a rank."""
import argparse,ast,hashlib,json,zipfile,re
from pathlib import Path
from package_submission import SECRET
from audit.provenance import fingerprint

def review(root,run_dir=None):
    root=Path(root).resolve();rd=Path(run_dir) if run_dir else root/(root/'runs/LATEST').read_text().strip()
    summary=json.loads((rd/'summary.json').read_text());fp=json.loads((rd/'fingerprint.json').read_text())
    findings=[];inventory=[];upload=root/'upload'
    def add(check,ok,detail):findings.append(dict(check=check,passed=bool(ok),detail=detail))
    actual=fingerprint(root/'dataset',fp['config']['media'],fp['config']['adaptive'])
    add('prediction fingerprint',actual['fingerprint']==fp['fingerprint'],'Source/input/config must match the measured run')
    add('all requests accounted',summary['requests']==518,f"{summary['requests']}/518 processed")
    add('proof readiness',summary['unresolved']==0,f"{summary['unresolved']} requests unresolved")
    add('official predictions',(upload/'output.csv').exists() and summary['official_output_written'],'Official output.csv must exist and be supported')
    add('closed-session traces',(upload/'agent-trace.zip').exists(),'Current session cannot self-certify closure')
    archive=upload/'code.zip'
    add('code archive',archive.exists(),'Runnable code archive is required')
    if archive.exists():
        with zipfile.ZipFile(archive) as z:
            add('archive CRC',z.testzip() is None,'CRC checks every member')
            names=z.namelist();add('unique archive members',len(names)==len(set(names)),'No duplicate paths')
            forbidden=[]
            for name in names:
                path=Path(name)
                if path.is_absolute() or '..' in path.parts or any(p in ('dataset','runs','.venv','__pycache__') for p in path.parts) or path.suffix.lower() in ('.zip','.tar','.gz','.json','.jsonl','.csv','.sql','.log'):forbidden.append(name)
                raw=z.read(name);add('secret-pattern scan '+name,not SECRET.search(raw),'Pattern screening is not a comprehensive privacy certification')
                local=root/'code/README.md' if name=='README.md' else root/name
                add('source match '+name,local.is_file() and raw==local.read_bytes(),'Archive must match current reviewed source')
                text=raw.decode('utf-8');entry=dict(path=name,lines=len(text.splitlines()),words=len(text.split()),sha256=hashlib.sha256(raw).hexdigest())
                if path.suffix=='.py':ast.parse(text,filename=name)
                inventory.append(entry)
            add('archive exclusions',not forbidden,repr(forbidden))
            for required in ('README.md','code/main.py','code/evaluation/evaluation_report.md','code/evaluation/usage_report.md','code/interview_prep.md'):
                add('required '+required,required in names,'Contract-required source/report')
    for name in ('log.txt','INTERVIEW.md','UPLOAD.md','MANIFEST.md'):
        p=upload/name;add('artifact '+name,p.is_file(),'Required supporting artifact')
        if p.is_file():
            raw=p.read_bytes();text=raw.decode('utf-8');inventory.append(dict(path='upload/'+name,lines=len(text.splitlines()),words=len(text.split()),sha256=hashlib.sha256(raw).hexdigest()))
            add('secret-pattern scan '+name,not SECRET.search(raw),'Manual privacy review remains necessary')
    if (upload/'log.txt').exists():add('authentic log copy',(upload/'log.txt').read_bytes()==(root/'log.txt').read_bytes(),'Original append-only log is preserved; no invented history')
    if (upload/'INTERVIEW.md').exists():
        add('interview matches source',(upload/'INTERVIEW.md').read_bytes()==(root/'code/interview_prep.md').read_bytes(),'Generated from actual measured run')
        add('interview length',600<=len((upload/'INTERVIEW.md').read_text().split())<=800,'Requested 600–800 words')
    if (upload/'MANIFEST.md').exists():
        manifest=(upload/'MANIFEST.md').read_text()
        for p in upload.iterdir():
            if p.is_file() and p.name!='MANIFEST.md':add('manifest checksum '+p.name,hashlib.sha256(p.read_bytes()).hexdigest() in manifest,'Byte consistency, not accuracy')
    result={'run_id':rd.name,'readiness':'GREEN' if all(f['passed'] for f in findings) else 'BLOCKED','checks':findings,'inventory':inventory,'ranking':'NOT ESTIMATED: hidden labels, judge scores, interview and competitors are unavailable'}
    (rd/'artifact-review.json').write_text(json.dumps(result,indent=2))
    text=f"# Submission review\n\nRun: `{rd.name}`. Readiness: **{result['readiness']}**. This is an evidence-based local review, not a prediction of leaderboard rank. Every archived text file was decoded and inventoried; every Python member was parsed. Automated counts and structural checks do not establish complete semantic correctness.\n\n"
    text+='| Check | Result | Meaning |\n|---|---|---|\n'+''.join(f"| {f['check']} | {'PASS' if f['passed'] else 'BLOCKED'} | {f['detail']} |\n" for f in findings)
    text+='\n## Complete text-member inventory\n\n| File | Lines | Words | SHA-256 |\n|---|---:|---:|---|\n'+''.join(f"| {i['path']} | {i['lines']} | {i['words']} | `{i['sha256']}` |\n" for i in inventory)
    text+='\n## Semantic assessment\n\nThe published blocked status is justified by unresolved evidence and the missing supported prediction file. A perfect status score on public examples does not establish plan accuracy. No local test can establish first place. The development summary is an authored explanation, not a replacement for an authentic transcript. Harness² demo/upstream tests do not validate this audit solution against HackerRank. Manual privacy/export review and official platform acceptance remain outside this local check.\n'
    (root/'REVIEW.md').write_text(text)
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',default=Path(__file__).resolve().parents[1]);a=p.parse_args();result=review(a.root);print(result['readiness']);print('\n'.join(f["check"]+': '+f['detail'] for f in result['checks'] if not f['passed']));raise SystemExit(0 if result['readiness']=='GREEN' else 2)
