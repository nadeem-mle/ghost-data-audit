"""Offline evidence auditor. Official output is written only on supported complete coverage."""
import argparse,json,csv,os,tempfile,hashlib,sys,re
from pathlib import Path
from collections import Counter
from audit.model import rows
from audit.ingest import Store
from audit.engine import Auditor,Policy
from validate_output import validate,check_proofs,verify_evidence
from audit.simulate import check_plan
from audit.provenance import fingerprint

def write_csv(path,results):
    with open(path,'w',newline='') as f:
        w=csv.writer(f);w.writerow(['case_id','deletion_status','steps_json'])
        for r in sorted(results,key=lambda x:x['case_id']):
            if r['status'] is not None:w.writerow([r['case_id'],r['status'],json.dumps(r['steps'],ensure_ascii=False,separators=(',',':'))])

def run(dataset,requests,output,media=True,adaptive=True,run_dir='runs/latest',gemini_client=None,agent_client=None,agent_case=None):
    d=Path(dataset);rd=Path(run_dir);rd.mkdir(parents=True,exist_ok=True)
    target=Path(output).resolve()
    if target==Path(requests).resolve() or target.is_relative_to(d.resolve()):raise ValueError('output must not overwrite participant input')
    stale_path=None
    if target.exists():
        import uuid
        stale_path=rd/('older-output-NOT-CURRENT-'+uuid.uuid4().hex+'.csv');os.replace(target,stale_path)
    request_rows=rows(requests)
    if agent_client is not None and (not agent_case or agent_case not in {r['case_id'] for r in request_rows}):raise ValueError('An explicit existing --agent-case is required')
    case_ids=[r['case_id'] for r in request_rows]
    if len(case_ids)!=len(set(case_ids)) or any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',cid) or '..' in cid for cid in case_ids):raise ValueError('invalid or duplicate case_id')
    target=Path(output).resolve()
    if target==Path(requests).resolve() or target.is_relative_to(d.resolve()):raise ValueError('output must not overwrite participant input')
    request_hash=hashlib.sha256(Path(requests).read_bytes()).hexdigest()
    fp=fingerprint(d,media,adaptive)
    (rd/'fingerprint.json').write_text(json.dumps(fp,indent=2))
    store=Store(d,media=media).ingest();auditor=Auditor(store,Policy(rows(d/'deletion_rules.csv')),adaptive)
    (rd/'coverage.json').write_text(json.dumps(store.coverage,indent=2))
    results=[]
    for req in request_rows:
        try:
            result=auditor.audit(req);check_plan(result)
        except (ValueError,OSError,AssertionError) as exc:
            result={'case_id':req['case_id'],'status':None,'steps':[],'ledger':[],'investigation':[],'unresolved':[type(exc).__name__+': '+str(exc)]}
        results.append(result)
        # Diagnostic checkpoints contain evidence, never shipped as source.
        (rd/(req['case_id']+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    if fingerprint(d,media,adaptive)['fingerprint']!=fp['fingerprint'] or hashlib.sha256(Path(requests).read_bytes()).hexdigest()!=request_hash:
        for result in results:result['unresolved'].append('Prediction source/input/config changed during run; rerun required')
    (rd/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));check_proofs(results)
    raw_checks=verify_evidence(store,results,rows(requests))
    agent_report=None
    if agent_client is not None:
        from audit.investigator import investigate
        req=next(r for r in request_rows if r['case_id']==agent_case)
        result=next(r for r in results if r['case_id']==agent_case)
        before=json.dumps(result,sort_keys=True)
        agent_report=investigate(store,req,result,auditor.identity(req)[0],agent_client)
        assert json.dumps(result,sort_keys=True)==before,'Investigator must not mutate accepted proof'
        (rd/'tool-agent.json').write_text(json.dumps(agent_report,ensure_ascii=False,indent=2))
    gemini_report=None
    if gemini_client is not None:
        from gemini_review import review_cases
        gemini_report=review_cases(store,results,request_rows,gemini_client,max_cases=3)
        (rd/'gemini-review.json').write_text(json.dumps(gemini_report,ensure_ascii=False,indent=2))
    draft=rd/'draft.csv';write_csv(draft,results)
    with (rd/'case_review.csv').open('w',newline='') as diagnostic:
        writer=csv.writer(diagnostic);writer.writerow(['case_id','assessment_if_supported','proof_readiness','unresolved_json','steps_json'])
        for result in sorted(results,key=lambda x:x['case_id']):
            writer.writerow([result['case_id'],result['status'] or '', 'BLOCKED' if result['unresolved'] else 'SUPPORTED',json.dumps(result['unresolved'],ensure_ascii=False),json.dumps(result['steps'],ensure_ascii=False)])
    unresolved=sum(bool(r['unresolved']) for r in results)
    summary={'request_sha256':request_hash,'raw_sources_rechecked':raw_checks,'requests':len(results),'unresolved':unresolved,'statuses':dict(Counter(r['status'] for r in results)),'source_coverage':dict(Counter(r['status'] for r in store.coverage)),'media':media,'adaptive':adaptive,'model_calls':0,'official_output_written':False}
    if gemini_report is not None:
        summary['model_calls']=gemini_report['usage']['attempted_calls']
        summary['gemini_review']={k:v for k,v in gemini_report.items() if k!='reviews'}
        summary['gemini_review']['successful_reviews']=sum(r['success'] for r in gemini_report['reviews'])
    if agent_report is not None:
        summary['tool_agent']={k:v for k,v in agent_report.items() if k not in ('trace','observations','original_unresolved')}
        summary['model_calls']+=agent_report['usage'].get('attempted_calls',0)
    if stale_path is not None:summary['older_output_archived']=str(stale_path)
    if not unresolved:
        validate(d,draft,requests)
        target=Path(output);target.parent.mkdir(parents=True,exist_ok=True)
        tmp=target.with_suffix('.pending');tmp.write_bytes(draft.read_bytes());os.replace(tmp,target);summary['official_output_written']=True;summary['output_sha256']=hashlib.sha256(target.read_bytes()).hexdigest()
    (rd/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary))
    return results,store,summary
