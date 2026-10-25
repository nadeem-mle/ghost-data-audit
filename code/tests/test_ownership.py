from audit.ownership import Candidate, log_candidates, structured_candidates

MANIFEST = {'file_id': 'evidence_test', 'captured_at': '2026-01-03T00:00:00Z'}


def test_raw_diagnostic_keeps_records_isolated_and_does_not_infer_from_nulls():
    obj = {'account_service': {'profile_lookups': [
        {'resource_id': 'opaque-A', 'profile': None, 'status_code': 404},
        {'resource_id': 'opaque-B', 'profile': {'unrecognized_selector': 'alice@example.org'}}]}}
    candidates = list(structured_candidates(obj, MANIFEST))
    assert [c.resource_id for c in candidates if c.matches({'alice@example.org'}, MANIFEST['captured_at'])] == ['opaque-B']


def test_trace_link_does_not_cross_services_or_file_boundaries():
    text = '\n'.join([
        '2026-01-01T00:00:00Z service=search_service trace_id=shared event=start lookup_key=alice@example.org',
        '2026-01-01T00:00:01Z service=account_service trace_id=shared event=start resource_id=opaque-A',
        '2026-01-01T00:00:02Z service=account_service trace_id=own event=start lookup_key=bob@example.org',
        '2026-01-01T00:00:03Z service=account_service trace_id=own event=unrecognized resource_id=opaque-B',
    ])
    candidates = list(log_candidates(text, MANIFEST))
    assert not any(c.matches({'alice@example.org'}, MANIFEST['captured_at']) for c in candidates)
    assert [c.resource_id for c in candidates if c.matches({'bob@example.org'}, MANIFEST['captured_at'])] == ['opaque-B']
    new_file = '2026-01-01T00:00:04Z service=account_service trace_id=own resource_id=opaque-C'
    assert not any(c.matches({'bob@example.org'}, MANIFEST['captured_at']) for c in log_candidates(new_file, MANIFEST))


def test_candidate_cutoff_requires_both_observation_and_availability():
    c = Candidate('evidence_test', '$', 'opaque-A', '2026-01-01T00:00:00Z',
                  '2026-01-03T00:00:00Z', frozenset({'alice@example.org'}))
    assert not c.matches({'alice@example.org'}, '2026-01-02T00:00:00Z')
    assert c.matches({'alice@example.org'}, '2026-01-03T00:00:00Z')
