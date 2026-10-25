"""Participant-visible ownership-gap diagnostic, separate from prediction proof gates.

Run with ``python -m audit.ownership --dataset DATASET --results RESULTS --output REPORT``.
Potential candidates are deliberately reported for inspection, never admitted as facts.
"""
import argparse
from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import re
import shlex

from .engine import Auditor, Policy, norm
from .ingest import COLLECTIONS, SERVICES, Store
from .model import rows, stamp
from .safe_sql import snapshot


def string_values(obj):
    if isinstance(obj, dict):
        for value in obj.values():
            yield from string_values(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from string_values(value)
    elif isinstance(obj, str):
        yield obj


def selectors(obj):
    """Exact scalar selectors plus delimited email/user references in prose."""
    result = set()
    for value in string_values(obj):
        result.add(norm(value))
        result.update(norm(v) for v in re.findall(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', value))
        result.update(re.findall(r'\buser_\d+\b', value))
    return result


@dataclass(frozen=True)
class Candidate:
    source_id: str
    location: str
    resource_id: str
    observed_at: str
    available_at: str
    selectors: frozenset

    def matches(self, identifiers, cutoff):
        return (stamp(self.observed_at) <= stamp(cutoff)
                and stamp(self.available_at) <= stamp(cutoff)
                and bool(self.selectors & identifiers))


def structured_candidates(obj, manifest, system=None, at=None, location='$'):
    """Keep resource objects isolated; never join adjacent snapshot records."""
    if isinstance(obj, dict):
        system = obj.get('data_store', obj.get('system', system))
        at = obj.get('observed_at', obj.get('recorded_at', obj.get('captured_at', at)))
        if obj.get('collection') in COLLECTIONS:
            system = COLLECTIONS[obj['collection']][0]
        if 'resource_id' in obj:
            if system == 'account_service':
                yield Candidate(manifest['file_id'], location, obj['resource_id'],
                                at or manifest['captured_at'], manifest['captured_at'],
                                frozenset(selectors(obj)))
            return
        for key, value in obj.items():
            yield from structured_candidates(value, manifest, key if key in SERVICES else system,
                                             at, location + '.' + key)
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            yield from structured_candidates(value, manifest, system, at, f'{location}[{i}]')


def log_candidates(text, manifest):
    """Inspect every trace event, including events that cannot prove record state."""
    traces = {}
    for line_no, line in enumerate(text.splitlines(), 1):
        parts = shlex.split(line)
        if len(parts) < 2:
            continue
        if line.split(' ', 1)[1].startswith('{'):
            obj = json.loads(line.split(' ', 1)[1])
        else:
            obj = dict(p.split('=', 1) for p in parts[1:] if '=' in p)
            if 'message' in obj:
                obj.update(dict(p.split('=', 1) for p in shlex.split(obj.pop('message')) if '=' in p))
                obj['service'] = obj.pop('function')
                obj['trace_id'] = obj.pop('requestId')
            elif len(parts) > 5 and re.fullmatch(r'<\d+>1', parts[1]):
                obj.update(service=parts[3], trace_id=parts[4])
            elif len(parts) > 5 and parts[1].startswith('['):
                obj.update(service=parts[2].strip('[]'), trace_id=parts[3].strip('[]'))
            elif ' | ' in line:
                columns = line.split('|')
                if len(columns) >= 6:
                    obj.update(service=columns[2].strip(), trace_id=columns[3].strip())
        key = (obj.get('service'), obj.get('trace_id'))
        if key[1]:
            obj = {**traces.get(key, {}), **obj}
            traces[key] = obj
        if obj.get('system', obj.get('service')) == 'account_service' and obj.get('resource_id'):
            yield Candidate(manifest['file_id'], f'line:{line_no}', obj['resource_id'],
                            parts[0], manifest['captured_at'], frozenset(selectors(obj)))


def diagnose(store, results):
    candidates = []
    formats = Counter()
    for m in store.manifest:
        path = store.root / m['file_path']
        formats[path.suffix] += 1
        if path.suffix == '.json':
            candidates.extend(structured_candidates(json.loads(path.read_text()), m))
        elif path.suffix == '.sql':
            for table, records in snapshot(path.read_text()).items():
                for i, row in enumerate(records):
                    obj = json.loads(row['record_json']) if 'record_json' in row else row
                    system = row.get('origin_system', COLLECTIONS.get(table, (None,))[0])
                    candidates.extend(structured_candidates(obj, m, system=system,
                                                           location=f'{table}/row:{i+1}'))
        elif path.suffix == '.log':
            candidates.extend(log_candidates(path.read_text(), m))
    # Media/text facts preserve parser boundaries. Raw document co-occurrence is
    # separately exposed as a candidate for manual inspection, never ownership.
    for fact in store.facts:
        if fact.category == 'USER_PROFILE':
            candidates.append(Candidate(fact.source_id, fact.source_location, fact.resource_id,
                                        fact.observed_at, fact.available_at, frozenset(selectors(fact.payload))))
    auditor = Auditor(store, Policy([]))
    missing = {r['case_id'] for r in results if any('No grounded account' in x for x in r['unresolved'])}
    details = []
    for request in rows(store.root / 'deletion_requests.csv'):
        if request['case_id'] not in missing:
            continue
        identifiers, _ = auditor.identity(request)
        hits = [dict(source_id=c.source_id, location=c.location, resource_id=c.resource_id)
                for c in candidates if c.matches(identifiers, request['audit_at'])]
        activity_hits = [a['activity_id'] for a in store.activities
                         if stamp(a['event_time']) <= stamp(request['audit_at'])
                         and selectors(a['details']) & identifiers]
        details.append(dict(case_id=request['case_id'], raw_account_candidates=hits,
                            identity_bearing_activities=activity_hits))
    return dict(purpose='Diagnostic only; candidates do not establish ownership or state',
                evidence_formats=dict(sorted(formats.items())),
                documents_with_account_resource_mentions=[
                    dict(source_id=source, resource_mentions=sorted(set(re.findall(r'\baccount_\d+\b', text))))
                    for source, text in sorted(store.documents.items())
                    if re.search(r'\baccount_\d+\b', text)],
                raw_and_parsed_account_observations=len(candidates),
                missing_account_cases=len(details),
                cases_with_raw_account_candidate=sum(bool(d['raw_account_candidates']) for d in details),
                cases_with_identity_bearing_activity=sum(bool(d['identity_bearing_activities']) for d in details),
                cases=details)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', required=True, type=Path)
    parser.add_argument('--results', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    report = diagnose(Store(args.dataset).ingest(), json.loads(args.results.read_text()))
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'cases'}))


if __name__ == '__main__':
    main()
