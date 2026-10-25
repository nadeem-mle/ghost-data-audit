"""Conservative plan simulation graph, never an observed topology or finding.

The caller must pass only latest, cutoff-eligible facts already admitted for one
subject, and policy obligations for those same physical copies. This module does
not search global evidence, infer ownership, or manufacture resource identifiers.
Potential edges deliberately overapproximate unknown routing between *known*
copies. Endpoint underdetermination remains a coverage limit: this graph cannot
certify that all real-world copies or recreation routes have been discovered.
"""
from collections.abc import Mapping

from .model import Fact


def key(fact):
    return fact.system_id, fact.resource_id, fact.copy_id


def build_graph(selected: list[Fact], obligations: Mapping, subject: str):
    """Return ``state``, simulation ``edges``, and separate provenance/limits.

    Each edge is (source_key, target_key, control_key), accepted by simulate().
    Provenance labels edges ``explicit`` only when both endpoints are supplied
    and match admitted copies; other edges are ``potential`` assumptions, never
    citation evidence. BACKUP_ARCHIVE controls require BLOCK_RESTORE, independently
    of DATA_FLOW controls requiring DISABLE_DATA_FLOW.
    """
    facts = {key(f): f for f in selected}
    if len(facts) != len(selected):
        raise ValueError('graph requires one selected fact per physical copy')
    state = {k: {'state': f.state, 'category': f.category, 'subject': subject}
             for k, f in sorted(facts.items())}
    targets = {k for k in facts if obligations.get(k) in ('DELETE', 'REDACT', 'ANONYMIZE')}
    records = {k for k, f in facts.items() if f.category not in ('DATA_FLOW', 'BACKUP_ARCHIVE')}
    provenance = []
    limits = []

    def endpoints(control, side, pool):
        payload = control.payload
        resource = payload.get(side + '_resource_id')
        system = payload.get(side + '_system_id', payload.get(side + '_system'))
        copy = payload.get(side + '_copy_id')
        specified = any(value is not None for value in (resource, system, copy))
        matches = {k for k in pool if (resource is None or k[1] == resource)
                   and (system is None or k[0] == system)
                   and (copy is None or k[2] == copy)}
        # A system-only selector still leaves individual resources unspecified.
        grounded = resource is not None and bool(matches)
        return matches, specified, grounded

    for control_key, control in sorted(facts.items()):
        if control.category not in ('DATA_FLOW', 'BACKUP_ARCHIVE'):
            continue
        sources = records if control.category == 'DATA_FLOW' else {control_key}
        src, src_specified, src_grounded = endpoints(control, 'source', sources)
        dst, dst_specified, dst_grounded = endpoints(control, 'target', targets)
        if control.category == 'BACKUP_ARCHIVE':
            # The admitted archive is the retained restore source and control.
            src = {control_key}
            src_grounded = True
        explicit = src_grounded and dst_grounded
        if not explicit:
            limits.append({'control': control_key,
                           'reason': 'source/destination underdetermined; only admitted known copies modeled'})
        # Unspecified routing is an assumption only for an enabled control.
        # Explicit disabled links remain useful for checking plan idempotency.
        if not explicit and control.state != 'ACTIVE':
            continue
        if (src_specified and not src) or (dst_specified and not dst):
            limits.append({'control': control_key,
                           'reason': 'explicit endpoint has no admitted matching copy'})
            continue
        for source in sorted(src):
            for target in sorted(dst):
                if source == target:
                    continue
                edge = source, target, control_key
                provenance.append({
                    'edge': edge,
                    'kind': 'explicit' if explicit else 'potential',
                    'control_category': control.category,
                    'required_control_state': 'DISABLED' if control.category == 'DATA_FLOW' else 'BLOCKED',
                    'admitted_sources': tuple((facts[k].source_id, facts[k].source_location)
                                              for k in (source, target, control_key)),
                })
    return {
        'state': state,
        'edges': tuple(item['edge'] for item in provenance),
        'provenance': tuple(provenance),
        'assumptions': (
            'Input facts are already admitted to one subject at the audit cutoff.',
            'Potential edges overapproximate routing among known copies only; retained identifiable sources may recreate prohibited targets.',
            'Simulation and edge provenance cannot establish observed findings, output identifiers, citations, or deletion labels.',
        ),
        'coverage_limits': tuple(limits),
    }
