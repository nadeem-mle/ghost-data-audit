"""Typed facts and exact contract serialization. No sample labels are imported."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import csv, json, hashlib

def stamp(value):
    if not value: raise ValueError('missing timestamp')
    d=datetime.fromisoformat(value.replace('Z','+00:00'))
    if d.tzinfo is None: raise ValueError('timezone required')
    return d.astimezone(timezone.utc)

def rows(path):
    with open(path, newline='', encoding='utf-8-sig') as f:
        reader=csv.DictReader(f,strict=True)
        result=list(reader)
        if any(None in r or any(v is None for v in r.values()) for r in result): raise ValueError('malformed CSV')
        return result

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

OPERATIONS={
 'FINDING':[('REPORT_REMAINING_RECORD','PRESENT'),('REPORT_EXPOSED_PII','PRESENT'),('REPORT_ACTIVE_DATA_FLOW','ACTIVE'),('REPORT_RESTORE_RISK','ACTIVE')],
 'REMEDIATION':[('DISABLE_DATA_FLOW','DISABLED'),('BLOCK_RESTORE','BLOCKED'),('DELETE_RECORD','ABSENT'),('REDACT_RECORD','REDACTED'),('ANONYMIZE_RECORD','ANONYMIZED')],
 'VERIFICATION':[('VERIFY_RECORD_ABSENT','ABSENT'),('VERIFY_RECORD_PRESENT','PRESENT'),('VERIFY_RECORD_REDACTED','REDACTED'),('VERIFY_RECORD_ANONYMIZED','ANONYMIZED'),('VERIFY_DATA_FLOW_DISABLED','DISABLED'),('VERIFY_RESTORE_BLOCKED','BLOCKED')]}
RANK={op:(i,j,state,phase) for i,(phase,ops) in enumerate(OPERATIONS.items()) for j,(op,state) in enumerate(ops)}
def step(op,system,resource,evidence=''):
    return dict(step_no=0,phase=RANK[op][3],system_id=system,resource_id=resource,operation=op,state=RANK[op][2],evidence_id=evidence)
def canonical(steps):
    by={}
    for x in steps:
        k=(x['phase'],x['system_id'],x['resource_id'],x['operation'])
        if k in by and by[k]['state']!=x['state']:raise ValueError('conflicting steps')
        by.setdefault(k,dict(x))
    out=sorted(by.values(),key=lambda x:(*RANK[x['operation']][:2],x['system_id'],x['resource_id']))
    for i,x in enumerate(out,1):x['step_no']=i
    return out

@dataclass(frozen=True)
class Fact:
    source_id:str
    source_location:str
    system_id:str
    resource_id:str
    copy_id:str
    category:str
    state:str
    observed_at:str
    available_at:str
    payload:dict=field(default_factory=dict)
    evidence_kind:str='readback'
    coverage_scope:str='record'
    def eligible(self,cutoff):return stamp(self.observed_at)<=stamp(cutoff) and stamp(self.available_at)<=stamp(cutoff)

class Unresolved(Exception):pass