def model_client(spec,**budget):
    """`openai:<model>` selects OpenAI (key from OPENAI_API_KEY or .env); otherwise Gemini."""
    if spec.startswith('openai:'):
        from audit.openai_client import OpenAIClient
        return OpenAIClient(spec.removeprefix('openai:'),**budget)
    from audit.gemini import GeminiClient
    return GeminiClient(spec,**budget)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dataset',default='dataset');p.add_argument('--requests');p.add_argument('--output',default='output.csv');p.add_argument('--no-llm',action='store_true',help='Honest offline baseline; includes local OCR, never calls a provider');p.add_argument('--text-only',action='store_true');p.add_argument('--no-investigator',action='store_true');p.add_argument('--run-dir',default='runs/latest');p.add_argument('--gemini-model');p.add_argument('--agent-model',help='Opt-in model-directed read-only investigation');p.add_argument('--agent-case',help='Exactly one case to investigate');a=p.parse_args()
    if a.no_llm and (a.gemini_model or a.agent_model):p.error('--no-llm and provider models are mutually exclusive')
    client=None
    if a.gemini_model:
        client=model_client(a.gemini_model,max_calls=3,retries=0,max_output_tokens=2048,max_input_bytes=24000)
    agent_client=None
    if a.agent_model:
        agent_client=model_client(a.agent_model,max_calls=9,retries=0,max_output_tokens=1024,max_input_bytes=24000)
    _,_,s=run(a.dataset,a.requests or Path(a.dataset)/'deletion_requests.csv',a.output,not a.text_only,not a.no_investigator,a.run_dir,gemini_client=client,agent_client=agent_client,agent_case=a.agent_case)
    sys.exit(2 if s['unresolved'] else 0)
