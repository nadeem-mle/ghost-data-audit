"""Assemble the 518-row submission from a run's results.json.

Supported cases are written verbatim. Cases still blocked by an unresolved proof
obligation get the engine's best evidence-grounded plan and are listed in
provisional_cases.csv; the graded columns never carry a fourth status.
"""
import argparse,csv,json,re,sys
from pathlib import Path

ORDER=['REPORT_REMAINING_RECORD','REPORT_EXPOSED_PII','REPORT_ACTIVE_DATA_FLOW','REPORT_RESTORE_RISK',
       'DISABLE_DATA_FLOW','BLOCK_RESTORE','DELETE_RECORD','REDACT_RECORD','ANONYMIZE_RECORD',
       'VERIFY_RECORD_ABSENT','VERIFY_RECORD_PRESENT','VERIFY_RECORD_REDACTED','VERIFY_RECORD_ANONYMIZED',
       'VERIFY_DATA_FLOW_DISABLED','VERIFY_RESTORE_BLOCKED']
PHASE={**{o:'FINDING' for o in ORDER[:4]},**{o:'REMEDIATION' for o in ORDER[4:9]},**{o:'VERIFICATION' for o in ORDER[9:]}}
STATE={'REPORT_REMAINING_RECORD':'PRESENT','REPORT_EXPOSED_PII':'PRESENT','REPORT_ACTIVE_DATA_FLOW':'ACTIVE','REPORT_RESTORE_RISK':'ACTIVE',
       'DISABLE_DATA_FLOW':'DISABLED','BLOCK_RESTORE':'BLOCKED','DELETE_RECORD':'ABSENT','REDACT_RECORD':'REDACTED','ANONYMIZE_RECORD':'ANONYMIZED',
       'VERIFY_RECORD_ABSENT':'ABSENT','VERIFY_RECORD_PRESENT':'PRESENT','VERIFY_RECORD_REDACTED':'REDACTED','VERIFY_RECORD_ANONYMIZED':'ANONYMIZED',
       'VERIFY_DATA_FLOW_DISABLED':'DISABLED','VERIFY_RESTORE_BLOCKED':'BLOCKED'}
KEYS={'step_no','phase','system_id','resource_id','operation','state','evidence_id'}

def check_row(cid,status,steps,known_ids):
    """Return contract violations for one row (empty list when valid)."""
    errs=[]
    if status not in ('COMPLETE','INCOMPLETE','NOT_APPLICABLE'):errs.append('bad status')
    if status=='NOT_APPLICABLE' and steps:errs.append('NOT_APPLICABLE must be []')
    if status in ('COMPLETE','INCOMPLETE') and not steps:errs.append('empty plan for '+status)
    rank=lambda s:(ORDER.index(s['operation']),s['system_id'],s['resource_id'])
    for i,s in enumerate(steps,1):
        if set(s)!=KEYS:errs.append(f'step {i} keys');continue
        if s['step_no']!=i:errs.append(f'step {i} numbering')
        if s['operation'] not in PHASE or PHASE[s['operation']]!=s['phase'] or STATE[s['operation']]!=s['state']:errs.append(f'step {i} op/phase/state')
        if status=='COMPLETE' and (s['phase']!='VERIFICATION' or not s['evidence_id']):errs.append(f'step {i} COMPLETE needs cited verification')
        if status=='INCOMPLETE' and s['phase']!='FINDING' and s['evidence_id']:errs.append(f'step {i} planned step must have empty evidence')
        if s['phase']=='FINDING' and not s['evidence_id']:errs.append(f'step {i} finding without evidence')
        if s['evidence_id'] and s['evidence_id'] not in known_ids:errs.append(f'step {i} unknown evidence {s["evidence_id"]}')
    if all(set(s)==KEYS and s['operation'] in PHASE for s in steps) and [rank(s) for s in steps]!=sorted(rank(s) for s in steps):errs.append('step order')
    return errs

def known_evidence(dataset):
    d=Path(dataset);ids=set()
    for name,col in (('evidence_files.csv','file_id'),('system_activity.csv','activity_id'),('user_audit_log.csv','audit_id')):
        ids|={r[col] for r in csv.DictReader(open(d/name,encoding='utf-8'))}
    return ids

def assemble(dataset,results_path,output,provisional_path):
    d=Path(dataset);requests=[r['case_id'] for r in csv.DictReader(open(d/'deletion_requests.csv',encoding='utf-8'))]
    results={r['case_id']:r for r in json.load(open(results_path,encoding='utf-8'))}
    known=known_evidence(d);rows=[];provisional=[];errors={}
    for cid in sorted(requests):
        r=results.get(cid,{'status':None,'steps':[],'unresolved':['case missing from results']})
        status,steps=r['status'],r['steps']
        if status is None:
            # Undecided: cited verification-only plans read as COMPLETE; anything else
            # stays INCOMPLETE with planned (uncited) remediation and verification.
            if steps and all(s['phase']=='VERIFICATION' and s['evidence_id'] for s in steps):status='COMPLETE'
            else:
                status='INCOMPLETE'
                steps=[dict(s,evidence_id='') if s['phase']!='FINDING' else s for s in steps]
        if r.get('unresolved'):provisional.append([cid,status,json.dumps(r['unresolved'],ensure_ascii=False)])
        errs=check_row(cid,status,steps,known)
        if errs:errors[cid]=errs
        rows.append([cid,status,json.dumps(steps,ensure_ascii=False,separators=(',',':'))])
    tmp=Path(str(output)+'.tmp')
    with open(tmp,'w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(['case_id','deletion_status','steps_json']);w.writerows(rows)
    tmp.replace(output)
    with open(provisional_path,'w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(['case_id','submitted_status','unresolved_json']);w.writerows(provisional)
    return dict(rows=len(rows),requests=len(requests),provisional=len(provisional),contract_errors=errors)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dataset',default='dataset');p.add_argument('--results',required=True)
    p.add_argument('--output',default='output.csv');p.add_argument('--provisional',default='provisional_cases.csv');a=p.parse_args()
    s=assemble(a.dataset,a.results,a.output,a.provisional)
    from collections import Counter
    print(json.dumps({**{k:v for k,v in s.items() if k!='contract_errors'},'contract_error_cases':len(s['contract_errors']),
                      'error_kinds':Counter(e.split(' ',2)[-1] if e.startswith('step') else e for v in s['contract_errors'].values() for e in v).most_common(10)},indent=1))
    sys.exit(1 if s['contract_errors'] or s['rows']!=s['requests'] else 0)
