"""Run after closing/exporting explicitly identified challenge sessions."""
import argparse,json,zipfile,shutil,tempfile
from pathlib import Path
from package_submission import ROOT,scan,refresh_manifest

def finalize(traces,closed,run_dir=None):
    if not closed:raise ValueError('Exit/export all selected sessions first; pass --closed only afterward')
    assert traces,'At least one explicitly identified trace is required'
    upload=ROOT/'upload';assert upload.exists(),'Build package first'
    selected=[]
    for name in traces:
        p=Path(name).resolve()
        if not p.is_file() or p.suffix not in ('.jsonl','.json','.txt','.md','.db'):raise ValueError('Expected explicit structured session/export file')
        if p.name in ('auth.json','config.json','config.toml','session_index.jsonl','.env') or 'credential' in p.name.lower():raise ValueError('Configuration/credential/account index is not a challenge trace')
        scan(p);selected.append(p)
    scan(ROOT/'log.txt')
    with tempfile.TemporaryDirectory(prefix='ghost-trace-',dir=ROOT/'runs') as temp:
        staged=Path(temp);archive=staged/'agent-trace.zip'
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for i,p in enumerate(selected):z.write(p,f'agent-trace/codex/session-{i+1}/{p.name}')
            z.writestr('agent-trace/EXPORT.md','Selected challenge sessions supplied explicitly by user after exit/export. Original formats preserved. No automated redaction was performed; source files unchanged. User must review privacy and confirm inclusion of every challenge session before upload.\n')
        with zipfile.ZipFile(archive) as z:assert z.testzip() is None
        shutil.copyfile(archive,upload/'agent-trace.zip')
    shutil.copyfile(ROOT/'log.txt',upload/'log.txt')
    rd=Path(run_dir) if run_dir else ROOT/(ROOT/'runs/LATEST').read_text().strip()
    refresh_manifest(upload,rd,'EXPORTED after user-attested closure; explicit challenge files only. Review completeness/privacy before upload.')
    print('Finalized trace copies and manifest; predictions unchanged. Readiness remains BLOCKED if proof gaps remain.')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--trace',action='append',required=True);p.add_argument('--closed',action='store_true');p.add_argument('--run-dir');a=p.parse_args();finalize(a.trace,a.closed,a.run_dir)
