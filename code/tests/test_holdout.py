"""Frozen independently specified holdout: never constructed from sample labels."""
import pytest
from audit.simulate import simulate
from audit.engine import Policy,Unresolved
from audit.model import step
from test_core import fact,result,REQ,RULES,AT,expected

def test_holdout_clean_tombstone_full_array():
    rules=RULES+[dict(rule_id='tomb',data_category='ACCOUNT_TOMBSTONE',condition='Account is deleted and only a stable internal user_id is needed to preserve references to retained records',required_action='REDACT')]
    f=fact('identity_service','deleted_ref','ACCOUNT_TOMBSTONE','REDACTED',payload={'subject_reference':'user_x','name':None,'email':None,'phone':None,'email_hash':None,'account_status':'DELETED'})
    r=result([fact('account_service','acct','USER_PROFILE','ABSENT'),f],rules)
    assert r['status']=='COMPLETE' and r['unresolved']==[]
    assert r['steps']==expected(('VERIFICATION','account_service','acct','VERIFY_RECORD_ABSENT','ABSENT','source_A'),('VERIFICATION','identity_service','deleted_ref','VERIFY_RECORD_REDACTED','REDACTED','source_A'))

def test_holdout_linkable_hash_mutation_full_array():
    rules=RULES+[dict(rule_id='anon',data_category='ANALYTICS_PROFILE',condition='Record is still attributable to a user',required_action='ANONYMIZE')]
    fs=[fact('account_service','acct','USER_PROFILE','ABSENT'),fact('analytics_platform','audience','ANALYTICS_PROFILE','IDENTIFIABLE',payload={'email_hash':'hash_x'})]
    r=result(fs,rules)
    assert r['status']=='INCOMPLETE' and not r['unresolved']
    assert r['steps']==expected(('FINDING','analytics_platform','audience','REPORT_EXPOSED_PII','PRESENT','source_A'),('REMEDIATION','analytics_platform','audience','ANONYMIZE_RECORD','ANONYMIZED',''),('VERIFICATION','account_service','acct','VERIFY_RECORD_ABSENT','ABSENT',''),('VERIFICATION','analytics_platform','audience','VERIFY_RECORD_ANONYMIZED','ANONYMIZED',''))

def test_holdout_cycle_retained_source_simulation():
    a=('account_service','a','primary');b=('search_service','b','replica');c=('security_service','sec','primary');f=('integration_service','f','primary');other=('account_service','unrelated','primary')
    state={a:{'state':'ABSENT','category':'USER_PROFILE','subject':'u'},b:{'state':'PRESENT','category':'SEARCH_INDEX_ENTRY','subject':'u'},c:{'state':'PRESENT','category':'SECURITY_AUDIT_LOG','subject':'u'},f:{'state':'ACTIVE','category':'DATA_FLOW','subject':'u'},other:{'state':'PRESENT','category':'USER_PROFILE','subject':'v'}}
    edges=[(c,b,f),(b,a,f),(a,b,f)]
    assert simulate(state,[],edges)[a]['state']=='PRESENT'
    actions=[step('DISABLE_DATA_FLOW','integration_service','f'),step('DELETE_RECORD','search_service','b')]
    after=simulate(state,actions,edges)
    assert after[a]['state']==after[b]['state']=='ABSENT' and after[c]==state[c] and after[other]==state[other]
    assert simulate(after,actions,edges)==after

def test_holdout_bijective_rename():
    fs=[fact('account_service','a','USER_PROFILE','PRESENT')]
    old=result(fs)
    from dataclasses import replace
    new=result([replace(fs[0],resource_id='renamed')])
    assert [{**s,'resource_id':'renamed'} for s in old['steps']]==new['steps']

def test_holdout_legal_hold_expiry():
    p=Policy([dict(rule_id='hold',data_category='LEGAL_HOLD_RECORD',condition='A supplied legal hold is active',required_action='RETAIN')])
    f=fact('s','h','LEGAL_HOLD_RECORD','PRESENT',payload={'hold_active':False,'hold_until':'2025-01-01T00:00:00Z'})
    with pytest.raises(Unresolved):p.obligation(f,AT)

def test_holdout_missing_retained_not_restore():
    r=result([fact('account_service','acct','USER_PROFILE','ABSENT'),fact('security_service','sec','SECURITY_AUDIT_LOG','ABSENT')])
    assert r['unresolved'] and all(s['operation']!='RESTORE_RECORD' for s in r['steps'])
