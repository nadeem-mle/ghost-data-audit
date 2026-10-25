"""Subject-scoped graph behavior, specified independently of sample answers."""
from audit.flows import build_graph, key
from audit.model import Fact, step
from audit.simulate import simulate


def fact(resource, category, state, payload=None, system='service'):
    return Fact('visible_' + resource, 'record', system, resource, 'primary',
                category, state, '2026-01-01T00:00:00Z',
                '2026-01-01T00:00:00Z', payload or {})


def test_potential_cycle_retained_source_and_idempotency():
    a = fact('a', 'USER_PROFILE', 'ABSENT')
    b = fact('b', 'SEARCH_INDEX_ENTRY', 'ABSENT')
    retained = fact('retained', 'LEGAL_HOLD_RECORD', 'PRESENT')
    flow = fact('flow', 'DATA_FLOW', 'ACTIVE')
    graph = build_graph([a, b, retained, flow],
                        {key(a): 'DELETE', key(b): 'DELETE', key(retained): 'RETAIN', key(flow): 'DISABLE'}, 'subject')
    assert (key(a), key(b), key(flow)) in graph['edges']
    assert (key(b), key(a), key(flow)) in graph['edges']
    assert all(p['kind'] == 'potential' for p in graph['provenance'])
    assert graph['coverage_limits']
    recreated = simulate(graph['state'], [], graph['edges'])
    assert recreated[key(a)]['state'] == recreated[key(b)]['state'] == 'PRESENT'
    actions = [step('DISABLE_DATA_FLOW', 'service', 'flow'),
               step('DELETE_RECORD', 'service', 'a'), step('DELETE_RECORD', 'service', 'b')]
    after = simulate(graph['state'], actions, graph['edges'])
    assert after[key(a)]['state'] == after[key(b)]['state'] == 'ABSENT'
    assert after[key(retained)] == graph['state'][key(retained)]
    assert simulate(after, actions, graph['edges']) == after
    assert graph['state'][key(flow)]['state'] == 'ACTIVE'


def test_explicit_links_do_not_expand_to_other_known_targets():
    source = fact('source', 'SECURITY_AUDIT_LOG', 'PRESENT')
    target = fact('target', 'USER_PROFILE', 'ABSENT')
    other = fact('other', 'USER_PROFILE', 'ABSENT')
    control = fact('flow', 'DATA_FLOW', 'ACTIVE',
                   {'source_resource_id': 'source', 'target_resource_id': 'target'})
    graph = build_graph([source, target, other, control],
                        {key(target): 'DELETE', key(other): 'DELETE'}, 'subject')
    assert graph['edges'] == ((key(source), key(target), key(control)),)
    assert graph['provenance'][0]['kind'] == 'explicit'
    assert not graph['coverage_limits']
    assert simulate(graph['state'], [], graph['edges'])[key(other)]['state'] == 'ABSENT'


def test_disabled_flow_does_not_recreate_or_assume_routes():
    source = fact('source', 'LEGAL_HOLD_RECORD', 'PRESENT')
    target = fact('target', 'USER_PROFILE', 'ABSENT')
    control = fact('flow', 'DATA_FLOW', 'DISABLED')
    graph = build_graph([source, target, control], {key(target): 'DELETE'}, 'subject')
    assert graph['edges'] == ()
    assert simulate(graph['state'], [], graph['edges']) == graph['state']


def test_backup_requires_its_own_restore_block():
    backup = fact('backup', 'BACKUP_ARCHIVE', 'ACTIVE')
    target = fact('target', 'USER_PROFILE', 'ABSENT')
    flow = fact('flow', 'DATA_FLOW', 'ACTIVE')
    graph = build_graph([backup, target, flow], {key(target): 'DELETE'}, 'subject')
    restore = next(p for p in graph['provenance'] if p['control_category'] == 'BACKUP_ARCHIVE')
    assert restore['required_control_state'] == 'BLOCKED'
    assert simulate(graph['state'], [], graph['edges'])[key(target)]['state']=='PRESENT'
    # Restore recreation is simulated, never admitted as observed evidence.
    assert restore['edge'] == (key(backup), key(target), key(backup))
    actions = [step('DISABLE_DATA_FLOW', 'service', 'flow'), step('BLOCK_RESTORE', 'service', 'backup')]
    after = simulate(graph['state'], actions, graph['edges'])
    assert after[key(backup)]['state'] == 'BLOCKED'
    assert after[key(target)]['state'] == 'ABSENT'


def test_only_admitted_subject_copies_are_nodes_or_endpoints():
    target = fact('target', 'USER_PROFILE', 'ABSENT')
    control = fact('flow', 'DATA_FLOW', 'ACTIVE',
                   {'source_resource_id': 'unrelated_not_admitted', 'target_resource_id': 'target'})
    graph = build_graph([target, control], {key(target): 'DELETE'}, 'subject')
    assert set(graph['state']) == {key(target), key(control)}
    assert not graph['edges']
    assert any('no admitted' in gap['reason'] for gap in graph['coverage_limits'])
