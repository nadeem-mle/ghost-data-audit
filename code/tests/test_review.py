"""Review regressions: black-box CLI, white-box branches and behavior boundaries."""
import csv,json,subprocess,sys
from pathlib import Path
import pytest
from audit.ingest import Store,infer_state
from audit.engine import intent,Unresolved
from test_ingestion import bare,M
from test_cli import dataset,write
from main import run

@pytest.mark.parametrize('category,key',[('DATA_FLOW','enabled'),('BACKUP_ARCHIVE','restore_allowed')])
@pytest.mark.parametrize('value',[None,'unknown','null','',2,'disabled-ish'])
def test_unknown_control_never_becomes_compliant(category,key,value):
    with pytest.raises(ValueError):infer_state(category,{key:value})

@pytest.mark.parametrize('text',[
    'I do not want to delete my account; please correct my email.',
    'Please never delete my account; send a data export.',
    'No quiero borrar mi cuenta. Corrige mi correo.',
    "Please don't erase my account. I need a copy.",
])
def test_negated_authorization(text):assert intent(text)=='NO'

def test_mixed_deletion_export():assert intent('Please export my records and then delete my account.')=='YES'
def test_conditional_not_authorized_automatically():
    with pytest.raises(Unresolved):intent('Delete my account only if the refund has completed.')

def test_multi_page_content_preserved():
    s=bare();s.document(M,'FIRST PAGE CONTEXT','page:1');s.document(M,'SECOND PAGE CONTEXT','page:2')
    assert 'FIRST PAGE CONTEXT' in s.documents[M['file_id']] and 'SECOND PAGE CONTEXT' in s.documents[M['file_id']]

def test_partial_parse_rolls_back_failed_file(tmp_path):
    d=dataset(tmp_path)
    good=dict(record_type='USER_PROFILE',system='account_service',resource_id='account',result='FOUND',subject_reference='u')
    bad=dict(record_type='DATA_FLOW',system='integration_service',resource_id='job',enabled=None,subject_reference='u')
    (d/'evidence/record.json').write_text(json.dumps({'records':[good,bad]}))
    s=Store(d,cache=tmp_path/'cache').ingest()
    assert s.coverage[0]['status']=='error' and s.facts==[] and s.inventories==[]

def test_case_path_traversal_rejected(tmp_path):
    d=dataset(tmp_path)
    req=list(csv.DictReader((d/'deletion_requests.csv').open()));req[0]['case_id']='../escaped'
    write(d/'deletion_requests.csv',list(req[0]),req)
    with pytest.raises(ValueError,match='case_id'):run(d,d/'deletion_requests.csv',tmp_path/'output.csv',run_dir=tmp_path/'run')
    assert not (tmp_path/'escaped.json').exists()

def test_output_cannot_overwrite_input(tmp_path):
    d=dataset(tmp_path);source=d/'deletion_requests.csv';before=source.read_bytes()
    with pytest.raises(ValueError,match='output'):run(d,source,source,run_dir=tmp_path/'run')
    assert source.read_bytes()==before

def test_black_box_success_then_safety_failure(tmp_path):
    d=dataset(tmp_path);code=Path(__file__).parents[1];output=tmp_path/'result.csv'
    command=[sys.executable,str(code/'main.py'),'--dataset',str(d),'--output',str(output),'--run-dir',str(tmp_path/'run'),'--no-llm']
    first=subprocess.run(command,capture_output=True,text=True,cwd=tmp_path,timeout=30)
    assert first.returncode==0,first.stderr
    validate=subprocess.run([sys.executable,str(code/'validate_output.py'),'--dataset',str(d),'--output',str(output)],capture_output=True,text=True,timeout=30)
    assert validate.returncode==0
    (d/'evidence/record.json').write_text('{malformed')
    second=subprocess.run(command,capture_output=True,text=True,cwd=tmp_path,timeout=30)
    assert second.returncode==2 and not output.exists()

@pytest.mark.parametrize('event',['profile_lookup_completed','audit_record_read_completed'])
def test_missing_row_count_is_not_state_proof(event):
    s=bare()
    with pytest.raises(ValueError,match='row-count'):
        s.log_file(M,f'2026-09-01T10:00:00Z service=account_service event={event} resource_id=a')

def test_packager_rejects_changed_inference_input(tmp_path,monkeypatch):
    import package_submission as pack
    from audit.provenance import fingerprint
    d=dataset(tmp_path);rd=tmp_path/'measured';rd.mkdir()
    (rd/'fingerprint.json').write_text(json.dumps(fingerprint(d)))
    (rd/'summary.json').write_text(json.dumps({'official_output_written':False}))
    (d/'evidence/record.json').write_text('{}')
    monkeypatch.setattr(pack,'ROOT',tmp_path)
    with pytest.raises(ValueError,match='stale inference'):pack.package(rd)

@pytest.mark.parametrize('text',[
    'Please delete my account and remove me from marketing lists only.',
    'Send a portable format export, and erase my account.',
])
def test_authorized_account_deletion_survives_mixed_task(text):assert intent(text)=='YES'

@pytest.mark.parametrize('text',[
    "I don't want my account deleted; I need access.",
    'I am not requesting account deletion. Please export my records.',
])
def test_postposed_negation(text):assert intent(text)=='NO'
