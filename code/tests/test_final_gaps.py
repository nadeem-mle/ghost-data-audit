import pytest
from audit.ingest import Store
from test_ingestion import bare,M

def test_collection_service_does_not_replace_explicit_business_system():
    s=bare();s.log_file(M,'2026-09-01T10:00:00Z INFO service=collection_router event=record_lookup system="account_service" resource_id="a" record_type="USER_PROFILE" result="NOT_FOUND" subject_reference="person@example.test"')
    assert len(s.facts)==1
    assert s.facts[0].system_id=='account_service' and s.facts[0].state=='ABSENT'

def test_trace_collision_between_services_does_not_transfer_identity():
    s=bare();s.log_file(M,'2026-09-01T10:00:00Z service=search_service trace_id=x event=start lookup_key=person@example.test\n2026-09-01T10:00:01Z service=account_service trace_id=x event=profile_lookup_completed resource_id=a rows=1')
    assert len(s.facts)==1 and 'lookup_key' not in s.facts[0].payload

def test_export_owner_key_is_indexable():
    from audit.engine import tokens
    assert 'person@example.test' in tokens({'owner_key':'person@example.test'})

def test_retention_register_is_grounded_provenance_not_a_new_business_record():
    s=bare();text='DISPUTED ORDERS AND TAX RECORDS REGISTER\nORD-ABC | user_01 | Tax correction | Retain until 04 May 2033'
    s.document(M,text,'page:1')
    assert M['file_id'] in s.metadata_documents and not s.facts

def test_other_document_is_not_silently_classified_as_metadata():
    s=bare();s.document(M,'Account data user_01 email person@example.test','page:1')
    assert M['file_id'] not in getattr(s,'metadata_documents',set())

def test_recycled_resource_is_not_deleted_for_prior_owner():
    from test_core import fact,store,REQ,RULES,AT
    from audit.engine import Auditor,Policy
    fs=[fact('account_service','reused','USER_PROFILE','PRESENT',at='2026-08-01T00:00:00Z'),fact('account_service','reused','USER_PROFILE','PRESENT',payload={'user_id':'user_other','email':'other@example.test'})]
    s=store(fs)
    result=Auditor(s,Policy(RULES),False).audit(REQ)
    assert result['unresolved'] and not any(x['operation']=='DELETE_RECORD' for x in result['steps'])

def test_unknown_directory_user_is_still_an_explicit_foreign_owner():
    from test_core import fact,result
    r=result([fact('account_service','foreign','USER_PROFILE','PRESENT',payload={'user_id':'user_not_in_directory','email':'subject@example.test'})])
    assert r['unresolved'] and not any(x['operation']=='DELETE_RECORD' for x in r['steps'])

def test_unblocked_backup_presence_is_a_restore_risk_not_a_deletion():
    # An archive holding the subject with no restore block shown is restorable
    # (labeled sample: eligible=true, deletion_block=false -> REPORT_RESTORE_RISK).
    from test_core import fact,result
    r=result([fact('account_service','acct','USER_PROFILE','ABSENT'),fact('backup_service','archive','BACKUP_ARCHIVE','PRESENT')])
    assert r['status']=='INCOMPLETE'
    ops=[(s['operation'],s['resource_id']) for s in r['steps']]
    assert ('REPORT_RESTORE_RISK','archive') in ops and ('BLOCK_RESTORE','archive') in ops and ('VERIFY_RESTORE_BLOCKED','archive') in ops
    assert ('DELETE_RECORD','archive') not in ops

def test_unknown_completion_is_withheld_not_emitted_as_complete():
    from test_core import result
    r=result([])
    assert r['status'] is None and r['unresolved']

def test_presence_only_readback_does_not_erase_explicit_archive_control():
    from dataclasses import replace
    from test_core import fact,result
    archive=fact('backup_service','archive','BACKUP_ARCHIVE','BLOCKED',at='2026-08-31T00:00:00Z')
    presence=replace(fact('backup_service','archive','BACKUP_ARCHIVE','PRESENT'),coverage_scope='presence')
    r=result([fact('account_service','acct','USER_PROFILE','ABSENT'),archive,presence])
    assert r['status']=='COMPLETE' and not r['unresolved']
    assert any(s['operation']=='VERIFY_RESTORE_BLOCKED' for s in r['steps'])

