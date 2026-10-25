"""Contract-scoped obligations, with no mandatory fictional account resource."""
import json
from audit.engine import Auditor, Policy
from test_core import fact, result, store, RULES, REQ, expected


SEARCH_RULE={'rule_id':'independent-search-rule','data_category':'SEARCH_INDEX_ENTRY',
             'condition':'Always','required_action':'DELETE'}


def test_proven_secondary_violation_does_not_require_invented_account_id():
    r=result([fact('search_service','search-real','SEARCH_INDEX_ENTRY','PRESENT')], RULES+[SEARCH_RULE])
    assert not r['unresolved'] and r['status']=='INCOMPLETE'
    assert r['steps']==expected(
        ('FINDING','search_service','search-real','REPORT_REMAINING_RECORD','PRESENT','source_A'),
        ('REMEDIATION','search_service','search-real','DELETE_RECORD','ABSENT',''),
        ('VERIFICATION','search_service','search-real','VERIFY_RECORD_ABSENT','ABSENT',''))
    assert not any(s['system_id']=='account_service' for s in r['steps'])


def test_supplied_compliant_scope_can_verify_without_account_category():
    r=result([fact('search_service','search-real','SEARCH_INDEX_ENTRY','ABSENT')], RULES+[SEARCH_RULE])
    assert not r['unresolved'] and r['status']=='COMPLETE'
    assert r['steps']==expected(('VERIFICATION','search_service','search-real','VERIFY_RECORD_ABSENT','ABSENT','source_A'))


def test_no_observations_still_cannot_claim_empty_complete():
    r=result([])
    assert r['status'] is None and not r['steps']
    assert any('cannot certify empty completion' in x for x in r['unresolved'])


def test_catalog_only_link_is_out_of_plan_and_does_not_block():
    # Labeled samples never include resources known only from a catalog link.
    s=store([fact('search_service','search-real','SEARCH_INDEX_ENTRY','ABSENT')])
    s.activities=[dict(event_time=REQ['audit_at'],event_type='LINK_RESOURCE_IDENTITY',activity_id='activity_x',
                       details='Linked subject@example.test to account-real',
                       target_system='account_service',resource_id='account-real')]
    r=Auditor(s,Policy(RULES+[SEARCH_RULE]),False).audit(REQ)
    assert r['catalog_only_resources']==[['account_service','account-real']]
    assert not any(x['resource_id']=='account-real' for x in r['steps'])


def test_explicit_cross_resource_reference_still_requires_missing_target():
    s=store([fact('search_service','search-real','SEARCH_INDEX_ENTRY','PRESENT',
                  payload={'subject_reference':'user_x','source_resource_id':'account-real'})])
    r=Auditor(s,Policy(RULES+[SEARCH_RULE]),False).audit(REQ)
    assert r['status']=='INCOMPLETE' and r['unresolved']
    assert r['scope']['missing_linked_resources']==[['account_service','account-real']]


def test_cli_and_independent_validator_support_non_account_scope(tmp_path):
    from test_cli import dataset, write
    import subprocess,sys
    from pathlib import Path
    d=dataset(tmp_path)
    write(d/'deletion_rules.csv',list(SEARCH_RULE),[SEARCH_RULE])
    (d/'evidence/record.json').write_text(json.dumps({'records':[dict(
        record_type='SEARCH_INDEX_ENTRY',observed_at='2026-01-02T00:00:00Z',
        system='search_service',resource_id='search-real',result='NOT_FOUND',subject_reference='u')]}))
    code=Path(__file__).resolve().parents[1];out=tmp_path/'output.csv'
    run=subprocess.run([sys.executable,str(code/'main.py'),'--dataset',str(d),'--output',str(out),
                        '--run-dir',str(tmp_path/'run'),'--no-llm'],capture_output=True,text=True)
    assert run.returncode==0,run.stdout+run.stderr
    validation=subprocess.run([sys.executable,str(code/'validate_output.py'),'--dataset',str(d),
                               '--output',str(out)],capture_output=True,text=True)
    assert validation.returncode==0,validation.stdout+validation.stderr
