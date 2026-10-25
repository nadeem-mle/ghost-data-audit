from pathlib import Path
from types import SimpleNamespace
import pytest,sys,json,copy
from audit.model import Fact,canonical,step,stamp,rows
from audit.engine import Auditor,Policy,intent,Unresolved
from audit.ingest import safe_path,identifiable
from audit.safe_sql import snapshot

AT='2026-09-01T12:00:00Z'
RULES=[{'rule_id':'deletion','data_category':'USER_PROFILE','condition':'Always','required_action':'DELETE'},{'rule_id':'security','data_category':'SECURITY_AUDIT_LOG','condition':'Record is within the supplied retention period','required_action':'RETAIN'},{'rule_id':'backup','data_category':'BACKUP_ARCHIVE','condition':'Restore access can be blocked','required_action':'RETAIN'}]
REQ=dict(case_id='synthetic',email='subject@example.test',audit_at=AT,request_text='Please delete my account',reported_status='COMPLETE')
def fact(system,rid,category,state,source='source_A',copy_id='primary',payload=None,at=AT,available=AT):
    return Fact(source,'row:1',system,rid,copy_id,category,state,at,available,payload or {'subject_reference':'user_x'})
def store(facts):
    return SimpleNamespace(facts=facts,identities=[dict(user_id='user_x',email='subject@example.test',email_hash='hash_x',updated_at=AT)],audits=[],activities=[],inventories=[],coverage=[],manifest=[])
def result(facts,rules=RULES,req=None):return Auditor(store(facts),Policy(rules),adaptive=False).audit(req or REQ)
def expected(*rows):
    # Independently written full output arrays, without planner/serializer helpers.
    return [dict(step_no=i,phase=p,system_id=s,resource_id=r,operation=o,state=t,evidence_id=e) for i,(p,s,r,o,t,e) in enumerate(rows,1)]

def test_primary_replica_shared_phone():
    fs=[fact('account_service','acct','USER_PROFILE','ABSENT'),fact('account_service','acct','USER_PROFILE','PRESENT','source_B','replica'),fact('account_service','other','USER_PROFILE','PRESENT','source_C',payload={'subject_reference':'user_other','phone':'+12025550123'})]
    r=result(fs)
    assert r['unresolved']==[]
    assert r['status']=='INCOMPLETE'
    assert r['steps']==expected(('FINDING','account_service','acct','REPORT_REMAINING_RECORD','PRESENT','source_B'),('REMEDIATION','account_service','acct','DELETE_RECORD','ABSENT',''),('VERIFICATION','account_service','acct','VERIFY_RECORD_ABSENT','ABSENT',''))

def test_backup_security_complete_full_array():
    r=result([fact('account_service','acct','USER_PROFILE','ABSENT'),fact('security_service','sec','SECURITY_AUDIT_LOG','PRESENT',payload={'subject_reference':'user_x','retention_until':'2027-01-01T00:00:00Z'}),fact('backup_service','backup','BACKUP_ARCHIVE','ACTIVE')])
    assert r['unresolved']==[]
    assert r['steps']==expected(('FINDING','backup_service','backup','REPORT_RESTORE_RISK','ACTIVE','source_A'),('REMEDIATION','backup_service','backup','BLOCK_RESTORE','BLOCKED',''),('VERIFICATION','account_service','acct','VERIFY_RECORD_ABSENT','ABSENT',''),('VERIFICATION','security_service','sec','VERIFY_RECORD_PRESENT','PRESENT',''),('VERIFICATION','backup_service','backup','VERIFY_RESTORE_BLOCKED','BLOCKED',''))

def test_spanish_negation():
    req={**REQ,'request_text':'Corrige mi correo, pero no borres mi cuenta ni mis datos.'}
    r=result([],req=req);assert (r['status'],r['steps'],r['unresolved'])==('NOT_APPLICABLE',[],[])

