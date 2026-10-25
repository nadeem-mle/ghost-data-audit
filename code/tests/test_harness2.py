"""Unit tests for Harness 2.0 checkers (no engine run, no provider calls)."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('harness2', Path(__file__).resolve().parents[1] / 'evaluation/harness2.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
EV = {'evidence_01', 'activity_01', 'audit_01'}


def step(n, op, system='account_service', resource='account_1', ev=''):
    return dict(step_no=n, phase=h.OP_PHASE[op], system_id=system, resource_id=resource,
                operation=op, state=h.OP_STATE[op], evidence_id=ev)


def good_incomplete():
    return [step(1, 'REPORT_REMAINING_RECORD', ev='evidence_01'), step(2, 'DELETE_RECORD'), step(3, 'VERIFY_RECORD_ABSENT')]


def test_valid_rows_have_no_violations():
    assert h.check_case('c', 'INCOMPLETE', good_incomplete(), EV) == []
    assert h.check_case('c', 'COMPLETE', [step(1, 'VERIFY_RECORD_ABSENT', ev='audit_01')], EV) == []
    assert h.check_case('c', 'NOT_APPLICABLE', [], EV) == []


def test_status_step_consistency():
    assert 'NOT_APPLICABLE with steps' in h.check_case('c', 'NOT_APPLICABLE', good_incomplete(), EV)
    v = h.check_case('c', 'COMPLETE', [step(1, 'REPORT_REMAINING_RECORD', ev='evidence_01'), step(2, 'VERIFY_RECORD_ABSENT')], EV)
    assert 'COMPLETE has FINDING step' in v and 'COMPLETE verification without evidence' in v
    bad = good_incomplete(); bad[2]['evidence_id'] = 'evidence_01'
    assert 'INCOMPLETE VERIFICATION cites evidence' in h.check_case('c', 'INCOMPLETE', bad, EV)
    assert 'invalid status' in h.check_case('c', None, [], EV)[0]


def test_numbering_order_schema_and_evidence_existence():
    s = good_incomplete(); s[1]['step_no'] = 5
    assert 'step numbering' in h.check_case('c', 'INCOMPLETE', s, EV)
    s = good_incomplete(); s[0], s[1] = s[1], s[0]; s[0]['step_no'], s[1]['step_no'] = 1, 2
    assert 'phase/operation/system/resource order' in h.check_case('c', 'INCOMPLETE', s, EV)
    s = good_incomplete(); s[0]['state'] = 'ABSENT'
    assert any(x.startswith('schema: state') for x in h.check_case('c', 'INCOMPLETE', s, EV))
    s = good_incomplete(); s[0]['evidence_id'] = 'evidence_99'
    assert 'evidence_id not in evidence_files/system_activity/user_audit_log' in h.check_case('c', 'INCOMPLETE', s, EV)
    s = good_incomplete(); del s[0]['state']
    assert any(x.startswith('schema: step keys') for x in h.check_case('c', 'INCOMPLETE', s, EV))


def test_root_cause_signatures_group_by_operation_and_system():
    label = good_incomplete()
    pred = label[:2]
    assert h.diff_signatures('INCOMPLETE', pred, 'INCOMPLETE', label) == ['missing VERIFY_RECORD_ABSENT account_service (empty-evidence)']
    assert h.diff_signatures('INCOMPLETE', label, 'INCOMPLETE', label) == []
    assert 'status COMPLETE -> None' in h.diff_signatures(None, label, 'COMPLETE', label)


def test_scorecard_diff_reports_changes():
    def sc(label, exact, status_acc):
        return {'label': label, 'samples': {'status_accuracy': [status_acc, 32], 'exact_plan': [exact, 32],
                'evidence_id_accuracy': [1, 2], 'ordering_canonical': [32, 32], 'verification_coverage': [1, 32],
                'step_precision': 1, 'step_recall': 1, 'step_f1': 1, 'false_complete': 0, 'wrongful_deletion': 0,
                'unresolved': 0, 'field_accuracy': {}, 'per_case': {'case_01': {'exact': exact > 9, 'status': 'COMPLETE'}}}}
    d = h.diff(sc('a', 9, 29), sc('b', 10, 30))
    assert d['metric_changes']['samples.exact_plan'] == [9, 10]
    assert d['samples_newly_exact'] == ['case_01'] and d['samples_newly_broken'] == []


def test_offline_by_default():
    assert h.run_engine.__defaults__[-2] is None  # llm=None
