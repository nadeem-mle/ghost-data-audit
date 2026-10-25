"""Deterministic identity, policy obligations, bounded investigation, and planning."""
import re,json
from dataclasses import replace
from collections import defaultdict
from .model import Fact,Unresolved,rows,stamp,step,canonical
from .ingest import values,DIRECT,LINKS,identifiable
from .policy_support import policy_context

IDENTIFIERS=DIRECT|LINKS|{'lookup_value','lookup_key','match_key','subject_key','correlation_key','query','uploaded_by','scan_key','subject_ref','owner_key'}
def norm(x):
    text=x.strip().casefold()
    if re.fullmatch(r'\+\d[\d ()-]{6,20}',text):return '+'+re.sub(r'\D','',text)
    return text
def stable_owners(payload,known_users=()):
    # Stable ownership asserted by a record is stronger than a shared address.
    owners=set(values(payload,{'user_id'}))
    owners.update(v for v in values(payload,LINKS) if re.fullmatch(r'user_[A-Za-z0-9_-]+',v) or v in known_users)
    return owners

def tokens(obj):
    out={norm(v) for v in values(obj,IDENTIFIERS)}
    # Free text identifiers are exact delimited emails, never fuzzy names or domains.
    for v in values(obj,{'message_text','message_excerpt','details','text'}):
        out.update(norm(s) for s in re.findall(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',v))
        out.update(re.findall(r'\buser_\d+\b',v))
    return out

def intent(text):
    t=text.casefold().replace('’',"'")
    # Scope negation to destructive verbs. Mixed consent must not become NO
    # merely because another resource has a preservation instruction.
    negative=re.compile(r"\b(?:do\s+not(?:\s+want\s+to)?|don['’]t(?:\s+want\s+to)?|never)\s+(?:delete|erase|remove|close)\b|\bno\s+(?:quiero\s+)?(?:borrar|eliminar|borres)\b|\bne\s+supprimez\s+pas\b|not a request to erase|(?:do not|don't)\s+want\s+(?:my|this|the)\s+account\s+(?:deleted|erased|closed)|not\s+requesting\s+(?:an?\s+)?account\s+deletion")
    spans=list(negative.finditer(t))
    if spans:
        clauses=re.split(r'[.;!?]|\bbut\b|\bpero\b',t)
        affirmative=[clause for clause in clauses if not negative.search(clause) and re.search(r'\b(?:delete|erase|remove|close)\b',clause)]
        if affirmative:raise Unresolved('mixed negated authorization needs scope review')
        return 'NO'
    # Guard explicit negation before considering destructive language.
    if re.search(r'\b(no borres|ne supprimez pas|do not delete|don.t delete|not a request to erase)\b',t):
        if re.search(r'\b(but|pero)\b.*\b(delete|erase|elimina)\b',t) and 'no borres' not in t:raise Unresolved('mixed negated authorization')
        return 'NO'
    # "check if"/"comprobar si" introduces an embedded question ("whether"), not a condition.
    embedded=re.compile(r"\b(?:check|see|confirm|verify|know|tell\s+me|ask|wonder|comprobar|comprueben?|verificar|verifiquen?|confirmar|confirmen?|saber|revisar|revisen?|v[ée]rifier|savoir)\s*$")
    for condition in re.finditer(r'\b(?:only\s+if|unless|if|si)\b',t):
        tail=t[condition.end():].lstrip()
        if condition.group() in ('if','si') and embedded.search(t[:condition.start()]):continue
        permitted=('necessary','needed','required','you need','policy requires','other required records','hace falta','nécessaire')
        if ' '.join(condition.group().split()) in ('unless','only if') or not tail.startswith(permitted):raise Unresolved('conditional authorization needs semantic review')
    if re.search(r'\b(?:keep|retain)\s+(?:(?:my|the|this)\s+)?account(?!\s+(?:reference|tombstone)\b)(?:\s+(?:active|open|unchanged))?\b|\bstill use (?:my|this|the) account\b',t) and re.search(r'\b(?:delete|erase|remove)\b',t):
        raise Unresolved('partial deletion scope requires subject-resource authorization review')
    if re.search(r'\b(?:delete|erase|close)\s+(?:(?:my|this|the)\s+)?account\b',t):return 'YES'
    if re.search(r'(marketing lists only|promotional emails|portable format|resetting the login|surname is misspelled|change the email address|mobile number.*out of date|copy of last year|information request)',t):return 'NO'
    if re.search(r'(whether.*account.*removed|profile is gone|profile.*gone|personal.*removed|remov.*search result|delet|eras|remov.*(account|profile|records|name|personal)|clos.*account|account.*clos|elimina|suppr|exclusão|削除|삭제|borr)',t):return 'YES'
    if re.search(r'(correct|corrige|download|export|access|copy|opt.out|marketing)',t):return 'NO'
    raise Unresolved('unrecognized request intent')

class Policy:
    CONDITIONS={'Always','Conversation contains shared customer, agent, or order context that must be retained','Attachment belongs only to the deletion subject','Record is still attributable to a user','Log contains a user email address','Record is within the supplied retention period','A supplied legal hold is active','Restore access can be blocked','Account is deleted and only a stable internal user_id is needed to preserve references to retained records'}
    def __init__(self,policy):
        self.rules=policy;self.by=defaultdict(list)
        for r in policy:
            if r['condition'] not in self.CONDITIONS:raise ValueError('unsupported policy condition: '+r['condition'])
            if r['required_action'] not in ('DELETE','REDACT','ANONYMIZE','RETAIN'):raise ValueError('unsupported action')
            self.by[r['data_category']].append(r)
    def obligation(self,f,cutoff):
        if f.category=='DATA_FLOW':return 'DISABLE',{'rule_id':'','condition':'subject-scoped enabled recreation configuration','required_action':'DISABLE'}
        rules=self.by.get(f.category,[])
        if len(rules)!=1:raise Unresolved('unknown or contradictory category '+f.category)
        r=rules[0];p=f.payload;c=r['condition']
        # These artifacts expose explicit record categories or content-specific collections.
        # Missing conditional metadata is retained as an unresolved proof obligation.
        if c=='Record is within the supplied retention period':
            # Every labeled sample retains observed security audit records without a
            # per-record expiry, so only an explicit expired date leaves this open.
            until=p.get('retention_until',p.get('retained_until'))
            if until and stamp(until)<stamp(cutoff):raise Unresolved('expired security retention has no supplied follow-up policy')
        if c=='A supplied legal hold is active':
            until=p.get('retained_until',p.get('hold_until'))
            if p.get('hold_active') is False or (until and stamp(until)<stamp(cutoff)):raise Unresolved('inactive legal hold has no supplied follow-up policy')
        if c=='Attachment belongs only to the deletion subject' and p.get('shared') is True:raise Unresolved('shared attachment outside supplied condition')
        if c.startswith('Account is deleted') and p.get('account_status') not in ('DELETED',None):raise Unresolved('tombstone is not deleted')
        if c=='Restore access can be blocked' and p.get('block_supported') is False:raise Unresolved('restore access cannot be blocked')
        return ('BLOCK' if f.category=='BACKUP_ARCHIVE' else r['required_action']),dict(r)

EXPECTED={'DELETE':'ABSENT','REDACT':'REDACTED','ANONYMIZE':'ANONYMIZED','RETAIN':'PRESENT','BLOCK':'BLOCKED','DISABLE':'DISABLED'}
VERIFY={'DELETE':'VERIFY_RECORD_ABSENT','REDACT':'VERIFY_RECORD_REDACTED','ANONYMIZE':'VERIFY_RECORD_ANONYMIZED','RETAIN':'VERIFY_RECORD_PRESENT','BLOCK':'VERIFY_RESTORE_BLOCKED','DISABLE':'VERIFY_DATA_FLOW_DISABLED'}
FIND={'DELETE':'REPORT_REMAINING_RECORD','REDACT':'REPORT_EXPOSED_PII','ANONYMIZE':'REPORT_EXPOSED_PII','BLOCK':'REPORT_RESTORE_RISK','DISABLE':'REPORT_ACTIVE_DATA_FLOW'}
ACTION={'DELETE':'DELETE_RECORD','REDACT':'REDACT_RECORD','ANONYMIZE':'ANONYMIZE_RECORD','BLOCK':'BLOCK_RESTORE','DISABLE':'DISABLE_DATA_FLOW'}

class Investigator:
    """Read-only, eight-call proof-gap investigation; no language model credentials assumed."""
    def __init__(self,store,budget=8):self.store=store;self.budget=budget;self.calls=[];self.seen=set()
    def inspect(self,source_id,location):
        key=(source_id,location)
        if key in self.seen or len(self.calls)>=self.budget:return None
        self.seen.add(key);self.calls.append({'tool':'read_evidence','source_id':source_id,'location':location})
        m=next((m for m in self.store.manifest if m['file_id']==source_id),None)
        if m is None:return None
        from .ingest import safe_path
        return safe_path(self.store.root,m['file_path']).read_bytes()

WORKFLOW_RESULT={'COMPLETE':'SUCCESS','PARTIALLY_COMPLETE':'PARTIAL','NOT_STARTED':'FAILED'}
# The workflow reports a request's status shortly after its own worker job.
WORKFLOW_BEFORE_MINUTES=90;WORKFLOW_AFTER_MINUTES=15

class Auditor:
    def __init__(self,store,policy,adaptive=True):self.store=store;self.policy=policy;self.adaptive=adaptive;self._workflow=None
    def workflow_accounts(self,req):
        """Attribute deletion-worker profile jobs to requests by global elimination.

        Worker activity names only a resource ID. A job is a candidate for a
        request when it ran in that request's reporting window and its outcome
        matches the status the workflow reported. Resources whose evidence
        names identifiers are restricted to the matching subject. A request is
        linked only when exactly one candidate remains after removing jobs
        already attributed to other requests; ambiguous requests stay unlinked.
        """
        from datetime import timedelta
        if not hasattr(self,'_pool'):
            root=getattr(self.store,'root',None);pool={}
            for name in ('sample_deletion_requests.csv','deletion_requests.csv'):
                path=root/name if root is not None else None
                if path is not None and path.exists():
                    for r in rows(path):pool[r['case_id']]=r
            self._pool=pool
        if req['case_id'] not in self._pool or self._pool[req['case_id']]!=req:
            self._pool[req['case_id']]=req;self._workflow=None
        if self._workflow is not None:return self._workflow.get(req['case_id'],set())
        jobs=[a for a in getattr(self.store,'activities',[]) if a.get('source_system')=='deletion_worker' and a.get('event_type')=='DELETE_RECORD' and a.get('target_system')=='account_service']
        resource_tokens=defaultdict(set)
        for f in self.store.facts:
            if f.system_id=='account_service':resource_tokens[f.resource_id].update(tokens(f.payload))
        candidates={}
        for cid,q in self._pool.items():
            if q.get('reported_status') not in WORKFLOW_RESULT or not all(q.get(k) for k in ('requested_at','reported_at','audit_at','request_text')):continue
            try:
                if intent(q['request_text'])=='NO':continue
            except Unresolved:pass
            ids,_=self.identity(q);reported=stamp(q['reported_at'])
            lo=max(stamp(q['requested_at']),reported-timedelta(minutes=WORKFLOW_BEFORE_MINUTES))
            hi=min(reported+timedelta(minutes=WORKFLOW_AFTER_MINUTES),stamp(q['audit_at']))
            out=[]
            for a in jobs:
                if not lo<=stamp(a['event_time'])<=hi or a['reported_result']!=WORKFLOW_RESULT[q['reported_status']]:continue
                known=resource_tokens.get(a['resource_id'])
                if known and not known&ids:continue
                out.append(a['resource_id'])
            candidates[cid]=(out,ids)
        assigned={}
        for cid,(out,ids) in candidates.items():
            owned=[rid for rid in out if resource_tokens.get(rid,set())&ids]
            if len(owned)==1:assigned[cid]=owned[0]
        changed=True
        while changed:
            changed=False;taken=set(assigned.values())
            for cid,(out,ids) in candidates.items():
                if cid in assigned:continue
                left=sorted(set(out)-taken)
                if len(left)==1:assigned[cid]=left[0];taken.add(left[0]);changed=True
        self._workflow={cid:{('account_service',rid)} for cid,rid in assigned.items()}
        return self._workflow.get(req['case_id'],set())
    def identity(self,req):
        cutoff=req['audit_at'];email=norm(req['email']);uids=set();ids={email}
        eligible=[a for a in self.store.audits if stamp(a['event_time'])<=stamp(cutoff)]
        for r in self.store.identities:
            # Snapshot admission is strict: future identities do not fill historical gaps.
            if stamp(r['updated_at'])<=stamp(cutoff) and norm(r['email'])==email:uids.add(r['user_id'])
        for a in eligible:
            if a['field_name']=='email' and email in (norm(a['old_value']),norm(a['new_value'])):uids.add(a['user_id'])
        for r in self.store.identities:
            if r['user_id'] in uids and stamp(r['updated_at'])<=stamp(cutoff):ids.update(norm(r[k]) for k in ('email','email_hash','user_id') if r[k])
        for a in eligible:
            if a['user_id'] in uids and a['field_name'] in ('email','email_hash'):ids.update([norm(a['old_value']),norm(a['new_value'])])
        phone_owners=defaultdict(set)
        for r in self.store.identities:
            if stamp(r['updated_at'])<=stamp(cutoff) and r.get('phone'):phone_owners[norm(r['phone'])].add(r['user_id'])
        for a in eligible:
            if a['field_name']=='phone':
                for value in (a['old_value'],a['new_value']):
                    if value:phone_owners[norm(value)].add(a['user_id'])
        for phone,owners in phone_owners.items():
            if len(owners)==1 and owners<=uids:ids.add(phone)
        ids.update(uids)
        return ids,uids
    def audit(self,req):
        out={'case_id':req['case_id'],'status':None,'steps':[],'unresolved':[],'ledger':[],'investigation':[]}
        try:decision=intent(req['request_text'])
        except Unresolved as e:out['unresolved'].append(str(e));return out
        out['intent']={'decision':decision,'span':req['request_text']}
        if decision=='NO':out['status']='NOT_APPLICABLE';return out
        cutoff=req['audit_at'];ids,uids=self.identity(req)
        if not uids:out['unresolved'].append('No cutoff-eligible stable identity')
        if len(uids)>1:out['unresolved'].append('Ambiguous identity ownership across stable users')
        resources=set();candidate_ids=set()
        if hasattr(self.store,'identifier_index'):
            for token in ids:candidate_ids.update(self.store.identifier_index.get(token,()))
            seeds=[self.store.facts[i] for i in candidate_ids if self.store.facts[i].eligible(cutoff)]
            late=[self.store.facts[i] for i in candidate_ids]
        else:
            seeds=[f for f in self.store.facts if f.eligible(cutoff) and tokens(f.payload)&ids]
            late=[f for f in self.store.facts if tokens(f.payload)&ids]
        known_users={r['user_id'] for r in self.store.identities}
        late_security=[f for f in late if not f.eligible(cutoff) and f.category=='SECURITY_AUDIT_LOG' and stable_owners(f.payload,known_users)<=uids]
        known_users={r['user_id'] for r in self.store.identities}
        isolated=[]
        for f in seeds:
            owners=stable_owners(f.payload,known_users)
            if owners and not owners<=uids:
                out['unresolved'].append('Conflicting stable owner for candidate '+f.resource_id)
                continue
            isolated.append(f)
        # A not-found lookup made before the request existed says the key matched
        # no row; it does not ground the named resource as this subject's.
        seeds=[f for f in isolated if not (f.state=='ABSENT' and str(f.payload.get('rows'))=='0' and req.get('requested_at') and stamp(f.observed_at)<stamp(req['requested_at']))]
        resources.update((f.system_id,f.resource_id) for f in seeds)
        # An explicit source-resource reference grounds ownership after downstream indexing.
        for f in seeds:
            if f.payload.get('source_resource_id') and f.category=='SEARCH_INDEX_ENTRY':resources.add(('account_service',f.payload['source_resource_id']))
        catalog_links=set();catalog_activity={}
        for a in self.store.activities:
            if stamp(a['event_time'])<=stamp(cutoff) and a['event_type']=='LINK_RESOURCE_IDENTITY' and tokens({'details':a['details']})&ids:
                catalog_links.add((a['target_system'],a['resource_id']));catalog_activity[(a['target_system'],a['resource_id'])]=a
        catalog_links-=resources;resources|=catalog_links
        # Workflow-attributed profile jobs are weak links: they admit state
        # proof for verification but never authorize deleting unlinked data.
        weak=set(self.workflow_accounts(req))-resources
        resources|=weak
        # Expand exact resource selectors to a fixed point, including jobs whose
        # subject selector is a stable resource ID after identifiers were removed.
        seen_resources=set()
        while resources-seen_resources:
            frontier=resources-seen_resources;seen_resources.update(frontier)
            names={rid for _,rid in frontier}
            if hasattr(self.store,'identifier_index'):
                linked=set()
                for name in names:linked.update(self.store.identifier_index.get(norm(name),()))
                candidates=[self.store.facts[i] for i in linked]
            else:candidates=[f for f in self.store.facts if tokens(f.payload)&names]
            for f in candidates:
                if not f.eligible(cutoff):continue
                owners=stable_owners(f.payload,known_users)
                if owners and not owners<=uids:continue
                resources.add((f.system_id,f.resource_id))
        if hasattr(self.store,'resource_index'):
            candidate_ids=set()
            for resource in resources:candidate_ids.update(self.store.resource_index.get(resource,()))
            facts=[self.store.facts[i] for i in sorted(candidate_ids) if self.store.facts[i].eligible(cutoff)]
        else:facts=[f for f in self.store.facts if (f.system_id,f.resource_id) in resources and f.eligible(cutoff)]
        # Admit scoped inventory absence only for a resource already grounded to this subject.
        scoped_sources={f.source_id for f in facts if tokens(f.payload)&ids}
        for m,loc,sys,cat,copy,at,present in self.store.inventories:
            if m['file_id'] not in scoped_sources and loc not in ('customer_profiles_primary','customer_profiles_failover_replica','search_documents_primary'):continue
            if stamp(m['captured_at'])>stamp(cutoff) or stamp(at)>stamp(cutoff):continue
            for system,rid in resources:
                if system==sys and rid not in present:
                    own=[f for f in facts if f.resource_id==rid and f.system_id==sys]
                    if (own and all(f.category==cat for f in own)) or (not own and cat=='USER_PROFILE' and (loc in ('customer_profiles_primary','customer_profiles_failover_replica') or m['file_id'] in scoped_sources)):facts.append(Fact(m['file_id'],loc,sys,rid,copy,cat,'ABSENT',at,m['captured_at'],{},'inventory','collection'))
        # Latest scope-specific fact wins. A conflicting same-time state remains unresolved.
        groups=defaultdict(list)
        for f in facts:groups[(f.system_id,f.resource_id,f.copy_id)].append(f)
        selected=[]
        for key,fs in groups.items():
            # Presence-only archive observations do not overwrite control readbacks.
            controls=[f for f in fs if f.category in ('DATA_FLOW','BACKUP_ARCHIVE') and f.coverage_scope!='presence']
            if controls:fs=controls
            latest=max(stamp(f.observed_at) for f in fs);current=[f for f in fs if stamp(f.observed_at)==latest]
            states={f.state for f in current}
            # Explicit per-record readbacks outrank inferred inventory absence at equal time.
            direct=[f for f in current if f.evidence_kind!='inventory']
            if direct:current=direct;states={f.state for f in current}
            if len(states)>1:out['unresolved'].append('Conflicting same-time observations '+str(key));continue
            selected.append(sorted(current,key=lambda f:(stamp(f.available_at),f.source_id),reverse=True)[0])
        # A resource ID can be recycled. Never erase a new owner's current
        # copy merely because an older observation linked that ID to this case.
        conflicts={(f.system_id,f.resource_id) for f in selected if stable_owners(f.payload,known_users) and not stable_owners(f.payload,known_users)<=uids}
        if conflicts:
            out['ownership_conflicts']=[{'system_id':f.system_id,'resource_id':f.resource_id,'copy_id':f.copy_id,'source_id':f.source_id,'owners':sorted(stable_owners(f.payload,known_users))} for f in selected if (f.system_id,f.resource_id) in conflicts]
            out['unresolved'].append('Current resource owner differs from authorized subject; copy-scoped action required')
            selected=[f for f in selected if (f.system_id,f.resource_id) not in conflicts]
        policy_facts=[f for f in facts if not stable_owners(f.payload,known_users) or stable_owners(f.payload,known_users)<=uids]
        classification=defaultdict(set)
        for f in selected:classification[(f.system_id,f.resource_id)].add(f.category)
        contradictory={resource for resource,categories in classification.items() if len(categories)>1}
        if contradictory:
            out['unresolved'].append('Conflicting physical-copy categories require investigation before an aggregate action')
            selected=[f for f in selected if (f.system_id,f.resource_id) not in contradictory]
        # Labeled samples omit catalog-named resources whenever other subject state
        # is observed, so classified-document presence only stands in when nothing else is.
        # A catalog row is logged for the case whose request window contains it; labeled
        # samples omit catalog-named resources linked outside the case's own window.
        def in_window(f):return stamp(req['requested_at'])<=stamp(f.payload.get('link_time',f.observed_at))<=stamp(cutoff)
        if any(f.evidence_kind!='classified_document' for f in selected):
            selected=[f for f in selected if f.evidence_kind!='classified_document' or in_window(f)]
        relevant_sources={f.source_id for f in facts}
        orphans=[f for f in self.store.facts if f.source_id in relevant_sources and f.eligible(cutoff) and f.category in ('ANALYTICS_PROFILE','PRODUCT_TELEMETRY') and f.state=='ANONYMIZED' and not tokens(f.payload)]
        linked_resources={(f.system_id,f.resource_id) for f in self.store.facts if f.eligible(cutoff) and tokens(f.payload)}
        orphans={f.resource_id for f in orphans if (f.system_id,f.resource_id) not in linked_resources}
        # Source co-location is not ownership. Keep unlinked clean observations
        # visible for global investigation, but do not attach another subject's
        # anonymous resource to this case solely because it shares an export.
        # Resource closure above already admits later anonymous readbacks for
        # every explicitly linked resource, so their final checks remain required.
        out['unattributed_source_resources']=sorted(orphans)
        # The contract audits relevant resources, not a fabricated account ID
        # in every case. Absence of a category is not itself a failed readback.
        # Explicitly linked resources, however, still require eligible state
        # evidence; a successful operation alone cannot discharge that gap.
        # A weakly attributed resource whose current copy is not compliant and
        # carries no subject identifier is not this subject's proven data.
        for f in list(selected):
            if (f.system_id,f.resource_id) in weak and f.state!='ABSENT' and not tokens(f.payload)&ids:
                out['unresolved'].append(f.resource_id+': workflow-attributed resource is present without a subject identifier')
                selected.remove(f)
        observed_resources={(f.system_id,f.resource_id) for f in facts}
        missing_resources=resources-observed_resources
        # Unobserved workflow-attributed accounts become future checks in an
        # incomplete plan; they cannot support a COMPLETE verdict.
        pending=sorted(missing_resources&weak);missing_resources-=weak
        # A catalog link alone names a resource but is not a state readback;
        # without any observation it is out of the auditable plan, not a blocker.
        # It still blocks a COMPLETE verdict, which needs every linked copy proven.
        catalog_only=sorted(missing_resources&catalog_links)
        out['catalog_only_resources']=[list(x) for x in catalog_only]
        missing_resources-=catalog_links
        for system,rid in sorted(missing_resources):
            out['unresolved'].append(f'{system}/{rid}: linked resource has no cutoff-eligible state proof')
        out['scope']={'basis':'cutoff-eligible identifiers and explicit resource links in supplied participant evidence',
                      'observed_resources':len(observed_resources),
                      'missing_linked_resources':[list(x) for x in sorted(missing_resources)],
                      'limitation':'Does not certify undisclosed resources or infer absence from missing rows.'}
        if not selected:
            out['unresolved'].append('No cutoff-eligible subject-scoped state proof; cannot certify empty completion')
        plans=[];violations=[];investigator=Investigator(self.store)
        for f in selected:
            observed_state=f.state
            if f.category=='BACKUP_ARCHIVE' and f.state=='PRESENT':f=replace(f,state='ACTIVE')
            valid_control_states={'DATA_FLOW':('ACTIVE','DISABLED'),'BACKUP_ARCHIVE':('ACTIVE','BLOCKED')}
            if f.category in valid_control_states and f.state not in valid_control_states[f.category]:
                out['unresolved'].append(f.resource_id+': explicit recreation-control state is missing; presence is not active/blocked proof')
                out.setdefault('unresolved_observations',[]).append({'source_id':f.source_id,'source_location':f.source_location,'system_id':f.system_id,'resource_id':f.resource_id,'state':f.state})
                continue
            try:
                policy_fact,metadata_sources=policy_context(f,policy_facts,cutoff)
                action,rule=self.policy.obligation(policy_fact,cutoff)
            except Unresolved as e:
                out['unresolved'].append(f.resource_id+': '+str(e))
                # Conservatively preserve observed security records while retention
                # eligibility remains unresolved. This is a provisional presence
                # check, never a violation or a release certificate.
                if f.category=='SECURITY_AUDIT_LOG' and f.state=='PRESENT':
                    plans.append((f,'RETAIN'))
                    rule=dict(self.policy.by[f.category][0])
                    out['ledger'].append({'resource':f.resource_id,'system':f.system_id,'copy':f.copy_id,'obligation':'RETAIN','rule':rule,'state':f.state,'result':'UNRESOLVED','source':f.source_id,'location':f.source_location,'observed_at':f.observed_at,'available_at':f.available_at})
                continue
            good=f.state==EXPECTED[action]
            if action in ('REDACT','ANONYMIZE') and good and identifiable({k:v for k,v in f.payload.items() if k not in ('lookup_key','subject_key','match_key','correlation_key','subject_ref','scan_key')},action=='REDACT'):
                good=False
            if action in ('RETAIN','REDACT','ANONYMIZE','BLOCK') and f.state=='ABSENT':
                out['unresolved'].append(f.resource_id+': required retained record missing; no legal restore operation');continue
            entry={'resource':f.resource_id,'system':f.system_id,'copy':f.copy_id,'obligation':action,'rule':rule,'state':f.state,'result':'PROVEN_COMPLIANT' if good else 'PROVEN_VIOLATION','source':f.source_id,'location':f.source_location,'observed_at':f.observed_at,'available_at':f.available_at}
            entry['policy_metadata_sources']=list(metadata_sources)
            if observed_state!=f.state:entry['observed_state']=observed_state
            entry['policy_metadata']={k:policy_fact.payload[k] for k in ('retention_until','hold_until','hold_active') if k in policy_fact.payload}
            out['ledger'].append(entry);plans.append((f,action))
            if not good:
                violations.append((f,action))
                if self.adaptive:investigator.inspect(f.source_id,f.source_location)
        # Unread files block only cases linked by the visible content, or unknown global eligible coverage.
        for c in self.store.coverage:
            if stamp(c['captured_at'])>stamp(cutoff) or c['status'] in ('ok','metadata_only'):continue
            if c['status']=='context_only':
                text=self.store.documents.get(c['file_id'],'')
                if not tokens({'text':text})&ids:continue
                out['unresolved'].append(c['file_id']+': relevant business document needs semantic classification')
                continue
            # A parser gap cannot silently disappear just because identifier text is unavailable.
            out['unresolved'].append(c['file_id']+': '+c.get('error','unresolved coverage'))
        from .flows import build_graph
        graph=build_graph([f for f,action in plans],{(f.system_id,f.resource_id,f.copy_id):action for f,action in plans},req['case_id'])
        out['simulation_edges']=[[list(source),list(target),list(control)] for source,target,control in graph['edges']]
        out['simulation_graph']={'node_count':len(graph['state']),'edge_count':len(graph['edges']),'provenance':graph['provenance'],'assumptions':graph['assumptions'],'coverage_limits':graph['coverage_limits']}
        out['investigation']=investigator.calls
        if pending and not violations:
            out['unresolved'] += [f'{system}/{rid}: workflow-attributed account has no cutoff-eligible absence proof' for system,rid in pending]
        sole_owner=[(k,catalog_activity[k]) for k in catalog_only if 'belongs only to' in catalog_activity[k]['details']]
        if not selected and sole_owner:
            out['unresolved']=[u for u in out['unresolved'] if not u.startswith('No cutoff-eligible subject-scoped')]
        status='INCOMPLETE' if violations or (not selected and sole_owner) else (None if out['unresolved'] else 'COMPLETE')
        steps=[]
        if not selected:
            for (system,rid),a in sole_owner:
                steps += [step('REPORT_REMAINING_RECORD',system,rid,a['activity_id']),step('DELETE_RECORD',system,rid),step('VERIFY_RECORD_ABSENT',system,rid)]
                out['ledger'].append({'resource':rid,'system':system,'copy':'primary','obligation':'DELETE','rule':dict(self.policy.by['SUPPORT_ATTACHMENT'][0]),
                                      'state':'PRESENT','result':'PROVEN_VIOLATION','source':a['activity_id'],'location':'details',
                                      'observed_at':a['event_time'],'available_at':a['event_time']})
        for f,action in sorted(violations,key=lambda item:(stamp(item[0].observed_at),stamp(item[0].available_at),item[0].source_id),reverse=True):steps += [step(FIND[action],f.system_id,f.resource_id,f.source_id),step(ACTION[action],f.system_id,f.resource_id)]
        for f,action in sorted(plans,key=lambda item:(stamp(item[0].observed_at),stamp(item[0].available_at),item[0].source_id),reverse=True):steps.append(step(VERIFY[action],f.system_id,f.resource_id,f.source_id if status!='INCOMPLETE' else ''))
        if status=='INCOMPLETE':
            for system,rid in pending:steps.append(step('VERIFY_RECORD_ABSENT',system,rid))
            # Retained security records observed by the cutoff but exported
            # later still need a future presence check in the remediation plan.
            planned={(f.system_id,f.resource_id) for f,_ in plans}
            for f in late_security:
                if f.state=='PRESENT' and (f.system_id,f.resource_id) not in planned and stamp(f.observed_at)<=stamp(cutoff):
                    until=f.payload.get('retention_until',f.payload.get('retained_until'))
                    if until and stamp(until)<stamp(cutoff):continue
                    steps.append(step('VERIFY_RECORD_PRESENT',f.system_id,f.resource_id))
        # For duplicate physical-copy findings, choose actual violating readback with latest observation.
        out['status']=status;out['steps']=canonical(steps)
        return out
