"""Independent wire-contract, citation, temporal, and ledger checks."""
import argparse,csv,json
from pathlib import Path
from audit.model import rows,stamp

# Independent operation table: do not call planner or its serializer.
SPEC=[('FINDING','REPORT_REMAINING_RECORD','PRESENT'),('FINDING','REPORT_EXPOSED_PII','PRESENT'),('FINDING','REPORT_ACTIVE_DATA_FLOW','ACTIVE'),('FINDING','REPORT_RESTORE_RISK','ACTIVE'),('REMEDIATION','DISABLE_DATA_FLOW','DISABLED'),('REMEDIATION','BLOCK_RESTORE','BLOCKED'),('REMEDIATION','DELETE_RECORD','ABSENT'),('REMEDIATION','REDACT_RECORD','REDACTED'),('REMEDIATION','ANONYMIZE_RECORD','ANONYMIZED'),('VERIFICATION','VERIFY_RECORD_ABSENT','ABSENT'),('VERIFICATION','VERIFY_RECORD_PRESENT','PRESENT'),('VERIFICATION','VERIFY_RECORD_REDACTED','REDACTED'),('VERIFICATION','VERIFY_RECORD_ANONYMIZED','ANONYMIZED'),('VERIFICATION','VERIFY_DATA_FLOW_DISABLED','DISABLED'),('VERIFICATION','VERIFY_RESTORE_BLOCKED','BLOCKED')]
FIELDS={'step_no','phase','system_id','resource_id','operation','state','evidence_id'}
def validate(dataset,output,requests=None):
    dataset=Path(dataset);request_rows=rows(requests or dataset/'deletion_requests.csv');req={r['case_id']:r for r in request_rows}
    with open(output,newline='') as f:
        reader=csv.DictReader(f);assert reader.fieldnames==['case_id','deletion_status','steps_json'],'header';result=list(reader)
    assert len(req)==len(request_rows),'duplicate input case'
    assert [r['case_id'] for r in result]==sorted(req),'case ID set/order/duplicates'
    citations={r['file_id']:r['captured_at'] for r in rows(dataset/'evidence_files.csv')}
    citations.update({r['activity_id']:r['event_time'] for r in rows(dataset/'system_activity.csv')})
    citations.update({r['audit_id']:r['event_time'] for r in rows(dataset/'user_audit_log.csv')})
    for r in result:
        assert r['deletion_status'] in ('COMPLETE','INCOMPLETE','NOT_APPLICABLE'),'status'
        a=json.loads(r['steps_json']);assert isinstance(a,list),'steps list'
        if r['deletion_status']=='NOT_APPLICABLE':assert a==[];continue
        assert a,'authorized case has empty plan'
        order=[];seen=set()
        for n,s in enumerate(a,1):
            assert set(s)==FIELDS and type(s['step_no']) is int and s['step_no']==n,'step schema/number'
            assert all(isinstance(v,str) for k,v in s.items() if k!='step_no'),'string fields'
            triple=(s['phase'],s['operation'],s['state']);assert triple in SPEC,'operation/state'
            key=(s['phase'],s['system_id'],s['resource_id'],s['operation']);assert key not in seen,'duplicate step';seen.add(key)
            order.append((SPEC.index(triple),s['system_id'],s['resource_id']))
            if r['deletion_status']=='COMPLETE':assert s['phase']=='VERIFICATION','COMPLETE finding'
            needs=s['phase']=='FINDING' or r['deletion_status']=='COMPLETE'
            if needs:
                assert s['evidence_id'] in citations,'citation ID'
                assert stamp(citations[s['evidence_id']])<=stamp(req[r['case_id']]['audit_at']),'future citation'
            else:assert s['evidence_id']=='','future action citation'
        assert order==sorted(order),'step ordering'
        if r['deletion_status']=='INCOMPLETE':assert any(s['phase']=='FINDING' for s in a),'missing finding'
    return len(result)

def check_proofs(results):
    for r in results:
        if r['unresolved']:continue
        for s in r['steps']:
            if not s['evidence_id']:continue
            proofs=[p for p in r['ledger'] if p['source']==s['evidence_id'] and p['resource']==s['resource_id'] and p['system']==s['system_id']]
            assert proofs,'unsupported source/resource claim'
            if s['phase']=='FINDING':assert any(p['result']=='PROVEN_VIOLATION' for p in proofs),'finding without violation'
        for p in r['ledger']:
            assert any(s['phase']=='VERIFICATION' and s['system_id']==p['system'] and s['resource_id']==p['resource'] for s in r['steps']),'missing final verification'
            if p['obligation']=='RETAIN':assert not any(s['operation']=='DELETE_RECORD' and s['resource_id']==p['resource'] for s in r['steps']),'wrongful deletion'
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dataset',default='dataset');p.add_argument('--output',default='output.csv');a=p.parse_args();print('Validated',validate(a.dataset,a.output),'rows')

