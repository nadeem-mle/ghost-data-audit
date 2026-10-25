"""Metamorphic labeled evaluation: row-order variants of the 32 labeled samples.

Row order of the participant CSVs carries no meaning, so every shuffled variant
keeps the organizer's sample labels as ground truth. Each variant re-runs the
full pipeline on all 32 sample requests and is scored against sample_output.csv.
Usage: python3 code/evaluation/metamorphic.py --dataset dataset --variants 7
"""
import argparse,csv,json,random,shutil,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from main import run
from audit.model import rows
from evaluation.main import metrics

SHUFFLED=('user_identities.csv','user_audit_log.csv','system_activity.csv','evidence_files.csv','sample_deletion_requests.csv')

def variant(src,dst,seed):
    """Copy the participant dataset with every row-ordered CSV shuffled by seed."""
    dst.mkdir(parents=True)
    for p in src.iterdir():
        if p.name=='evidence':shutil.copytree(p.resolve(),dst/'evidence')
        elif p.suffix=='.csv' and p.name in SHUFFLED:
            with open(p,newline='',encoding='utf-8') as f:r=list(csv.reader(f))
            head,body=r[0],r[1:];random.Random(seed).shuffle(body)
            with open(dst/p.name,'w',newline='',encoding='utf-8') as f:csv.writer(f).writerows([head]+body)
        elif p.is_file():shutil.copyfile(p,dst/p.name)

def evaluate(dataset,variants,out):
    src=Path(dataset).resolve();labels=rows(src/'sample_output.csv');per=[];agg={'cases':0,'status_correct':0,'exact_cases':0,'false_complete':0,'wrongful_deletion':0,'step_tp':0,'step_fp':0,'step_fn':0}
    base=None;unstable=set()
    with tempfile.TemporaryDirectory(prefix='meta-') as tmp:
        for seed in range(variants):
            t=time.time();d=Path(tmp)/f'v{seed}';variant(src,d,seed)
            results,_,_=run(d,d/'sample_deletion_requests.csv',Path(tmp)/f'out{seed}.csv',True,True,Path(tmp)/f'run{seed}')
            m=metrics(results,labels);m['seconds']=round(time.time()-t,1);m['seed']=seed
            plans={r['case_id']:(r['status'],json.dumps(r['steps'])) for r in results}
            if base is None:base=plans
            unstable|={c for c in plans if plans[c]!=base[c]}
            per.append({k:m[k] for k in ('seed','status_correct','exact_cases','false_complete','wrongful_deletion','precision','recall','seconds')})
            for k in agg:agg[k]+=m[k]
    p=agg['step_tp']/(agg['step_tp']+agg['step_fp']);r=agg['step_tp']/(agg['step_tp']+agg['step_fn'])
    report={'variants':variants,'labeled_cases':agg['cases'],**agg,'precision':round(p,4),'recall':round(r,4),
            'order_unstable_cases':sorted(unstable),'per_variant':per}
    Path(out).write_text(json.dumps(report,indent=1));return report

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--dataset',default='dataset');a.add_argument('--variants',type=int,default=7)
    a.add_argument('--out',default=str(Path(__file__).resolve().parents[2]/'runs'/'agents'/'qa'/'metamorphic.json'));x=a.parse_args()
    rep=evaluate(x.dataset,x.variants,x.out);print(json.dumps({k:v for k,v in rep.items() if k!='per_variant'},indent=1))
