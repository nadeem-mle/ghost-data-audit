import pytest
from types import SimpleNamespace
from audit.gemini import GeminiError
from gemini_review import review_cases
from test_core import REQ,fact,store

class Fake:
    model='synthetic-model'
    usage={'attempted_calls':0}
    def __init__(self,answer):self.answer=answer
    def generate_json(self,prompt):
        self.usage['attempted_calls']+=1
        assert 'deletion_status' not in prompt
        return self.answer

def setup():
    s=store([fact('security_service','sec','SECURITY_AUDIT_LOG','PRESENT')])
    r={'case_id':REQ['case_id'],'unresolved':['missing retention period'],'ledger':[{'system':'security_service','resource':'sec'}]}
    return s,[r]

def test_advisory_cannot_silently_clear_proof_gap():
    s,rs=setup();c=Fake(dict(supported_observations=[],missing_proof=['No expiry is present'],next_read_only_actions=['Inspect supplied retention register']))
    r=review_cases(s,rs,[REQ],c)
    assert r['reviews'][0]['success'] and rs[0]['unresolved']==['missing retention period']

def test_hallucinated_source_is_rejected():
    s,rs=setup();c=Fake(dict(supported_observations=[dict(source_id='invented',location='x',resource_id='sec',exact_quote='2030')],missing_proof=[],next_read_only_actions=[]))
    r=review_cases(s,rs,[REQ],c)
    assert not r['reviews'][0]['success'] and not r['reviews'][0]['validated_observations']

def test_quote_must_match_same_evidence_unit():
    s,rs=setup();c=Fake(dict(supported_observations=[dict(source_id='source_A',location='row:1',resource_id='sec',exact_quote='retention_until:2030')],missing_proof=[],next_read_only_actions=[]))
    assert not review_cases(s,rs,[REQ],c)['reviews'][0]['success']

def test_known_quote_passes_but_is_still_advisory():
    s,rs=setup();c=Fake(dict(supported_observations=[dict(source_id='source_A',location='row:1',resource_id='sec',exact_quote='user_x',explanation='Stable subject')],missing_proof=['Expiry absent'],next_read_only_actions=[]))
    r=review_cases(s,rs,[REQ],c)
    assert r['reviews'][0]['success'] and len(r['reviews'][0]['validated_observations'])==1 and rs[0]['unresolved']
