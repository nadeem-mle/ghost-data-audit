"""Classify context-only business documents with two LLMs; cache only agreed answers.

The cache (prompts/document_classifications.json) is bound to each file's sha256
and replayed offline by Store.ingest, so `main.py --no-llm` reproduces the run.
Usage: python3 code/classify_documents.py --dataset dataset [--models openai:gpt-5.5,openai:gpt-5.4-mini]
"""
import argparse,csv,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from audit.ingest import Store
from main import model_client

CACHE=Path(__file__).resolve().parent/'prompts'/'document_classifications.json'
PROMPT=("You classify one evidence document for a GDPR deletion audit. Choose exactly one data_category from the policy rules, "
        "or NONE if the document is not a stored copy of a person's personal data. Use only the text given.\n"
        "POLICY RULES:\n{rules}\nCATALOG RESOURCES NAMED IN THIS DOCUMENT: {links}\n"
        "DOCUMENT (file {file_id}, source {source}, captured {captured}):\n{text}\n"
        'Return JSON: {{"data_category": str, "rule_id": str, "required_action": str, "confidence": number, "reason": str}}')

def catalog_labels(a):
    """Human-readable labels a catalog row gives a resource, e.g. 'export_1842 (NST-2026-0718-1842)'."""
    import re
    return [x for x in re.findall(r'\(([^()]+)\)',a['details']) if len(x)>=6]

def classify(dataset,models):
    store=Store(Path(dataset),media=True).ingest()
    rules=list(csv.DictReader(open(Path(dataset)/'deletion_rules.csv',encoding='utf-8')))
    categories={r['data_category'] for r in rules}|{'NONE'}
    manifest={m['file_id']:m for m in store.manifest}
    cache=json.loads(CACHE.read_text()) if CACHE.exists() else {}
    usage={}
    for c in store.coverage:
        if c['status']!='context_only':continue
        if cache.get(c['file_id'],{}).get('sha256')==c['sha256']:continue
        m=manifest[c['file_id']];text=store.documents.get(c['file_id'],'')
        if len(text.strip())<30:continue  # nothing readable to classify; stays unresolved
        links=[{'system':a['target_system'],'resource_id':a['resource_id'],'label':lab} for a in store.activities
               if a['event_type']=='LINK_RESOURCE_IDENTITY' for lab in catalog_labels(a) if lab in text]
        prompt=PROMPT.format(rules=json.dumps(rules),file_id=c['file_id'],source=m.get('origin',''),captured=m['captured_at'],text=text[:8000],links=json.dumps(links))
        answers={}
        for spec in models:
            client=model_client(spec,max_calls=1,retries=0,max_output_tokens=3000,max_input_bytes=24000)
            answers[spec]=client.generate_json(prompt)
            for k,v in client.usage.items():usage.setdefault(spec,{}).setdefault(k,0);usage[spec][k]+=v
        labels={a.get('data_category') for a in answers.values()}
        agreed=len(labels)==1 and labels<=categories
        cache[c['file_id']]={'sha256':c['sha256'],'data_category':labels.pop() if agreed else None,'agreed':agreed,
                             'models':{k:{f:a.get(f) for f in ('data_category','rule_id','confidence','reason')} for k,a in answers.items()}}
    CACHE.parent.mkdir(exist_ok=True);CACHE.write_text(json.dumps(cache,indent=1,ensure_ascii=False))
    return cache,usage

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dataset',default='dataset');p.add_argument('--models',default='openai:gpt-5.5,openai:gpt-5.4-mini');a=p.parse_args()
    cache,usage=classify(a.dataset,a.models.split(','))
    print(json.dumps({'classifications':{k:(v['data_category'],v['agreed']) for k,v in cache.items()},'usage':usage},indent=1))
