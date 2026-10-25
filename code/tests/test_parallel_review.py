"""Independent retention and checker regressions from the parallel review.

Only synthetic records are used. Missing retention evidence is not supplied by
sample answers, another subject's period, or a later capture.
"""
import hashlib
from dataclasses import replace
from types import SimpleNamespace

import pytest

from audit.engine import Auditor, Policy, Unresolved
from audit.model import Fact
from validate_output import verify_evidence
from test_core import AT, REQ, RULES, fact, result


@pytest.mark.parametrize('until', [
    '2026-09-01T12:00:00Z',
    '2026-09-01T17:00:00+05:00',
    '2027-01-01T00:00:00Z',
])
def test_supplied_retention_eligibility_inclusive(until):
    record = fact('security_service', 'security', 'SECURITY_AUDIT_LOG', 'PRESENT',
                  payload={'subject_reference': 'user_x', 'retention_until': until})
    action, proof = Policy(RULES).obligation(record, AT)
    assert action == 'RETAIN'
    assert proof['condition'] == 'Record is within the supplied retention period'


# Updated 2026-10-25: rule_12 now treats a missing retention date as retained
# (all labeled samples retain audit records without a per-record expiry). The
# old tests asserted a "retention period not supplied" blocker; the invariants
# kept below are no deletion of retained records and no borrowed evidence.
def test_missing_retention_retains_without_deletion_or_invented_expiry():
    audit = result([
        fact('account_service', 'account', 'USER_PROFILE', 'ABSENT'),
        fact('security_service', 'security', 'SECURITY_AUDIT_LOG', 'PRESENT'),
    ])
    assert not any('retention' in gap for gap in audit['unresolved'])
    assert not any(step['operation'] == 'DELETE_RECORD' for step in audit['steps'])
    security_proof = [p for p in audit['ledger'] if p['resource'] == 'security']
    assert security_proof and security_proof[0]['result'] == 'PROVEN_COMPLIANT'
    assert 'retention_until' not in security_proof[0]['policy_metadata']


def test_expired_retention_still_blocks_without_deletion():
    audit = result([
        fact('account_service', 'account', 'USER_PROFILE', 'ABSENT'),
        fact('security_service', 'security', 'SECURITY_AUDIT_LOG', 'PRESENT',
             payload={'subject_reference': 'user_x', 'retention_until': '2026-01-01T00:00:00Z'}),
    ])
    assert any(gap.startswith('security:') for gap in audit['unresolved'])
    assert audit['status'] is None
    assert not any(step['operation'] == 'DELETE_RECORD' for step in audit['steps'])


def test_other_resources_retention_period_is_not_a_policy_default():
    audit = result([
        fact('account_service', 'account', 'USER_PROFILE', 'ABSENT'),
        fact('security_service', 'security', 'SECURITY_AUDIT_LOG', 'PRESENT'),
        fact('security_service', 'unrelated_security', 'SECURITY_AUDIT_LOG', 'PRESENT',
             payload={'subject_reference': 'user_other',
                      'retention_until': '2030-01-01T00:00:00Z'}),
    ])
    proof = [p for p in audit['ledger'] if p['resource'] == 'security']
    assert proof and 'retention_until' not in proof[0]['policy_metadata']
    assert not any(step['resource_id'] == 'unrelated_security' for step in audit['steps'])


def test_future_capture_cannot_supply_missing_retention_metadata():
    audit = result([
        fact('account_service', 'account', 'USER_PROFILE', 'ABSENT'),
        fact('security_service', 'security', 'SECURITY_AUDIT_LOG', 'PRESENT'),
        fact('security_service', 'security', 'SECURITY_AUDIT_LOG', 'PRESENT',
             source='source_future', at='2026-08-31T10:00:00Z',
             available='2026-09-02T00:00:00Z',
             payload={'subject_reference': 'user_x',
                      'retention_until': '2030-01-01T00:00:00Z'}),
    ])
    proof = [p for p in audit['ledger'] if p['resource'] == 'security']
    assert proof and 'source_future' not in proof[0]['policy_metadata_sources']
    assert not any(step['evidence_id'] == 'source_future' for step in audit['steps'])


