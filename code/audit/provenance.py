"""Fingerprint prediction code, inputs, parser configuration, and dependency versions."""
from pathlib import Path
import hashlib,json,sys,importlib.metadata

def fingerprint(dataset,media=True,adaptive=True):
    source=Path(__file__).resolve().parents[1]
    # Documentation changes do not change inference identity.
    paths=[source/'main.py',source/'validate_output.py']+list((source/'audit').glob('*.py'))
    sources={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
    inputs={str(p.relative_to(Path(dataset))):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(dataset).rglob('*')) if p.is_file() and p.name not in ('sample_output.csv','output.csv')}
    versions={name:importlib.metadata.version(name) for name in ('rapidocr_onnxruntime','onnxruntime','PyMuPDF','pytest')}
    config={'media':media,'adaptive':adaptive,'parser':'typed-v3','ocr':'rapidocr-1.4.4','schema':1,'prompt':'no-generative-prompt','python':sys.version.split()[0],'versions':versions}
    body={'sources':sources,'inputs':inputs,'config':config};body['fingerprint']=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest();return body