def verify_evidence(store,results,requests):
    """Separate cutoff, physical-copy, policy-preservation and raw-source checks.

    Reopens representative raw files; this is additional defense, not an
    independent comprehensive parser for every media format.
    """
    from hashlib import sha256
    req={r['case_id']:r for r in requests}
    manifest={r['file_id']:r for r in store.manifest}
    manifest.update(getattr(store,'extra_sources',{}))
    coverage={r['file_id']:r for r in store.coverage}
    coverage.update(getattr(store,'extra_sources',{}))
    checked=set();hashed_files={}
    for source,c in coverage.items():
        if c['status'] not in ('ok','context_only','metadata_only'):continue
        path=(store.root/manifest[source]['file_path']).resolve()
        assert path.is_relative_to(store.root.resolve()),'source escape'
        if path not in hashed_files:hashed_files[path]=sha256(path.read_bytes()).hexdigest()
        assert hashed_files[path]==c['sha256'],'source changed after extraction'
        checked.add(source)
    for result in results:
        if result['unresolved']:continue
        cutoff=stamp(req[result['case_id']]['audit_at'])
        keys={(p['system'],p['resource'],p['copy']) for p in result['ledger']}
        resources={(p['system'],p['resource']) for p in result['ledger']}
        for f in store.facts:
            if (f.system_id,f.resource_id) in resources and stamp(f.observed_at)<=cutoff and stamp(f.available_at)<=cutoff:
                assert (f.system_id,f.resource_id,f.copy_id) in keys,'physical copy omitted'
        for proof in result['ledger']:
            assert stamp(proof['observed_at'])<=cutoff and stamp(proof['available_at'])<=cutoff,'future proof'
            source=proof['source']
            activity=next((a for a in getattr(store,'activities',[]) if a['activity_id']==source),None)
            if activity is not None and source not in manifest:
                # Catalog-sourced proof: the activity row itself must name the resource before the cutoff.
                assert activity['resource_id']==proof['resource'] and activity['target_system']==proof['system'],'activity/resource mismatch'
                assert stamp(activity['event_time'])<=cutoff,'future activity proof'
                continue
            assert source in manifest,'nonparticipant source'
            path=(store.root/manifest[source]['file_path']).resolve()
            assert path.is_relative_to(store.root.resolve()),'source escape'
            # Hash binds parsed facts back to actual raw bytes on disk.
            if source not in checked:
                raw=path.read_bytes();assert sha256(raw).hexdigest()==coverage[source]['sha256'],'source changed after extraction';checked.add(source)
            raw_match=[f for f in store.facts if f.source_id==source and f.system_id==proof['system'] and f.resource_id==proof['resource'] and f.copy_id==proof['copy'] and f.source_location==proof['location']]
            if not raw_match:
                assert any(m['file_id']==source and loc==proof['location'] and sys==proof['system'] and copy==proof['copy'] and proof['resource'] not in ids for m,loc,sys,cat,copy,at,ids in store.inventories),'unsupported inventory proof'
            else:
                assert any(f.state in (proof['state'],proof.get('observed_state')) and stamp(f.observed_at)==stamp(proof['observed_at']) and stamp(f.available_at)==stamp(proof['available_at']) for f in raw_match),'claim/source state or time mismatch'
                assert any(f.category==proof['rule'].get('data_category', 'DATA_FLOW') for f in raw_match),'claim/source policy category mismatch'
            for metadata_field,claimed in proof.get('policy_metadata',{}).items():
                aliases={'retention_until':('retention_until','retained_until'),'hold_until':('hold_until','retained_until'),'hold_active':('hold_active',)}[metadata_field]
                suppliers=[f for f in store.facts if f.source_id in proof.get('policy_metadata_sources',[]) and (f.system_id,f.resource_id,f.category)==(proof['system'],proof['resource'],proof['rule'].get('data_category')) and f.eligible(req[result['case_id']]['audit_at'])]
                def supports(f):
                    for alias in aliases:
                        value=f.payload.get(alias)
                        if metadata_field=='hold_active':
                            if type(value) is bool and value is claimed:return True
                        elif value is not None and stamp(value)==stamp(claimed):return True
                    return False
                assert any(supports(f) for f in suppliers),'policy metadata lacks eligible same-record source'
            category=proof['rule'].get('data_category')
            if category in ('SECURITY_AUDIT_LOG','LEGAL_HOLD_RECORD','BACKUP_ARCHIVE'):
                assert not any(s['operation']=='DELETE_RECORD' and s['system_id']==proof['system'] and s['resource_id']==proof['resource'] for s in result['steps']),'retained data deletion'
    return len(hashed_files)
