"""Harness 2.0: one-command, re-runnable evaluation of the deletion auditor.

  cd code && ../.venv/bin/python evaluation/harness2.py --dataset ../dataset [--label NAME]

Sections
  1. samples   - engine on the 32 labeled samples; metrics reused from evaluation/main.py
                 plus ordering accuracy and failures grouped by root-cause signature.
  2. fixtures  - the 30 independent edge-case fixtures (frozen expected.json); built from
                 runs/edge-author into runs/agents/qa/fixtures if no frozen copy exists.
  3. full      - invariant checks on the full 518-case run (fresh run by default, or an
                 existing run directory via --full-run-dir).

Writes runs/agents/qa/scorecard-<label>.json/.md, updates scorecard-latest.json and diffs
against the previous scorecard-latest.json (or --compare FILE).
The engine is always run as a subprocess (`code/main.py --no-llm`) so a broken
engine is reported as a failure instead of crashing the harness.
"""
import argparse, csv, hashlib, importlib.util, json, subprocess, sys, time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

CODE = Path(__file__).resolve().parents[1]
ROOT = CODE.parent
PY = ROOT / '.venv/bin/python'
OUT = ROOT / 'runs/agents/qa'
EDGE_AUTHOR = ROOT / 'runs/edge-author'
FROZEN_FIXTURES = ROOT.parent / 'ghost-audit-edge-cases'
REFERENCE_FULL_RUN = ROOT / 'runs/20261025T114601727402Z'

OPERATIONS = [
    ('FINDING', 'REPORT_REMAINING_RECORD', 'PRESENT'), ('FINDING', 'REPORT_EXPOSED_PII', 'PRESENT'),
    ('FINDING', 'REPORT_ACTIVE_DATA_FLOW', 'ACTIVE'), ('FINDING', 'REPORT_RESTORE_RISK', 'ACTIVE'),
    ('REMEDIATION', 'DISABLE_DATA_FLOW', 'DISABLED'), ('REMEDIATION', 'BLOCK_RESTORE', 'BLOCKED'),
    ('REMEDIATION', 'DELETE_RECORD', 'ABSENT'), ('REMEDIATION', 'REDACT_RECORD', 'REDACTED'),
    ('REMEDIATION', 'ANONYMIZE_RECORD', 'ANONYMIZED'), ('VERIFICATION', 'VERIFY_RECORD_ABSENT', 'ABSENT'),
    ('VERIFICATION', 'VERIFY_RECORD_PRESENT', 'PRESENT'), ('VERIFICATION', 'VERIFY_RECORD_REDACTED', 'REDACTED'),
    ('VERIFICATION', 'VERIFY_RECORD_ANONYMIZED', 'ANONYMIZED'), ('VERIFICATION', 'VERIFY_DATA_FLOW_DISABLED', 'DISABLED'),
    ('VERIFICATION', 'VERIFY_RESTORE_BLOCKED', 'BLOCKED')]
OP_INDEX = {op: i for i, (_, op, _) in enumerate(OPERATIONS)}
OP_PHASE = {op: p for p, op, _ in OPERATIONS}
OP_STATE = {op: s for _, op, s in OPERATIONS}
PHASE_ORDER = {'FINDING': 0, 'REMEDIATION': 1, 'VERIFICATION': 2}
STEP_KEYS = {'step_no', 'phase', 'system_id', 'resource_id', 'operation', 'state', 'evidence_id'}
STATUSES = {'COMPLETE', 'INCOMPLETE', 'NOT_APPLICABLE'}


def read_csv(path):
    with open(path, newline='') as f:
        return list(csv.DictReader(f))


