import csv,json,subprocess,sys
from pathlib import Path
from main import run
from validate_output import validate

def write(path,columns,data):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=columns);w.writeheader();w.writerows(data)

def dataset(tmp_path):
    p=tmp_path/'dataset';p.mkdir();(p/'evidence').mkdir()
    write(p/'deletion_requests.csv',['case_id','email','requested_at','reported_status','reported_at','audit_at','request_text'],[dict(case_id='custom',email='user@example.test',requested_at='2026-01-01T00:00:00Z',reported_status='COMPLETE',reported_at='2026-01-02T00:00:00Z',audit_at='2026-01-03T00:00:00Z',request_text='Please delete my account')])
    write(p/'user_identities.csv',['user_id','name','email','phone','email_hash','updated_at'],[dict(user_id='u',name='Fictional',email='user@example.test',phone='',email_hash='',updated_at='2026-01-01T00:00:00Z')])
    write(p/'user_audit_log.csv',['audit_id','user_id','event_time','field_name','old_value','new_value'],[])
    write(p/'system_activity.csv',['activity_id','event_time','event_type','source_system','target_system','resource_id','reported_result','details'],[])
    write(p/'deletion_rules.csv',['rule_id','data_category','condition','required_action'],[dict(rule_id='delete',data_category='USER_PROFILE',condition='Always',required_action='DELETE')])
    write(p/'evidence_files.csv',['file_id','file_path','origin','captured_at'],[dict(file_id='real_source',file_path='evidence/record.json',origin='account_service',captured_at='2026-01-02T00:00:00Z')])
    (p/'evidence/record.json').write_text(json.dumps({'records':[dict(record_type='USER_PROFILE',recorded_at='2026-01-02T00:00:00Z',system='account_service',resource_id='account',result='NOT_FOUND',subject_reference='u')]}))
    return p

def test_end_to_end_written_and_reread(tmp_path):
    d=dataset(tmp_path);out=tmp_path/'output.csv'
    _,_,summary=run(d,d/'deletion_requests.csv',out,run_dir=tmp_path/'run')
    assert summary['official_output_written'] and validate(d,out)==1

def test_malformed_evidence_blocks_atomic_output(tmp_path):
    d=dataset(tmp_path);(d/'evidence/record.json').write_text('{bad json')
    out=tmp_path/'output.csv';_,_,summary=run(d,d/'deletion_requests.csv',out,run_dir=tmp_path/'run')
    assert summary['unresolved']==1 and not out.exists()

def test_bad_output_null_rejected(tmp_path):
    d=dataset(tmp_path);out=tmp_path/'output.csv';results,_,_=run(d,d/'deletion_requests.csv',out,run_dir=tmp_path/'run')
    steps=results[0]['steps'];steps[0]['evidence_id']=None
    write(out,['case_id','deletion_status','steps_json'],[dict(case_id='custom',deletion_status='COMPLETE',steps_json=json.dumps(steps))])
    import pytest
    with pytest.raises(AssertionError):validate(d,out)
