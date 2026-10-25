"""Join supplied policy metadata without inferring retention from category names.

Retention belongs to a logical record, so a primary readback can establish the
period for its replica. It cannot establish a period for a different record,
and a future capture cannot fill a historical proof gap.
"""
from dataclasses import replace
from datetime import datetime
import re

from .model import Unresolved, stamp


def policy_context(fact, facts, cutoff):
    """Return a fact with latest, cutoff-eligible record policy metadata.

    Readback state and its provenance remain unchanged. Metadata source IDs are
    returned separately so callers can preserve the additional proof references.
    Conflicting values at the latest metadata observation are unresolved; file
    order and replica selection never decide the applicable retention period.
    """
    if fact.category not in ('SECURITY_AUDIT_LOG', 'LEGAL_HOLD_RECORD'):
        return fact, ()
    related = [f for f in facts if f.eligible(cutoff)
               and (f.system_id, f.resource_id, f.category) ==
               (fact.system_id, fact.resource_id, fact.category)]
    aliases = ('retention_until', 'retained_until') if fact.category == 'SECURITY_AUDIT_LOG' else ('hold_until', 'retained_until')
    payload = dict(fact.payload)
    sources = set()
    for target, keys in [('retention_until' if fact.category == 'SECURITY_AUDIT_LOG' else 'hold_until', aliases),
                         ('hold_active', ('hold_active',))]:
        observations = []
        for other in related:
            for key in keys:
                value = other.payload.get(key)
                if value is None or value == '':
                    continue
                if target == 'hold_active':
                    if type(value) is not bool:
                        raise Unresolved('legal hold active flag is not an explicit boolean')
                    normalized = value
                else:
                    normalized = stamp(value)
                observations.append((stamp(other.observed_at), normalized, value, other.source_id))
        if not observations:
            continue
        latest = max(o[0] for o in observations)
        current = [o for o in observations if o[0] == latest]
        if len({o[1] for o in current}) != 1:
            raise Unresolved('conflicting supplied ' + target + ' for logical record')
        # Remove aliases so downstream code cannot accidentally prefer an older
        # retained_until value over the latest hold_until value.
        for key in keys:
            payload.pop(key, None)
        payload[target] = current[0][2]
        sources.update(o[3] for o in current)
    return replace(fact, payload=payload), tuple(sorted(sources))


def legal_register_rows(text):
    """Extract explicit order/subject retention links, never resource IDs.

    Calendar dates remain calendar dates. A caller must join both identifiers
    to an admitted record and apply its date convention before policy use.
    """
    if 'DISPUTED ORDERS AND TAX RECORDS REGISTER' not in text.upper():
        return []
    pattern = re.compile(r'\b(ORD-[A-Za-z0-9-]+)\s*\|\s*(user_[A-Za-z0-9_-]+)\s*\|[^\n]*?\bRetain until\s+(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\b', re.I)
    return [dict(order_reference=m[1], subject_reference=m[2],
                 retention_date=datetime.strptime(m[3], '%d %b %Y').date().isoformat())
            for m in pattern.finditer(text)]