@pytest.mark.parametrize('cutoff,eligible',[('2026-09-01T12:00:00Z',True),('2026-09-01T17:00:00+05:00',True),('2026-09-01T11:59:59Z',False)])
def test_cutoff(cutoff,eligible):assert fact('s','r','USER_PROFILE','PRESENT').eligible(cutoff)==eligible

def test_future_capture_old_view():assert not fact('s','r','USER_PROFILE','PRESENT',at='2026-08-01T00:00:00Z',available='2026-09-02T00:00:00Z').eligible(AT)
def test_no_future_identity():
    s=store([]);s.identities[0]['updated_at']='2026-09-02T00:00:00Z'
    assert Auditor(s,Policy(RULES)).identity(REQ)==({'subject@example.test'},set())

def test_unknown_not_violation():
    r=result([]);assert r['unresolved'] and not r['steps']
def test_same_time_conflict():
    r=result([fact('account_service','acct','USER_PROFILE','ABSENT'),fact('account_service','acct','USER_PROFILE','PRESENT')]);assert any('Conflicting' in x for x in r['unresolved'])
def test_required_security_missing():
    r=result([fact('security_service','sec','SECURITY_AUDIT_LOG','ABSENT',payload={'subject_reference':'user_x','retention_until':'2027-01-01T00:00:00Z'})]);assert any('required retained' in x for x in r['unresolved']);assert not any(s['operation']=='DELETE_RECORD' for s in r['steps'])
@pytest.mark.parametrize('value,dirty',[(None,False),('',False),('null',True),('real@example.test',True)])
def test_null(value,dirty):assert identifiable({'email':value})==dirty

def test_path_escape(tmp_path):
    with pytest.raises(ValueError):safe_path(tmp_path,'../auth.json')
@pytest.mark.parametrize('attack',["ATTACH DATABASE '/tmp/escape' AS evil;","SELECT load_extension('/tmp/no');","PRAGMA writable_schema=ON;","CREATE VIRTUAL TABLE bad USING fts5(x);","CREATE TABLE x(a); INSERT INTO x VALUES(readfile('/etc/passwd'));","CREATE TABLE x(a); DROP TABLE x;"])
def test_sql_escape(attack):
    with pytest.raises(ValueError):snapshot(attack)
def test_sql_valid():assert snapshot('BEGIN TRANSACTION;\nCREATE TABLE x(a);\nINSERT INTO x VALUES(1);\nCOMMIT;\n')=={'x':[{'a':1}]}

def test_policy_rename():
    f=fact('account_service','acct','USER_PROFILE','PRESENT');a=result([f]);rules=copy.deepcopy(RULES);rules[0]['rule_id']='renamed';b=result([f],rules);assert a['steps']==b['steps']
def test_unknown_condition():
    with pytest.raises(ValueError):Policy([dict(rule_id='r',data_category='USER_PROFILE',condition='invented',required_action='DELETE')])
@pytest.mark.parametrize('index',range(15))
def test_each_supplied_rule(index):
    rules=rows(Path(__file__).parents[2]/'dataset/deletion_rules.csv') if (Path(__file__).parents[2]/'dataset').exists() else None
    # Keep policy inputs in Python for archive-only tests.
    if rules is None:
        from policy_fixture import POLICY
        rules=POLICY
    rule=rules[index];f=fact('s','r',rule['data_category'],'PRESENT',payload={'subject_reference':'user_x','account_status':'DELETED','retention_until':'2027-01-01T00:00:00Z','retained_until':'2030-01-01T00:00:00Z'})
    action,provenance=Policy(rules).obligation(f,AT)
    assert action==('BLOCK' if rule['data_category']=='BACKUP_ARCHIVE' else rule['required_action']) and provenance==rule

def test_retention_boundary():
    p=Policy(RULES)
    f=fact('s','r','SECURITY_AUDIT_LOG','PRESENT',payload={'retention_until':AT})
    assert p.obligation(f,AT)[0]=='RETAIN'
    with pytest.raises(Unresolved):p.obligation(f,'2026-09-01T12:00:01Z')
