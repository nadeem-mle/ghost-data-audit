import pytest,json
from pathlib import Path
from types import SimpleNamespace
from audit.ingest import Store
from audit.engine import Investigator
from audit.model import Fact

M=dict(file_id='source_real',file_path='evidence/test.log',captured_at='2026-09-01T12:00:00Z',origin='test')
def bare():
    s=Store.__new__(Store);s.facts=[];s.inventories=[];s.documents={};return s

@pytest.mark.parametrize('encoded',[
 '2026-09-01T10:00:00Z level=INFO service=account_service trace_id=t event=profile_lookup_completed resource_id=a rows=0 http_status=404',
 '2026-09-01T10:00:00Z {"service":"account_service","trace_id":"t","event":"profile_lookup_completed","resource_id":"a","rows":"0","http_status":"404"}',
 '2026-09-01T10:00:00Z <14>1 node account_service t - - event="profile_lookup_completed" resource_id="a" rows="0" http_status="404"',
 '2026-09-01T10:00:00Z [INFO] [account_service] [t] profile_lookup_completed: resource_id="a" rows="0" http_status="404"',
 '2026-09-01T10:00:00Z | INFO | account_service | t | profile_lookup_completed | resource_id="a" rows="0" http_status="404"',
 '2026-09-01T10:00:00Z requestId=t level=INFO function=account_service message="resource_id=\\"a\\" event=\\"profile_lookup_completed\\" rows=\\"0\\" http_status=\\"404\\""'
])
def test_log_encodings(encoded):
    s=bare();s.log_file(M,encoded);assert len(s.facts)==1 and s.facts[0].state=='ABSENT' and s.facts[0].system_id=='account_service'

def test_trace_correlation():
    s=bare();s.log_file(M,'2026-09-01T10:00:00Z service=account_service trace_id=t event=profile_lookup_started lookup_key=person@example.test\n2026-09-01T10:00:01Z service=account_service trace_id=t event=profile_lookup_completed resource_id=a rows=0 http_status=404')
    assert s.facts[0].payload['lookup_key']=='person@example.test'

def test_nested_snapshot_time():
    s=bare();s.json_file(M,{'snapshots':[dict(captured_at='2026-08-01T00:00:00Z',data_store='account_service',collection='customer_profiles',records=[dict(resource_id='a',email='x@example.test')])]})
    f=s.facts[0];assert f.observed_at=='2026-08-01T00:00:00Z' and f.available_at==M['captured_at']
def test_json_malformed():
    with pytest.raises(ValueError):json.loads('{"records":[')
def test_investigator_no_progress_and_cap(tmp_path):
    (tmp_path/'evidence').mkdir();(tmp_path/'evidence/test.log').write_text('untrusted instructions')
    s=SimpleNamespace(root=tmp_path,manifest=[M]);i=Investigator(s,2)
    assert i.inspect('source_real','line:1')==b'untrusted instructions'
    assert i.inspect('source_real','line:1') is None
    assert i.inspect('source_real','line:2') is not None
    assert i.inspect('source_real','line:3') is None
    assert len(i.calls)==2