def load_eval_metrics():
    """Import metrics() from evaluation/main.py without shadowing code/main.py."""
    sys.path.insert(0, str(CODE))
    spec = importlib.util.spec_from_file_location('ghost_eval_main', CODE / 'evaluation/main.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.metrics


# Runs main.run with a model-assisted review client built by main.model_client under an
# explicit call budget, then saves the client's provider-reported usage. The API key is
# resolved inside the client (env / .env) and is never read or printed by the harness.
LLM_RUNNER = """
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import main
dataset, requests, out, spec, calls = sys.argv[2], sys.argv[3], Path(sys.argv[4]), sys.argv[5], int(sys.argv[6])
client = main.model_client(spec, max_calls=calls, retries=0, max_output_tokens=2048, max_input_bytes=24000)
try:
    main.run(dataset, requests, out / 'output.csv', True, True, out, gemini_client=client)
finally:
    (out / 'llm_usage.json').write_text(json.dumps({'model': spec, 'max_calls': calls, 'usage': client.usage}, indent=2))
"""


def run_engine(dataset, out_dir, requests=None, timeout=1800, llm=None, llm_calls=3):
    """Run the engine in a subprocess (offline unless llm='openai:<model>').

    Returns (results list or None, summary, returncode, seconds)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in ('results.json', 'summary.json', 'output.csv', 'llm_usage.json'):
        (out_dir / stale).unlink(missing_ok=True)
    if llm:
        cmd = [str(PY), '-c', LLM_RUNNER, str(CODE), str(dataset),
               str(requests or Path(dataset) / 'deletion_requests.csv'), str(out_dir), llm, str(llm_calls)]
    else:
        cmd = [str(PY), str(CODE / 'main.py'), '--dataset', str(dataset), '--output', str(out_dir / 'output.csv'),
               '--run-dir', str(out_dir), '--no-llm']
        if requests:
            cmd += ['--requests', str(requests)]
    t = time.monotonic()
    p = subprocess.run(cmd, cwd=CODE, capture_output=True, text=True, timeout=timeout)
    (out_dir / 'cli.txt').write_text(p.stdout + p.stderr)
    try:
        results = json.loads((out_dir / 'results.json').read_text())
        summary = json.loads((out_dir / 'summary.json').read_text())
    except (OSError, ValueError):
        results, summary = None, {}
    return results, summary, p.returncode, time.monotonic() - t


def canonical_key(s):
    return (PHASE_ORDER.get(s.get('phase'), 9), OP_INDEX.get(s.get('operation'), 99), s.get('system_id', ''), s.get('resource_id', ''))


def is_canonical_order(steps):
    return [canonical_key(s) for s in steps] == sorted(canonical_key(s) for s in steps) and \
        [s.get('step_no') for s in steps] == list(range(1, len(steps) + 1))


def sig(s):
    return f"{s['operation']} {s['system_id']}"


def diff_signatures(pred_status, pred, label_status, label):
    """Root-cause signatures for one case (independent of resource IDs so cases group)."""
    out = []
    if pred_status != label_status:
        out.append(f'status {label_status} -> {pred_status}')
    k = lambda s: (s['phase'], s['system_id'], s['resource_id'], s['operation'])
    pa, pb = {k(s): s for s in pred}, {k(s): s for s in label}
    for key in pb.keys() - pa.keys():
        ev = 'cited' if pb[key]['evidence_id'] else 'empty-evidence'
        out.append(f'missing {sig(pb[key])} ({ev})')
    for key in pa.keys() - pb.keys():
        out.append(f'extra {sig(pa[key])}')
    for key in pa.keys() & pb.keys():
        a, b = pa[key], pb[key]
        if a['evidence_id'] != b['evidence_id']:
            kind = 'should be empty' if not b['evidence_id'] else 'missing citation' if not a['evidence_id'] else 'different file'
            out.append(f'evidence_id {sig(a)}: {kind}')
        for f in ('state',):
            if a[f] != b[f]:
                out.append(f'{f} {sig(a)}')
    if not out and pred != label:
        out.append('ordering/step_no only')
    return sorted(set(out))


# ---------------------------------------------------------------- 1. samples
def eval_samples(dataset, work, llm=None, llm_calls=3, subdir='samples'):
    labels = read_csv(dataset / 'sample_output.csv')
    results, summary, rc, secs = run_engine(dataset, work / subdir, dataset / 'sample_deletion_requests.csv',
                                            llm=llm, llm_calls=llm_calls)
    usage_path = work / subdir / 'llm_usage.json'
    usage = json.loads(usage_path.read_text()) if usage_path.exists() else None
    if results is None:
        return {'error': f'engine failed (exit {rc}); see {work/subdir/"cli.txt"}', 'llm': usage}
    metrics = load_eval_metrics()(results, labels)
    pred = {r['case_id']: r for r in results}
    ordering_ok = sum(is_canonical_order(pred[l['case_id']]['steps']) for l in labels)
    same_set = same_order = 0
    groups = defaultdict(list)
    per_case = {}
    for l in labels:
        p = pred[l['case_id']]
        lab = json.loads(l['steps_json'])
        k = lambda s: json.dumps(s, sort_keys=True)
        if sorted(map(k, p['steps'])) == sorted(map(k, lab)):
            same_set += 1
            same_order += p['steps'] == lab
        sigs = diff_signatures(p['status'], p['steps'], l['deletion_status'], lab)
        per_case[l['case_id']] = {'status': p['status'], 'label': l['deletion_status'], 'exact': not sigs,
                                  'unresolved': len(p.get('unresolved') or []), 'signatures': sigs}
        for s in sigs:
            groups[s].append(l['case_id'])
    fa = metrics['field_accuracy']
    return {
        'cases': metrics['cases'], 'seconds': round(secs, 1),
        'status_accuracy': [metrics['status_correct'], metrics['cases']],
        'exact_plan': [metrics['exact_cases'], metrics['cases']],
        'step_precision': round(metrics['precision'], 4), 'step_recall': round(metrics['recall'], 4),
        'step_f1': round(metrics['f1'], 4), 'step_tp_fp_fn': [metrics['step_tp'], metrics['step_fp'], metrics['step_fn']],
        'field_accuracy': {f: [a, b, round(a / b, 4) if b else None] for f, (a, b) in fa.items()},
        'evidence_id_accuracy': metrics['evidence_accuracy'],
        'ordering_canonical': [ordering_ok, metrics['cases']],
        'ordering_match_given_same_step_set': [same_order, same_set],
        'verification_coverage': metrics['verification_coverage'],
        'false_complete': metrics['false_complete'], 'wrongful_deletion': metrics['wrongful_deletion'],
        'unresolved': metrics['unresolved'], 'confusion': metrics['confusion'],
        'failed_cases': metrics['failures'],
        'failure_groups': dict(sorted(((s, sorted(c)) for s, c in groups.items()), key=lambda x: (-len(x[1]), x[0]))),
        'per_case': per_case,
        'mode': f'model-assisted {llm} (max_calls={llm_calls})' if llm else 'offline (--no-llm)',
        'llm': usage, 'model_calls': summary.get('model_calls', 0),
    }


# ---------------------------------------------------------------- 2. fixtures
def fixture_root(work):
    """Prefer the frozen external copy; otherwise build from runs/edge-author builders."""
    if (FROZEN_FIXTURES / 'freeze.json').exists():
        return FROZEN_FIXTURES, 'frozen external copy'
    root = OUT / 'fixtures'
    if not (root / '30/expected.json').exists():
        sys.path.insert(0, str(EDGE_AUTHOR))
        import build_group1, build_group2, build_group3  # noqa: E402
        rules = read_csv(ROOT / 'dataset/deletion_rules.csv')
        for mod in (build_group1, build_group2, build_group3):
            mod.build(root, rules)
    return root, 'built from runs/edge-author'


def check_frozen(root):
    f = root / 'freeze.json'
    if not f.exists():
        return None
    bad = [n for n, d in json.loads(f.read_text())['files'].items()
           if not (root / n).exists() or hashlib.sha256((root / n).read_bytes()).hexdigest() != d]
    return bad


def eval_fixture(root, case, work):
    exp = json.loads((root / case / 'expected.json').read_text())
    out = work / 'fixtures' / case
    results, summary, rc, secs = run_engine(root / case / 'dataset', out, timeout=300)
    errors = []
    actual = results[0] if results else None
    if actual is None:
        errors.append(f'engine produced no results (exit {rc})')
    else:
        if actual['status'] != exp['status']:
            errors.append(f"status {exp['status']} -> {actual['status']}")
        if actual['steps'] != exp['steps']:
            errors.extend('plan: ' + s for s in diff_signatures(actual['status'], actual['steps'], actual['status'], exp['steps']))
        if bool(summary.get('official_output_written')) != exp['ready']:
            errors.append(f"release ready={exp['ready']} -> {bool(summary.get('official_output_written'))}")
        for reason in exp['unresolved_contains']:
            if not any(reason.casefold() in x.casefold() for x in actual['unresolved']):
                errors.append('missing unresolved reason: ' + reason)
        if exp['ready'] and actual['unresolved']:
            errors.append('unexpected unresolved: ' + '; '.join(actual['unresolved'])[:300])
        for fb in exp['forbidden']:
            if any(all(s.get(k) == v for k, v in fb.items()) for s in actual['steps']):
                errors.append('forbidden action ' + json.dumps(fb, sort_keys=True))
    return {'case': case, 'pass': not errors, 'expected_status': exp['status'],
            'actual_status': actual and actual['status'], 'errors': errors, 'seconds': round(secs, 1)}


def eval_fixtures(work):
    root, source = fixture_root(work)
    tampered = check_frozen(root)
    cases = sorted(p.name for p in root.iterdir() if (p / 'expected.json').exists())
    reports = [eval_fixture(root, c, work) for c in cases]
    groups = defaultdict(list)
    for r in reports:
        for e in r['errors']:
            groups[e].append(r['case'])
    return {'source': f'{source}: {root}', 'freeze_violations': tampered,
            'passed': [sum(r['pass'] for r in reports), len(reports)],
            'failed_cases': [r['case'] for r in reports if not r['pass']],
            'failure_groups': dict(sorted(groups.items(), key=lambda x: (-len(x[1]), x[0]))),
            'cases': reports}


# ---------------------------------------------------------------- 3. full-run invariants
def check_case(case_id, status, steps, evidence_ids):
    v = []
    if status not in STATUSES:
        return [f'invalid status {status!r}']
    if not isinstance(steps, list):
        return ['steps not a list']
    for i, s in enumerate(steps, 1):
        if not isinstance(s, dict) or set(s) != STEP_KEYS:
            v.append('schema: step keys ' + (str(sorted(set(s) ^ STEP_KEYS)) if isinstance(s, dict) else 'not object'))
            continue
        if s['step_no'] != i:
            v.append('step numbering')
        op = s['operation']
        if op not in OP_INDEX:
            v.append(f'schema: unknown operation {op}')
            continue
        if s['phase'] != OP_PHASE[op]:
            v.append(f'schema: phase {s["phase"]} for {op}')
        if s['state'] != OP_STATE[op]:
            v.append(f'schema: state {s["state"]} for {op}')
        if not all(isinstance(s[k], str) for k in ('system_id', 'resource_id', 'evidence_id')) or not s['system_id'] or not s['resource_id']:
            v.append('schema: empty/non-string id field')
        ev = s['evidence_id']
        if status == 'COMPLETE':
            if s['phase'] != 'VERIFICATION':
                v.append(f'COMPLETE has {s["phase"]} step')
            if not ev:
                v.append('COMPLETE verification without evidence')
        if status == 'INCOMPLETE':
            if s['phase'] in ('REMEDIATION', 'VERIFICATION') and ev:
                v.append(f'INCOMPLETE {s["phase"]} cites evidence')
            if s['phase'] == 'FINDING' and not ev:
                v.append('INCOMPLETE finding without evidence')
        if ev and ev not in evidence_ids:
            v.append('evidence_id not in evidence_files/system_activity/user_audit_log')
    good = [s for s in steps if isinstance(s, dict) and set(s) == STEP_KEYS]
    if len(good) == len(steps) and [canonical_key(s) for s in good] != sorted(canonical_key(s) for s in good):
        v.append('phase/operation/system/resource order')
    keys = [(s['phase'], s['system_id'], s['resource_id'], s['operation']) for s in good]
    if len(keys) != len(set(keys)):
        v.append('duplicate step')
    if status == 'NOT_APPLICABLE' and steps != []:
        v.append('NOT_APPLICABLE with steps')
    if status == 'INCOMPLETE':
        phases = {s['phase'] for s in good}
        if not {'FINDING', 'REMEDIATION'} <= phases:
            v.append('INCOMPLETE without finding+remediation')
    if status == 'COMPLETE' and not steps:
        v.append('COMPLETE with no verification steps')
    return v


def eval_full(dataset, work, run_dir=None):
    if run_dir:
        rd, source = Path(run_dir), f'existing run {run_dir}'
        secs = None
    else:
        rd, source = work / 'full', 'fresh run of current code'
        results, summary, rc, secs = run_engine(dataset, rd, timeout=3600)
        if results is None:
            return {'error': f'full engine run failed (exit {rc}); see {rd/"cli.txt"}', 'source': source}
    requests = [r['case_id'] for r in read_csv(dataset / 'deletion_requests.csv')]
    evidence_ids = {r['file_id'] for r in read_csv(dataset / 'evidence_files.csv')} | \
        {r['activity_id'] for r in read_csv(dataset / 'system_activity.csv')} | \
        {r['audit_id'] for r in read_csv(dataset / 'user_audit_log.csv')}
    draft_path = rd / 'draft.csv'
    draft = read_csv(draft_path) if draft_path.exists() else []
    results = json.loads((rd / 'results.json').read_text()) if (rd / 'results.json').exists() else []
    by_case = {r['case_id']: r for r in results}
    file_v = []
    ids = [r['case_id'] for r in draft]
    if ids != sorted(ids):
        file_v.append('draft rows not sorted by case_id')
    if len(ids) != len(set(ids)):
        file_v.append('duplicate draft rows')
    missing_rows = sorted(set(requests) - set(ids), key=lambda c: int(c.split('_')[-1]) if c.split('_')[-1].isdigit() else 0)
    unknown_rows = sorted(set(ids) - set(requests))
    groups = defaultdict(list)
    for row in draft:
        try:
            steps = json.loads(row['steps_json'])
        except ValueError:
            groups['steps_json not valid JSON'].append(row['case_id'])
            continue
        for viol in sorted(set(check_case(row['case_id'], row['deletion_status'], steps, evidence_ids))):
            groups[viol].append(row['case_id'])
        r = by_case.get(row['case_id'])
        if r is not None and (r['status'] != row['deletion_status'] or r['steps'] != steps):
            groups['draft row differs from results.json'].append(row['case_id'])
    violating = {c for cs in groups.values() for c in cs}
    unresolved_cases = [c for c, r in by_case.items() if r.get('unresolved')]
    return {
        'source': f'{source}: {rd}', 'seconds': secs and round(secs, 1),
        'requests': len(requests), 'results': len(results), 'draft_rows': len(draft),
        'missing_rows': [len(missing_rows), missing_rows], 'unknown_rows': unknown_rows,
        'statuses': dict(Counter(r['deletion_status'] for r in draft)),
        'unresolved_cases': len(unresolved_cases),
        'unresolved_with_draft_row': len([c for c in unresolved_cases if c in set(ids)]),
        'file_violations': file_v,
        'cases_with_violations': [len(violating), len(draft)],
        'violation_groups': {k: [len(v), sorted(v)[:25]] for k, v in sorted(groups.items(), key=lambda x: -len(x[1]))},
    }


# ---------------------------------------------------------------- scorecard / diff
def headline(sc):
    h = {}
    s = sc.get('samples', {})
    if 'error' not in s and s:
        for k in ('status_accuracy', 'exact_plan', 'evidence_id_accuracy', 'ordering_canonical', 'verification_coverage'):
            h['samples.' + k] = s[k][0]
        for k in ('step_precision', 'step_recall', 'step_f1', 'false_complete', 'wrongful_deletion', 'unresolved'):
            h['samples.' + k] = s[k]
        for f, (a, b, _) in s['field_accuracy'].items():
            h['samples.field.' + f] = f'{a}/{b}'
    m = sc.get('samples_llm', {})
    if m and 'error' not in m:
        h['samples_llm.status_accuracy'] = m['status_accuracy'][0]
        h['samples_llm.exact_plan'] = m['exact_plan'][0]
        h['samples_llm.step_f1'] = m['step_f1']
        h['samples_llm.total_tokens'] = ((m.get('llm') or {}).get('usage') or {}).get('total_tokens')
    f = sc.get('fixtures', {})
    if f:
        h['fixtures.passed'] = f['passed'][0]
    u = sc.get('full', {})
    if 'error' not in u and u:
        h['full.draft_rows'] = u['draft_rows']
        h['full.missing_rows'] = u['missing_rows'][0]
        h['full.unresolved_cases'] = u['unresolved_cases']
        h['full.cases_with_violations'] = u['cases_with_violations'][0]
        for k, st in u['statuses'].items():
            h['full.status.' + k] = st
    return h


def diff(prev, cur):
    hp, hc = headline(prev), headline(cur)
    changes = {k: [hp.get(k), hc.get(k)] for k in sorted(hp.keys() | hc.keys()) if hp.get(k) != hc.get(k)}
    sp, sc_ = prev.get('samples', {}).get('per_case', {}), cur.get('samples', {}).get('per_case', {})
    fixed = sorted(c for c in sc_ if c in sp and not sp[c]['exact'] and sc_[c]['exact'])
    broken = sorted(c for c in sc_ if c in sp and sp[c]['exact'] and not sc_[c]['exact'])
    status_changes = {c: [sp[c]['status'], sc_[c]['status']] for c in sc_ if c in sp and sp[c]['status'] != sc_[c]['status']}
    fp = {r['case']: r['pass'] for r in prev.get('fixtures', {}).get('cases', [])}
    fc = {r['case']: r['pass'] for r in cur.get('fixtures', {}).get('cases', [])}
    vp = {k: v[0] for k, v in prev.get('full', {}).get('violation_groups', {}).items()}
    vc = {k: v[0] for k, v in cur.get('full', {}).get('violation_groups', {}).items()}
    return {'previous_label': prev.get('label'), 'metric_changes': changes,
            'samples_newly_exact': fixed, 'samples_newly_broken': broken, 'sample_status_changes': status_changes,
            'fixtures_newly_passing': sorted(c for c in fc if fc[c] and fp.get(c) is False),
            'fixtures_newly_failing': sorted(c for c in fc if not fc[c] and fp.get(c) is True),
            'invariant_group_changes': {k: [vp.get(k, 0), vc.get(k, 0)] for k in sorted(vp.keys() | vc.keys()) if vp.get(k, 0) != vc.get(k, 0)}}


def frac(x):
    return f'{x[0]}/{x[1]}'


def markdown(sc):
    L = [f"# Harness 2.0 scorecard — {sc['label']}", '', f"Generated {sc['generated_at']}. Command: `{sc['command']}`", '']
    s = sc.get('samples', {})
    L += ['## 1. Labeled samples (32)', '']
    if 'error' in s:
        L.append('ERROR: ' + s['error'])
    elif s:
        L += ['| Metric | Value |', '|---|---:|']
        for k in ('status_accuracy', 'exact_plan', 'evidence_id_accuracy', 'ordering_canonical',
                  'ordering_match_given_same_step_set', 'verification_coverage'):
            L.append(f'| {k} | {frac(s[k])} |')
        for k in ('step_precision', 'step_recall', 'step_f1', 'false_complete', 'wrongful_deletion', 'unresolved'):
            L.append(f'| {k} | {s[k]} |')
        L.append(f"| step TP/FP/FN | {'/'.join(map(str, s['step_tp_fp_fn']))} |")
        L += ['', '| Field | Correct/compared | Acc |', '|---|---:|---:|']
        L += [f'| {f} | {a}/{b} | {r} |' for f, (a, b, r) in s['field_accuracy'].items()]
        L += ['', 'Confusion (truth -> predicted): ' + ', '.join(f'{k}: {v}' for k, v in sorted(s['confusion'].items())), '',
              '### Sample failures grouped by root-cause signature', '', '| Signature | # | Cases |', '|---|---:|---|']
        L += [f'| {g} | {len(c)} | {", ".join(c)} |' for g, c in s['failure_groups'].items()]
    m = sc.get('samples_llm')
    if m:
        L += ['', f"## 1b. Labeled samples, {m.get('mode', 'model-assisted')}", '']
        if 'error' in m:
            L.append('ERROR: ' + m['error'])
        else:
            L += [f"Status {frac(m['status_accuracy'])}, exact {frac(m['exact_plan'])}, P/R/F1 {m['step_precision']}/{m['step_recall']}/{m['step_f1']}, "
                  f"evidence {frac(m['evidence_id_accuracy'])}, false-COMPLETE {m['false_complete']}, wrongful deletion {m['wrongful_deletion']}, unresolved {m['unresolved']}."]
        L.append(f"Provider usage (provider-reported): `{json.dumps((m.get('llm') or {}).get('usage'))}`")
    f = sc.get('fixtures', {})
    if f:
        L += ['', f"## 2. Edge-case fixtures: {frac(f['passed'])} pass", '', f"Source: {f['source']}. Freeze violations: {f['freeze_violations']}", '',
              '| Case | Expected | Actual | Result |', '|---|---|---|---|']
        L += [f"| {r['case']} | {r['expected_status']} | {r['actual_status']} | {'PASS' if r['pass'] else '; '.join(r['errors'])} |" for r in f['cases']]
        L += ['', '### Fixture failures grouped', '', '| Error | Cases |', '|---|---|']
        L += [f'| {e} | {", ".join(c)} |' for e, c in f['failure_groups'].items()]
    u = sc.get('full', {})
    L += ['', '## 3. Full 518 invariants', '']
    if 'error' in u:
        L.append('ERROR: ' + u['error'])
    elif u:
        L += [f"Source: {u['source']}", '',
              f"Requests {u['requests']}, results {u['results']}, draft rows {u['draft_rows']}, missing rows {u['missing_rows'][0]} (each scores zero), "
              f"unresolved cases {u['unresolved_cases']} ({u['unresolved_with_draft_row']} still have a provisional row). Statuses: {u['statuses']}. "
              f"File-level violations: {u['file_violations'] or 'none'}. Cases with invariant violations: {frac(u['cases_with_violations'])}.", '',
              '| Violation | Cases | Examples |', '|---|---:|---|']
        L += [f'| {k} | {n} | {", ".join(ex[:8])} |' for k, (n, ex) in u['violation_groups'].items()]
        if u['missing_rows'][0]:
            L += ['', 'Missing rows: ' + ', '.join(u['missing_rows'][1])]
    d = sc.get('diff')
    L += ['', '## Diff vs previous scorecard', '']
    if not d:
        L.append('No previous scorecard (this is the baseline).')
    else:
        L += [f"Previous: {d['previous_label']}", '', '| Metric | Before | After |', '|---|---:|---:|']
        L += [f'| {k} | {a} | {b} |' for k, (a, b) in d['metric_changes'].items()] or ['| (no headline changes) | | |']
        for k in ('samples_newly_exact', 'samples_newly_broken', 'fixtures_newly_passing', 'fixtures_newly_failing'):
            L.append(f'- {k}: {", ".join(d[k]) or "none"}')
        L.append(f"- sample_status_changes: {d['sample_status_changes'] or 'none'}")
        L.append(f"- invariant_group_changes: {d['invariant_group_changes'] or 'none'}")
    return '\n'.join(L) + '\n'


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--dataset', default='../dataset')
    p.add_argument('--label', default=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    p.add_argument('--compare', help='scorecard JSON to diff against (default: previous scorecard-latest.json)')
    p.add_argument('--full-run-dir', help='check an existing run dir (draft.csv + results.json) instead of running all 518')
    p.add_argument('--reference-full-run', action='store_true', help=f'shorthand for --full-run-dir {REFERENCE_FULL_RUN}')
    p.add_argument('--skip', default='', help='comma list of sections to skip: samples,fixtures,full')
    p.add_argument('--out', default=str(OUT))
    p.add_argument('--llm', help='optional extra sample run with the model-assisted path, e.g. openai:gpt-5.4-mini (default: offline only)')
    p.add_argument('--llm-calls', type=int, default=3, help='provider call budget for --llm (default 3)')
    a = p.parse_args(argv)
    if a.llm and a.llm_calls < 3:
        # gemini_review.review_cases reviews up to 3 cases and only catches GeminiError, so a
        # smaller budget raises OpenAIError and aborts the run (reported bug, not owned by QA).
        p.error('--llm-calls must be >= 3 (gemini_review reviews up to 3 cases)')
    dataset = Path(a.dataset).resolve()
    out = Path(a.out)
    work = out / 'work' / a.label
    work.mkdir(parents=True, exist_ok=True)
    skip = set(filter(None, a.skip.split(',')))
    sc = {'label': a.label, 'generated_at': datetime.now(timezone.utc).isoformat(),
          'command': 'cd code && ../.venv/bin/python evaluation/harness2.py ' + ' '.join(argv if argv is not None else sys.argv[1:]),
          'dataset': str(dataset)}
    if 'samples' not in skip:
        print('[harness2] samples...', flush=True)
        sc['samples'] = eval_samples(dataset, work)
        if a.llm:
            print(f'[harness2] samples with {a.llm} (max_calls={a.llm_calls})...', flush=True)
            sc['samples_llm'] = eval_samples(dataset, work, a.llm, a.llm_calls, 'samples-llm')
    if 'fixtures' not in skip:
        print('[harness2] fixtures...', flush=True)
        sc['fixtures'] = eval_fixtures(work)
    if 'full' not in skip:
        print('[harness2] full 518 invariants...', flush=True)
        sc['full'] = eval_full(dataset, work, a.full_run_dir or (REFERENCE_FULL_RUN if a.reference_full_run else None))
    latest = out / 'scorecard-latest.json'
    prev_path = Path(a.compare) if a.compare else latest if latest.exists() else None
    if prev_path and prev_path.exists():
        sc['diff'] = diff(json.loads(prev_path.read_text()), sc)
    (out / f'scorecard-{a.label}.json').write_text(json.dumps(sc, indent=2))
    (out / f'scorecard-{a.label}.md').write_text(markdown(sc))
    latest.write_text(json.dumps(sc, indent=2))
    print(json.dumps(headline(sc), indent=2))
    if sc.get('diff'):
        print(json.dumps({k: v for k, v in sc['diff'].items() if v}, indent=2))
    print(f"[harness2] wrote {out / f'scorecard-{a.label}.md'}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