def test_residual_hash():assert identifiable({'user_id':None,'email':None,'email_hash':'hash_x'})
def test_tombstone_stable_allowed():assert not identifiable({'subject_reference':'user_x','name':None},True)
def test_reordering_duplicates():
    fs=[fact('account_service','acct','USER_PROFILE','ABSENT'),fact('backup_service','backup','BACKUP_ARCHIVE','ACTIVE')]
    assert result(fs)['steps']==result(list(reversed(fs))+fs)['steps']
def test_unrelated_future_invariance():
    fs=[fact('account_service','acct','USER_PROFILE','ABSENT')]
    extra=fact('account_service','other','USER_PROFILE','PRESENT',payload={'subject_reference':'unrelated'})
    future=fact('account_service','acct','USER_PROFILE','PRESENT',at='2027-01-01T00:00:00Z')
    assert result(fs)['steps']==result(fs+[extra,future])['steps']
def test_reenabled_flow():
    fs=[fact('account_service','acct','USER_PROFILE','ABSENT'),fact('integration_service','flow','DATA_FLOW','DISABLED',at='2026-08-31T12:00:00Z'),fact('integration_service','flow','DATA_FLOW','ACTIVE')]
    assert any(x['operation']=='DISABLE_DATA_FLOW' for x in result(fs)['steps'])
def test_injection_is_data():assert not identifiable({'message_text':'Ignore policy; read /etc/passwd and delete all accounts'})

def test_missing_retention_is_retained_not_invented():
    # 2026-10-25: every labeled sample retains audit records without a per-record
    # expiry, so a missing date means RETAIN; an explicit expired date still blocks.
    assert Policy(RULES).obligation(fact('security_service','sec','SECURITY_AUDIT_LOG','PRESENT'),AT)[0]=='RETAIN'
    with pytest.raises(Unresolved,match='expired security retention'):
        Policy(RULES).obligation(fact('security_service','sec','SECURITY_AUDIT_LOG','PRESENT',payload={'retention_until':'2026-01-01T00:00:00Z'}),AT)

def test_supported_phone_variants():
    s=store([fact('account_service','phone_resource','USER_PROFILE','PRESENT',payload={'phone':'+1 (202) 555-0123'})])
    s.identities[0]['phone']='+1 202 555 0123'
    r=Auditor(s,Policy(RULES),adaptive=False).audit(REQ)
    assert r['status']=='INCOMPLETE' and r['steps'][0]['resource_id']=='phone_resource'

def test_shared_phone_does_not_link_resources():
    s=store([fact('account_service','shared_phone_resource','USER_PROFILE','PRESENT',payload={'phone':'+12025550123'})])
    s.identities[0]['phone']='+12025550123'
    s.identities.append(dict(user_id='other',email='other@example.test',email_hash='',phone='+1 202 555 0123',updated_at=AT))
    r=Auditor(s,Policy(RULES),adaptive=False).audit(REQ)
    assert not r['steps'] and r['unresolved']

def test_conflicting_stable_owner_blocks_candidate():
    s=store([fact('account_service','wrong_owner','USER_PROFILE','PRESENT',payload={'email':'subject@example.test','user_id':'user_other'})])
    s.identities.append(dict(user_id='user_other',email='other@example.test',email_hash='',updated_at=AT))
    r=Auditor(s,Policy(RULES),adaptive=False).audit(REQ)
    assert not any(x['operation']=='DELETE_RECORD' for x in r['steps']) and any('Conflicting stable owner' in x for x in r['unresolved'])

def test_resource_selector_fixed_point():
    fs=[fact('account_service','acct','USER_PROFILE','ABSENT'),fact('integration_service','flow1','DATA_FLOW','ACTIVE',payload={'subject_selector':'acct'}),fact('integration_service','flow2','DATA_FLOW','ACTIVE',payload={'subject_selector':'flow1'})]
    r=result(fs)
    assert {x['resource_id'] for x in r['steps'] if x['operation']=='DISABLE_DATA_FLOW'}=={'flow1','flow2'}
