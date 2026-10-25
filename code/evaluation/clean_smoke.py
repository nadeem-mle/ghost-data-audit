"""Archive-only tests and a cold, text-only externally supplied dataset smoke test."""
import argparse,tempfile,zipfile,subprocess,sys,json
from pathlib import Path

def smoke(archive,dataset):
    with tempfile.TemporaryDirectory(prefix='ghost-archive-') as tmp:
        root=Path(tmp)
        with zipfile.ZipFile(archive) as z:z.extractall(root)
        test=subprocess.run([sys.executable,'-m','pytest','-q','code/tests'],cwd=root,capture_output=True,text=True)
        print('Extracted archive tests:',test.stdout.strip());assert test.returncode==0,test.stdout+test.stderr
        cli=subprocess.run([sys.executable,'code/main.py','--help'],cwd=root,capture_output=True,text=True);assert cli.returncode==0
        # Actual complete participant run, with visual evidence deliberately disabled, tests safe failure.
        inference=subprocess.run([sys.executable,'code/main.py','--dataset',str(Path(dataset).resolve()),'--requests',str(Path(dataset).resolve()/'sample_deletion_requests.csv'),'--text-only','--output','output.csv'],cwd=root,capture_output=True,text=True)
        assert inference.returncode==2,inference.stdout+inference.stderr
        assert not (root/'output.csv').exists()
        print('Clean smoke: tests + CLI + cold text-only public-sample run; expected nonzero release gate. Not a successful full-data clean reproduction.')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--archive',required=True);p.add_argument('--dataset',required=True);a=p.parse_args();smoke(a.archive,a.dataset)
