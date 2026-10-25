"""Synthetic policy joins exercise identity scope, time and conflicting copies."""
from dataclasses import replace
import pytest

from audit.model import Fact, Unresolved
from audit.policy_support import legal_register_rows, policy_context

AT = '2026-06-01T00:00:00Z'
EARLIER = '2026-05-01T00:00:00Z'
UNTIL = '2027-01-01T00:00:00Z'


def fact(payload=None, **kw):
    base = Fact('readback', 'row', 'security_service', 'event_x', 'primary',
                'SECURITY_AUDIT_LOG', 'PRESENT', AT, AT, payload or {})
    return replace(base, **kw)


def test_retention_joins_same_logical_record_across_copies():
    readback = fact(copy_id='replica')
    metadata = fact({'retained_until': UNTIL}, source_id='period', observed_at=EARLIER)
    resolved, sources = policy_context(readback, [readback, metadata], AT)
    assert resolved.payload == {'retention_until': UNTIL}
    assert sources == ('period',)
    assert resolved.source_id == readback.source_id
    assert readback.payload == {}


def test_unrelated_or_future_metadata_cannot_fill_gap():
    readback = fact()
    candidates = [fact({'retention_until': UNTIL}, resource_id='other'),
                  fact({'retention_until': UNTIL}, system_id='other'),
                  fact({'retention_until': UNTIL}, category='LEGAL_HOLD_RECORD'),
                  fact({'retention_until': UNTIL}, available_at=UNTIL),
                  fact({'retention_until': UNTIL}, observed_at=UNTIL)]
    assert policy_context(readback, candidates, AT) == (readback, ())


def test_conflicting_replica_periods_remain_unresolved():
    a = fact({'retention_until': UNTIL})
    b = fact({'retention_until': '2028-01-01T00:00:00Z'}, copy_id='replica')
    with pytest.raises(Unresolved, match='conflicting supplied'):
        policy_context(a, [a, b], AT)


def test_latest_explicit_metadata_supersedes_old_metadata():
    old = fact({'retention_until': UNTIL}, observed_at=EARLIER)
    latest = fact({'retained_until': '2028-01-01T00:00:00Z'})
    resolved, _ = policy_context(old, [old, latest], AT)
    assert resolved.payload == {'retention_until': '2028-01-01T00:00:00Z'}


def test_legal_hold_false_and_latest_date_are_preserved():
    old = fact({'retained_until': UNTIL, 'hold_active': True},
               category='LEGAL_HOLD_RECORD', observed_at=EARLIER)
    current = fact({'hold_until': EARLIER, 'hold_active': False}, category='LEGAL_HOLD_RECORD')
    resolved, _ = policy_context(old, [old, current], AT)
    assert resolved.payload == {'hold_until': EARLIER, 'hold_active': False}


def test_equivalent_timezones_do_not_create_false_conflict():
    a = fact({'retention_until': UNTIL})
    b = fact({'retained_until': '2027-01-01T05:00:00+05:00'})
    assert policy_context(a, [a, b], AT)[0].payload['retention_until'] == UNTIL


def test_register_links_both_subject_and_order_without_inventing_resource():
    text = ('DISPUTED ORDERS AND TAX RECORDS REGISTER\n'
            '1 ORD-SYNTHETIC | user_synthetic | Card dispute | 04 May 2026 | USD 10 | Retain until 04 May 2033 | AR\n')
    assert legal_register_rows(text) == [dict(order_reference='ORD-SYNTHETIC',
        subject_reference='user_synthetic', retention_date='2033-05-04')]
    assert legal_register_rows(text.split('\n', 1)[1]) == []