def test_earlier_same_resource_retention_metadata_remains_available():
    audit = result([
        fact('account_service', 'account', 'USER_PROFILE', 'ABSENT'),
        fact('security_service', 'security', 'SECURITY_AUDIT_LOG', 'PRESENT',
             source='source_old', at='2026-08-31T10:00:00Z',
             payload={'subject_reference': 'user_x',
                      'retention_until': '2030-01-01T00:00:00Z'}),
        fact('security_service', 'security', 'SECURITY_AUDIT_LOG', 'PRESENT',
             source='source_current'),
    ])
    assert audit['unresolved'] == []
    assert audit['status'] == 'COMPLETE'
    presence = [s for s in audit['steps'] if s['resource_id'] == 'security']
    assert len(presence) == 1
    assert presence[0]['operation'] == 'VERIFY_RECORD_PRESENT'
    assert presence[0]['evidence_id'] == 'source_current'


@pytest.mark.parametrize('category,payload,condition', [
    ('SECURITY_AUDIT_LOG', {'retention_until': '2026-08-31T23:59:59Z'},
     'Record is within the supplied retention period'),
    ('LEGAL_HOLD_RECORD', {'hold_active': False, 'retained_until': '2030-01-01T00:00:00Z'},
     'A supplied legal hold is active'),
])
def test_expired_or_inactive_retention_does_not_invent_a_delete_rule(category, payload, condition):
    rules = [{'rule_id': 'arbitrary_policy_identifier', 'data_category': category,
              'condition': condition, 'required_action': 'RETAIN'}]
    with pytest.raises(Unresolved):
        Policy(rules).obligation(fact('retention', 'record', category, 'PRESENT', payload=payload), AT)


def _checker_fixture(tmp_path, *, observed=AT, category='SECURITY_AUDIT_LOG'):
    raw = b'explicit synthetic readback; resource=record; source source_check\n'
    (tmp_path / 'source.txt').write_bytes(raw)
    source = dict(file_id='source_check', file_path='source.txt', captured_at=AT)
    record = Fact('source_check', 'line:1', 'security_service', 'record', 'primary',
                  category, 'PRESENT', observed, AT,
                  {'subject_reference': 'user_x', 'retention_until': '2030-01-01T00:00:00Z'})
    store = SimpleNamespace(root=tmp_path, manifest=[source],
                            coverage=[{**source, 'status': 'ok', 'sha256': hashlib.sha256(raw).hexdigest()}],
                            facts=[record], inventories=[])
    proof = dict(system='security_service', resource='record', copy='primary',
                 obligation='RETAIN', state='PRESENT', result='PROVEN_COMPLIANT',
                 source='source_check', location='line:1', observed_at=AT, available_at=AT,
                 rule={'data_category': 'SECURITY_AUDIT_LOG', 'required_action': 'RETAIN'})
    audit = dict(case_id=REQ['case_id'], unresolved=[], ledger=[proof], steps=[])
    return store, audit


def test_independent_checker_rejects_forged_observation_time(tmp_path):
    store, audit = _checker_fixture(tmp_path, observed='2026-09-02T00:00:00Z')
    with pytest.raises(AssertionError):
        verify_evidence(store, [audit], [REQ])


def test_independent_checker_rejects_forged_category(tmp_path):
    store, audit = _checker_fixture(tmp_path, category='USER_PROFILE')
    with pytest.raises(AssertionError):
        verify_evidence(store, [audit], [REQ])

@pytest.mark.parametrize('separator',[':', '       ', '\n'])
def test_labelled_pdf_retention_extracted_without_global_default(separator):
    from audit.ingest import Store
    text='Event reference audit_record_test\nsubject reference user_03\nretain until 25 Aug 2027 04'+separator+'03 UTC'
    # Use the documented resource grammar and an independent literal expected expiry.
    text=text.replace('audit_record_test','audit_record_003')
    store=Store.__new__(Store);store.facts=[];store.documents={}
    manifest=dict(file_id='synthetic_pdf',file_path='evidence/source.pdf',captured_at=AT)
    store.document(manifest,text,'page:1')
    assert len(store.facts)==1
    assert store.facts[0].payload['retention_until']=='2027-08-25T04:03:00Z'
    assert store.facts[0].observed_at==AT  # An event date is not a fabricated readback time.
