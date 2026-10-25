"""Independent LLM review of finished predictions (advisory; never changes output.csv).

Samples cases (every case that was ever provisional plus a seeded random draw),
shows a reviewer model the request, the evidence ledger and our steps, and asks
it to flag contract or evidence problems. Writes runs/agents/qa/llm-review.json.
Usage: python3 code/evaluation/llm_review.py --run-dir runs/<run> [--model openai:gpt-5.5] [--n 20]
"""
import argparse,csv,json,random,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from main import model_client

CONTRACT=Path(__file__).resolve().parents[2]/'official'/'problem_statement.md'
ASK=("You are an independent auditor reviewing one prediction for the 'Ghost Data Still Exists' deletion-audit challenge.\n"
     "CONTRACT (authoritative):\n{contract}\nDELETION RULES:\n{rules}\nREQUEST:\n{request}\n"
     "EVIDENCE LEDGER (what the system observed, with source ids, states and the rule applied):\n{ledger}\n"
     "PREDICTION: status={status}\nsteps={steps}\n"
     "Check: status follows from the ledger; every finding/remediation/verification is consistent with the rule; step order and "
     "evidence_id conventions follow the contract; nothing in the ledger is ignored; request intent authorizes deletion.\n"
     'Return JSON {{"verdict": "AGREE"|"DISAGREE", "severity": "none"|"minor"|"major", "issues": [str]}}')

def review(dataset,run_dir,model,n,seed=7,pace=6):
    d=Path(dataset);rd=Path(run_dir)
    requests={r['case_id']:r for r in csv.DictReader(open(d/'deletion_requests.csv',encoding='utf-8'))}
    rules=(d/'deletion_rules.csv').read_text(encoding='utf-8')
    contract=CONTRACT.read_text(encoding='utf-8')
    contract=contract[contract.index('## Required Output'):contract.index('## Evaluation')]
    focus=['case_33','case_46','case_55','case_61','case_390']
    rest=sorted(set(requests)-set(focus));random.Random(seed).shuffle(rest)
    reviews=[];usage={}
    for cid in focus+rest[:max(0,n-len(focus))]:
        r=json.loads((rd/(cid+'.json')).read_text(encoding='utf-8'))
        ledger=[{k:l.get(k) for k in ('system','resource','state','observed_state','result','obligation','source','location','observed_at')}|{'rule':l['rule'].get('rule_id')} for l in r['ledger']]
        prompt=ASK.format(contract=contract,rules=rules,request=json.dumps(requests[cid],ensure_ascii=False),
                          ledger=json.dumps(ledger,ensure_ascii=False),status=r['status'],steps=json.dumps(r['steps']))
        time.sleep(pace);client=model_client(model,max_calls=2,retries=1,max_output_tokens=4000,max_input_bytes=60000)
        try:answer=client.generate_json(prompt)
        except RuntimeError as e:answer={'verdict':'ERROR','severity':'none','issues':[str(e)]}
        for k,v in client.usage.items():usage[k]=usage.get(k,0)+v
        reviews.append({'case_id':cid,'status':r['status'],**answer})
    out={'model':model,'cases':len(reviews),'agree':sum(x['verdict']=='AGREE' for x in reviews),
         'major':[x for x in reviews if x.get('severity')=='major'],'reviews':reviews,'usage':usage}
    target=Path(__file__).resolve().parents[2]/'runs'/'agents'/'qa'/('llm-review-'+model.replace(':','_')+'.json')
    target.write_text(json.dumps(out,indent=1,ensure_ascii=False));return out,target

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dataset',default='dataset');p.add_argument('--run-dir',required=True)
    p.add_argument('--model',default='openai:gpt-5.5');p.add_argument('--n',type=int,default=20);a=p.parse_args()
    out,target=review(a.dataset,a.run_dir,a.model,a.n)
    print(json.dumps({k:out[k] for k in ('model','cases','agree','usage')},indent=1));print('major:',json.dumps([(x['case_id'],x['issues']) for x in out['major']],indent=1,ensure_ascii=False)[:4000]);print(target)
