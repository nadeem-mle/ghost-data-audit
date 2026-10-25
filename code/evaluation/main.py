"""Labels are read here only, after predictions; metrics count missing/extra steps."""
import argparse,sys,json
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from main import run
from audit.model import rows

def metrics(results,labels):
    predicted={r['case_id']:r for r in results};n=len(labels);confusion=Counter();matched=0;status_correct=0;tp=fp=fn=0;field_ok=Counter();field_n=Counter();evidence_ok=evidence_n=0;coverage_match=0;false_complete=wrongful=0;failures=[]
    for label in labels:
        p=predicted[label['case_id']];a=p['steps'];b=json.loads(label['steps_json']);status=p['status'];confusion[(label['deletion_status'],str(status))]+=1;status_correct+=status==label['deletion_status']
        exact=a==b and status==label['deletion_status'];matched+=exact
        if not exact:failures.append(label['case_id'])
        false_complete+=status=='COMPLETE' and label['deletion_status']!='COMPLETE'
        key=lambda x:(x['phase'],x['system_id'],x['resource_id'],x['operation'])
        pa={key(x):x for x in a};pb={key(x):x for x in b};common=pa.keys()&pb.keys();tp+=sum(pa[k]==pb[k] for k in common);fp+=len(pa)-sum(pa[k]==pb[k] for k in common);fn+=len(pb)-sum(pa[k]==pb[k] for k in common)
        for k in pa.keys()|pb.keys():
            for f in ('step_no','phase','system_id','resource_id','operation','state','evidence_id'):
                field_n[f]+=1;field_ok[f]+=k in pa and k in pb and pa[k][f]==pb[k][f]
            evidence_n+=1;evidence_ok+=k in common and pa[k]['evidence_id']==pb[k]['evidence_id']
        va={key(x) for x in a if x['phase']=='VERIFICATION'};vb={key(x) for x in b if x['phase']=='VERIFICATION'};coverage_match+=va==vb
        retained={x['resource_id'] for x in b if x['operation'] in ('VERIFY_RECORD_PRESENT','VERIFY_RECORD_REDACTED','VERIFY_RECORD_ANONYMIZED','VERIFY_RESTORE_BLOCKED')}
        wrongful+=sum(x['operation']=='DELETE_RECORD' and x['resource_id'] in retained for x in a)
    precision=tp/(tp+fp) if tp+fp else 0;recall=tp/(tp+fn) if tp+fn else 0
    return dict(cases=n,status_correct=status_correct,exact_cases=matched,sequence_match=sum(predicted[l['case_id']]['steps']==json.loads(l['steps_json']) for l in labels),confusion={a+' -> '+b:v for (a,b),v in confusion.items()},step_tp=tp,step_fp=fp,step_fn=fn,precision=precision,recall=recall,f1=2*precision*recall/(precision+recall) if precision+recall else 0,field_accuracy={k:[field_ok[k],field_n[k]] for k in field_n},evidence_accuracy=[evidence_ok,evidence_n],verification_coverage=[coverage_match,n],false_complete=false_complete,wrongful_deletion=wrongful,unresolved=sum(bool(p['unresolved']) for p in results),failures=failures)

def evaluate(dataset,ablations=True):
    d=Path(dataset);labels=rows(d/'sample_output.csv');reports={}
    modes=[('text_baseline',False,False),('local_ocr',True,False),('adaptive',True,True)] if ablations else [('adaptive',True,True)]
    for name,media,adaptive in modes:
        results,_,summary=run(d,d/'sample_deletion_requests.csv',Path('runs')/(name+'.csv'),media,adaptive,Path('runs/evaluation')/name)
        reports[name]=metrics(results,labels);reports[name]['model_calls']=0
    Path('runs/evaluation/metrics.json').write_text(json.dumps(reports,indent=2))
    print(json.dumps(reports,indent=2));return reports
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dataset',default='dataset');p.add_argument('--single',action='store_true');a=p.parse_args();evaluate(a.dataset,not a.single)
