"""Workflow attribution of deletion-worker profile jobs (synthetic data only)."""
from test_core import AT, RULES, fact, store
from audit.engine import Auditor, Policy

REQ = dict(case_id='wf', email='subject@example.test', requested_at='2026-08-30T12:00:00Z',
           reported_status='COMPLETE', reported_at='2026-08-31T12:00:00Z', audit_at=AT,
           request_text='Please delete my account')


def job(rid, time='2026-08-31T11:00:00Z', result='SUCCESS'):
    return dict(activity_id='a_' + rid, event_time=time, event_type='DELETE_RECORD',
                source_system='deletion_worker', target_system='account_service',
                resource_id=rid, reported_result=result, details='Deletion worker submitted ' + rid)


def run(facts, jobs):
    s = store(facts); s.activities = jobs
    return Auditor(s, Policy(RULES), adaptive=False).audit(REQ)


def test_unique_matching_job_links_account_and_cites_absence():
    r = run([fact('security_service', 'sec', 'SECURITY_AUDIT_LOG', 'PRESENT'),
             fact('account_service', 'acct', 'USER_PROFILE', 'ABSENT', payload={})], [job('acct')])
    assert r['status'] == 'COMPLETE'
    assert any(x['resource_id'] == 'acct' and x['operation'] == 'VERIFY_RECORD_ABSENT' and x['evidence_id'] == 'source_A' for x in r['steps'])


def test_ambiguous_or_mismatched_jobs_are_not_linked():
    facts = [fact('security_service', 'sec', 'SECURITY_AUDIT_LOG', 'PRESENT')]
    assert not any(x['resource_id'].startswith('acct') for x in run(facts, [job('acct1'), job('acct2')])['steps'])
    assert not any(x['resource_id'] == 'acct' for x in run(facts, [job('acct', result='FAILED')])['steps'])


def test_weak_link_never_deletes_unattributed_present_record():
    r = run([fact('security_service', 'sec', 'SECURITY_AUDIT_LOG', 'PRESENT'),
             fact('account_service', 'acct', 'USER_PROFILE', 'PRESENT', payload={'note': 'no identifiers'})], [job('acct')])
    assert r['status'] is None
    assert not any(x['operation'] in ('DELETE_RECORD', 'REPORT_REMAINING_RECORD') for x in r['steps'])


def test_unobserved_weak_link_cannot_certify_complete():
    r = run([fact('security_service', 'sec', 'SECURITY_AUDIT_LOG', 'PRESENT')], [job('acct')])
    assert r['status'] is None and any('workflow-attributed' in u for u in r['unresolved'])


def test_pre_request_not_found_lookup_does_not_attribute_account():
    stale = fact('account_service', 'stale', 'USER_PROFILE', 'ABSENT', at='2026-03-10T06:18:01Z', available='2026-03-10T06:18:01Z',
                 payload={'lookup_key': 'subject@example.test', 'rows': '0', 'http_status': '404'})
    fresh = fact('account_service', 'fresh', 'USER_PROFILE', 'ABSENT',
                 payload={'lookup_key': 'subject@example.test', 'rows': '0'})
    steps = run([fact('security_service', 'sec', 'SECURITY_AUDIT_LOG', 'PRESENT'), stale, fresh], [])['steps']
    ids = {x['resource_id'] for x in steps}
    assert 'stale' not in ids and 'fresh' in ids
