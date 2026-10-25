"""Plan-only state simulation; simulated facts never become citations."""
from copy import deepcopy

def simulate(state,actions,edges=()):
    """state keys are (system,resource,copy); each record has subject,state,category.

    Edges are explicit source/target keys plus an enabled flow key. Both graph
    cycles and retained sources converge once all relevant controls are disabled.
    """
    out=deepcopy(state)
    ranked={'DISABLE_DATA_FLOW':0,'BLOCK_RESTORE':1,'DELETE_RECORD':2,'REDACT_RECORD':3,'ANONYMIZE_RECORD':4}
    final={'DISABLE_DATA_FLOW':'DISABLED','BLOCK_RESTORE':'BLOCKED','DELETE_RECORD':'ABSENT','REDACT_RECORD':'REDACTED','ANONYMIZE_RECORD':'ANONYMIZED'}
    for a in sorted(actions,key=lambda a:ranked.get(a['operation'],99)):
        if a['operation'] not in final:continue
        for key,obj in out.items():
            if key[:2]!=(a['system_id'],a['resource_id']):continue
            if a['operation']=='DELETE_RECORD' and obj['category'] in ('SECURITY_AUDIT_LOG','LEGAL_HOLD_RECORD','BACKUP_ARCHIVE','ACCOUNT_TOMBSTONE','SUPPORT_MESSAGE','ANALYTICS_PROFILE','PRODUCT_TELEMETRY'):raise ValueError('destructive plan violates retention')
            obj['state']=final[a['operation']]
    for _ in range(len(out)+1):
        changed=False
        for source,target,control in edges:
            if out[control]['state']=='ACTIVE' and (out[source]['state'] in ('PRESENT','IDENTIFIABLE') or (out[source]['category']=='BACKUP_ARCHIVE' and out[source]['state']=='ACTIVE')) and out[target]['state']!='PRESENT':out[target]['state']='PRESENT';changed=True
        if not changed:return out
    raise ValueError('recreation graph did not converge')

def check_plan(result):
    if result['unresolved']:return
    state={(p['system'],p['resource'],p['copy']):{'state':p['state'],'category':p['rule'].get('data_category','DATA_FLOW'),'subject':result['case_id']} for p in result['ledger']}
    actions=[s for s in result['steps'] if s['phase']=='REMEDIATION']
    edges=[tuple(tuple(k) for k in edge) for edge in result.get('simulation_edges',[])]
    after=simulate(state,actions,edges)
    expected={'DELETE':'ABSENT','REDACT':'REDACTED','ANONYMIZE':'ANONYMIZED','RETAIN':'PRESENT','DISABLE':'DISABLED','BLOCK':'BLOCKED'}
    for p in result['ledger']:assert after[(p['system'],p['resource'],p['copy'])]['state']==expected[p['obligation']],'simulation obligation failure'
    assert simulate(after,actions,edges)==after,'non-idempotent plan'