@pytest.mark.parametrize('event,details,category,state',[
 ('CHECK_DATA_FLOW','Connector status check confirmed that data flow route remains enabled.','DATA_FLOW','ACTIVE'),
 ('CHECK_DATA_FLOW','Connector status check confirmed that data flow route remains disabled.','DATA_FLOW','DISABLED'),
 ('CHECK_RESTORE_ACCESS','Restore-access check confirmed that archive route can still be restored.','BACKUP_ARCHIVE','ACTIVE'),
 ('CHECK_RESTORE_ACCESS','Restore-access check confirmed that archive route is blocked from restore.','BACKUP_ARCHIVE','BLOCKED'),
])
def test_explicit_activity_readbacks_are_admitted(tmp_path,event,details,category,state):
    s=bare();s.root=tmp_path;s.extra_sources={};(tmp_path/'system_activity.csv').write_text('synthetic readback CSV')
    s.activities=[dict(activity_id='activity_real',event_time='2026-09-01T10:00:00Z',event_type=event,target_system='control_service',resource_id='route',details=details,reported_result='FAILED')]
    s.activity_readbacks()
    assert len(s.facts)==1 and s.facts[0].source_id=='activity_real' and s.facts[0].category==category and s.facts[0].state==state

@pytest.mark.parametrize('event,detail',[
 ('DISABLE_DATA_FLOW','Policy action completed for route.'),
 ('CHECK_DATA_FLOW','The operation reported SUCCESS.'),
 ('CHECK_RESTORE_ACCESS','Restore requested but not read back.'),
])
def test_workflow_claim_is_not_a_state_readback(tmp_path,event,detail):
    s=bare();s.root=tmp_path;s.extra_sources={};(tmp_path/'system_activity.csv').write_text('synthetic')
    s.activities=[dict(activity_id='a',event_time='2026-09-01T10:00:00Z',event_type=event,target_system='control',resource_id='route',details=detail)]
    s.activity_readbacks();assert not s.facts

def test_copy_category_conflict_does_not_delete_retained_copy():
    from test_core import fact,result,RULES
    rules=RULES+[{'rule_id':'tomb','data_category':'ACCOUNT_TOMBSTONE','condition':'Account is deleted and only a stable internal user_id is needed to preserve references to retained records','required_action':'REDACT'}]
    r=result([fact('account_service','acct','USER_PROFILE','PRESENT',copy_id='replica'),fact('account_service','acct','ACCOUNT_TOMBSTONE','REDACTED',payload={'subject_reference':'user_x','account_status':'DELETED'})],rules)
    assert r['unresolved'] and not any(s['operation']=='DELETE_RECORD' for s in r['steps'])

def test_deduplicated_finding_uses_newest_actual_violating_copy():
    from test_core import fact,result
    r=result([fact('account_service','acct','USER_PROFILE','PRESENT',source='earlier',copy_id='replica_a',at='2026-08-31T00:00:00Z'),fact('account_service','acct','USER_PROFILE','PRESENT',source='later',copy_id='replica_b')])
    findings=[s for s in r['steps'] if s['phase']=='FINDING']
    assert len(findings)==1 and findings[0]['evidence_id']=='later'

@pytest.mark.parametrize('text',[
 'Delete my account if my refund clears. Contact me if you need help.',
 'Delete my account only if necessary, and retain security logs if required.',
 'Elimina mi cuenta si se procesa el reembolso.',
 'Keep my account active but delete my old export.',
])
def test_other_allowed_condition_does_not_fabricate_authorization(text):
    from audit.engine import intent,Unresolved
    with pytest.raises(Unresolved):intent(text)

@pytest.mark.parametrize('text',[
 'Please delete my account. Contact me if you need anything.',
 'Completa la eliminación si hace falta.',
])
def test_supported_administrative_or_remaining_data_condition(text):
    from audit.engine import intent
    assert intent(text)=='YES'
