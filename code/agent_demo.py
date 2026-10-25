"""Live synthetic-only tool-agent demonstration; no challenge excerpts are sent."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from audit.gemini import GeminiClient
from audit.investigator import investigate
from audit.model import Fact


def demo(client):
    at = '2026-01-01T00:00:00Z'
    request = dict(case_id='synthetic_live_demo', email='demo@example.test', audit_at=at)
    facts = [Fact('synthetic_source_A', 'row:1', 'security_service', 'demo_record',
                  'primary', 'SECURITY_AUDIT_LOG', 'PRESENT', at, at,
                  {'user_id': 'synthetic_user', 'email': request['email'],
                   'notice': 'Retention expiry is not supplied.'}),
             Fact('synthetic_source_B', 'row:2', 'security_service', 'demo_record',
                  'replica', 'SECURITY_AUDIT_LOG', 'PRESENT', at, at,
                  {'user_id': 'synthetic_user', 'retained': True})]
    store = SimpleNamespace(facts=facts, identities=[{'user_id': 'synthetic_user'}])
    result = dict(case_id=request['case_id'], ledger=[{'system': 'security_service', 'resource': 'demo_record'}],
                  unresolved=['Compare all physical copies of the returned resource; determine whether any supplies explicit retention expiry.'])
    report = investigate(store, request, result, [request['email'], 'synthetic_user'], client, max_tools=4)
    report['data_classification'] = 'Locally authored synthetic demo; no challenge evidence or secrets'
    report['proof_gap_preserved'] = result['unresolved'] == report['original_unresolved']
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--model', required=True)
    p.add_argument('--output', default='runs/tool-agent-live.json'); a = p.parse_args()
    report = demo(GeminiClient(a.model, max_calls=5, retries=0, max_input_bytes=24000, max_output_tokens=1024))
    out = Path(a.output); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ('success', 'stop_reason', 'tool_calls', 'usage', 'proof_gap_preserved')}))
    raise SystemExit(0 if report['success'] and report['tool_calls'] and report['proof_gap_preserved'] else 2)
