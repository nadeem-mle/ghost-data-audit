"""Participant evidence admission, immutable provenance, and source coverage."""
import json,re,shlex,subprocess,sqlite3
from pathlib import Path
from .model import Fact,rows,digest,stamp
from .safe_sql import snapshot

COLLECTIONS={
 'customer_profiles':('account_service','USER_PROFILE'), 'customer_search_documents':('search_service','SEARCH_INDEX_ENTRY'),
 'customer_analytics_reports':('analytics_platform','ANALYTICS_PROFILE'), 'support_conversations':('support_platform','SUPPORT_MESSAGE'),
 'ticket_attachments':('support_platform','SUPPORT_ATTACHMENT'),'customer_export_jobs':('export_service','USER_EXPORT'),
 'connector_configurations':('integration_service','DATA_FLOW'),'backup_catalog':('backup_service','BACKUP_ARCHIVE'),
 'security_audit_events':('security_service','SECURITY_AUDIT_LOG'),'retained_order_records':('legal_service','LEGAL_HOLD_RECORD'),
 'deleted_customer_references':('identity_service','ACCOUNT_TOMBSTONE'),
 'customer_profiles_primary':('account_service','USER_PROFILE'),'customer_profiles_failover_replica':('account_service','USER_PROFILE'),
 'search_documents_primary':('search_service','SEARCH_INDEX_ENTRY'), 'customer_analytics_profiles':('analytics_platform','ANALYTICS_PROFILE'), 'support_records':('support_platform','SUPPORT_MESSAGE'), 'customer_exports':('export_service','USER_EXPORT'), 'connector_subscriptions':('integration_service','DATA_FLOW'), 'backup_restore_entries':('backup_service','BACKUP_ARCHIVE'), 'security_audit_records':('security_service','SECURITY_AUDIT_LOG')}
SERVICES={'account_service':'USER_PROFILE','search_service':'SEARCH_INDEX_ENTRY','analytics_platform':'ANALYTICS_PROFILE','export_service':'USER_EXPORT','integration_service':'DATA_FLOW','backup_service':'BACKUP_ARCHIVE','security_service':'SECURITY_AUDIT_LOG','support_platform':'SUPPORT_MESSAGE','identity_service':'ACCOUNT_TOMBSTONE','marketing_platform':'MARKETING_PROFILE','email_delivery_service':'EMAIL_DELIVERY_LOG','cache_service':'CACHE_ENTRY'}
DIRECT={'name','full_name','display_name','email','phone','email_hash','requester_email','requester_phone','requester_name','customer_email','owner_email','owner_phone','matched_value'}
LINKS={'user_id','customer_reference','subject_reference','subject_selector'}

def values(obj,keys):
    if isinstance(obj,dict):
        for k,v in obj.items():
            if k in keys and isinstance(v,str) and v not in ('','no direct identifier'): yield v
            elif isinstance(v,(dict,list)):yield from values(v,keys)
    elif isinstance(obj,list):
        for v in obj:yield from values(v,keys)

def identifiable(obj,tombstone=False):
    if any(values(obj,DIRECT)):return True
    if not tombstone and any(values(obj,LINKS)):return True
    text=' '.join(values(obj,{'message_text','message_excerpt'}))
    return bool(re.search(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\+\d[\d ()-]{7,}',text))

def control_bool(value):
    if type(value) is bool:return value
    if type(value) is int and value in (0,1):return bool(value)
    if isinstance(value,str) and value.casefold() in ('true','false','1','0'):return value.casefold() in ('true','1')
    raise ValueError('unknown control value; explicit boolean required')

def row_presence(obj):
    value=obj.get('rows')
    if not re.fullmatch(r'\d+',str(value)):raise ValueError('missing explicit row-count readback')
    return 'PRESENT' if int(value)>0 else 'ABSENT'

def infer_state(cat,obj):
    if obj.get('result') in ('NOT_FOUND','ABSENT'):return 'ABSENT'
    if obj.get('result') in ('FOUND','IDENTIFIABLE','REDACTED','ANONYMIZED','ACTIVE','DISABLED','BLOCKED'):return {'FOUND':'PRESENT','IDENTIFIABLE':'IDENTIFIABLE'}.get(obj['result'],obj['result'])
    if cat=='DATA_FLOW':
        if 'enabled' not in obj:raise ValueError('missing enabled state')
        return 'ACTIVE' if control_bool(obj['enabled']) else 'DISABLED'
    if cat=='BACKUP_ARCHIVE':
        if 'restore_allowed' not in obj:raise ValueError('missing restore policy')
        return 'ACTIVE' if control_bool(obj['restore_allowed']) else 'BLOCKED'
    if cat=='USER_PROFILE' and (obj.get('status_code')==404 or obj.get('http_status')=='404'):return 'ABSENT'
    if cat in ('ANALYTICS_PROFILE','PRODUCT_TELEMETRY'):return 'IDENTIFIABLE' if identifiable(obj) else 'ANONYMIZED'
    if cat in ('SUPPORT_MESSAGE','EMAIL_DELIVERY_LOG','ACCOUNT_TOMBSTONE'):
        # Stable subject reference is permitted for shared records/tombstones.
        return 'IDENTIFIABLE' if identifiable(obj,True) else 'REDACTED'
    return 'PRESENT'

def labelled_utc_date(text,label):
    from datetime import datetime,timezone
    match=re.search(r'\b'+re.escape(label)+r'\s+(\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\s+\d{1,2})[\s:]+(\d{2})\s+UTC\b',text,re.I)
    if not match:return None
    normalized=' '.join((match[1]+' '+match[2]).split())
    return datetime.strptime(normalized,'%d %b %Y %H %M').replace(tzinfo=timezone.utc).isoformat().replace('+00:00','Z')

def safe_path(root,name):
    p=(root/name).resolve()
    if not p.is_relative_to(root.resolve()):raise ValueError('evidence path traversal')
    return p

class Store:
    def __init__(self,dataset,cache=Path('runs/cache'),media=True):
        self.root=Path(dataset);self.cache=Path(cache);self.cache.mkdir(parents=True,exist_ok=True)
        self.facts=[];self.coverage=[];self.inventories=[];self.documents={};self.metadata_documents=set();self.extra_sources={};self.media=media
        self.manifest=rows(self.root/'evidence_files.csv')
        self.identities=rows(self.root/'user_identities.csv');self.audits=rows(self.root/'user_audit_log.csv');self.activities=rows(self.root/'system_activity.csv')
        self.index=sqlite3.connect(':memory:');self.index.execute('create table facts (idx integer,resource text,source text,system text,observed text,available text,payload text)')
    def add(self,m,loc,system,rid,cat,obj,at=None,copy='primary',state=None,kind='readback',scope='record'):
        at=at or m['captured_at'];stamp(at);stamp(m['captured_at'])
        if not rid or not system or not cat:raise ValueError('incomplete fact identity')
        f=Fact(m['file_id'],loc,system,rid,copy,cat,state or infer_state(cat,obj),at,m['captured_at'],obj,kind,scope)
        self.facts.append(f)
    def ingest(self):
        for m in self.manifest:
            entry=dict(m,status='ok',facts=0);start=len(self.facts);inventory_start=len(self.inventories)
            try:
                p=safe_path(self.root,m['file_path']);entry['sha256']=digest(p)
                if p.suffix=='.json':self.json_file(m,json.loads(p.read_text()))
                elif p.suffix=='.sql':self.sql_file(m,p.read_text())
                elif p.suffix=='.log':self.log_file(m,p.read_text())
                elif p.suffix=='.txt':self.text_file(m,p.read_text())
                elif p.suffix=='.pdf':
                    import pymupdf as fitz
                    with fitz.open(p) as doc:
                        for i,page in enumerate(doc):
                            text=page.get_text(sort=True)
                            if len(text.strip())<30:
                                if not self.media:raise ValueError('visual evidence disabled')
                                pix=page.get_pixmap(matrix=fitz.Matrix(2,2));img=self.cache/(digest(p)+f'-{i}.png');pix.save(img);text=self.ocr(img)
                            self.document(m,text,f'page:{i+1}')
                elif p.suffix=='.png':
                    if not self.media:raise ValueError('visual evidence disabled')
                    self.document(m,self.ocr(p),'image')
                else:raise ValueError('unsupported evidence format')
                entry['facts']=len(self.facts)-start
                if not entry['facts'] and p.suffix not in ('.sql',):entry['status']='metadata_only' if m['file_id'] in self.metadata_documents else 'context_only';entry['error']='Provenance metadata, not a separate subject business record' if entry['status']=='metadata_only' else 'Business context retained; not an explicit state readback'
            except (ValueError,OSError,ImportError,RuntimeError,KeyError,TypeError,subprocess.TimeoutExpired) as e:
                del self.facts[start:];del self.inventories[inventory_start:]
                entry.update(status='error',error=f'{type(e).__name__}: {e}')
            self.coverage.append(entry)
        self.activity_readbacks()
        self.classified_documents()
        for i,f in enumerate(self.facts):self.index.execute('insert into facts values(?,?,?,?,?,?,?)',(i,f.resource_id,f.source_id,f.system_id,f.observed_at,f.available_at,json.dumps(f.payload,ensure_ascii=False)))
        self.index.execute('create index resource_idx on facts(resource)');self.index.commit()
        from .engine import tokens
        from collections import defaultdict
        self.identifier_index=defaultdict(set);self.resource_index=defaultdict(set)
        for i,f in enumerate(self.facts):
            for token in tokens(f.payload):self.identifier_index[token].add(i)
            self.resource_index[(f.system_id,f.resource_id)].add(i)
        return self
    def classified_documents(self):
        """Replay agreed LLM document classifications (prompts/document_classifications.json).

        A context-only document whose cached category was agreed by two models, and
        whose text shows the label a catalog row gives a resource, is a presence
        readback of that resource. Cache entries are bound to the file's sha256.
        """
        cache_path=Path(__file__).resolve().parents[1]/'prompts'/'document_classifications.json'
        if not cache_path.exists():return
        cache=json.loads(cache_path.read_text(encoding='utf-8'))
        manifest={m['file_id']:m for m in self.manifest}
        for entry in self.coverage:
            c=cache.get(entry['file_id'])
            if entry['status']!='context_only' or not c or not c.get('agreed') or c.get('sha256')!=entry.get('sha256') or c['data_category'] in (None,'NONE'):continue
            text=self.documents.get(entry['file_id'],'');m=manifest[entry['file_id']];start=len(self.facts)
            for a in self.activities:
                if a['event_type']!='LINK_RESOURCE_IDENTITY':continue
                for label in re.findall(r'\(([^()]+)\)',a['details']):
                    if len(label)>=6 and label in text:
                        available=max(m['captured_at'],a['event_time'],key=stamp)
                        self.facts.append(Fact(m['file_id'],'classified:'+label,a['target_system'],a['resource_id'],'primary',c['data_category'],'PRESENT',
                                               m['captured_at'],available,{'details':a['details'],'document_label':label,'link_time':a['event_time']},'classified_document','record'))
            if len(self.facts)>start:entry.update(status='ok',facts=len(self.facts)-start,classification=c['data_category'])
    def activity_readbacks(self):
        source_hash=digest(self.root/'system_activity.csv')
        for row_no,a in enumerate(self.activities,2):
            rid=a['resource_id'];detail=a['details'];state=None;category=None
            if a['event_type']=='CHECK_DATA_FLOW':
                match=re.fullmatch(r'Connector status check confirmed that data flow '+re.escape(rid)+r' remains (enabled|disabled)\.',detail,re.I)
                if match:category='DATA_FLOW';state='ACTIVE' if match[1].casefold()=='enabled' else 'DISABLED'
            elif a['event_type']=='CHECK_RESTORE_ACCESS':
                if re.fullmatch(r'Restore-access check confirmed that archive '+re.escape(rid)+r' can still be restored\.',detail,re.I):category='BACKUP_ARCHIVE';state='ACTIVE'
                elif re.fullmatch(r'Restore-access check confirmed that archive '+re.escape(rid)+r' is blocked from restore\.',detail,re.I):category='BACKUP_ARCHIVE';state='BLOCKED'
            if state:
                m={'file_id':a['activity_id'],'file_path':'system_activity.csv','captured_at':a['event_time'],'sha256':source_hash,'status':'ok'}
                self.extra_sources[a['activity_id']]=m
                self.add(m,'system_activity.csv/row:'+str(row_no),a['target_system'],rid,category,{'details':detail},a['event_time'],state=state,kind='activity_readback',scope='control')

    def json_file(self,m,obj):
        def visit(x,path='$',system=None,cat=None,at=None):
            if isinstance(x,dict):
                system=x.get('data_store',x.get('system',system));at=x.get('observed_at',x.get('recorded_at',x.get('captured_at',at)))
                collection=x.get('collection')
                if collection in COLLECTIONS:system,cat=COLLECTIONS[collection]
                if 'resource_id' in x and system:
                    cat=x.get('record_type',cat or SERVICES.get(system))
                    self.add(m,path,system,x['resource_id'],cat,x,at)
                    return
                for k,v in x.items():visit(v,path+'.'+k,k if k in SERVICES else system,cat,at)
            elif isinstance(x,list):
                for i,v in enumerate(x):visit(v,f'{path}[{i}]',system,cat,at)
        origin=m['origin'] if m['origin'] in SERVICES else None
        visit(obj,system=origin,cat=SERVICES.get(origin))
        # Empty snapshot collections are complete within the documented collection scope.
        for i,s in enumerate(obj.get('snapshots',[])):
            if s.get('collection') in COLLECTIONS:
                sys,cat=COLLECTIONS[s['collection']]
                self.inventories.append((m,f'$.snapshots[{i}]',sys,cat,'primary',s.get('captured_at',m['captured_at']),{r['resource_id'] for r in s.get('records',[])}))
    def sql_file(self,m,text):
        if not (text.startswith('-- Ghost Data Still Exists: point-in-time database snapshot') or 'CREATE TABLE snapshot_scope ' in text):raise ValueError('unrecognized snapshot contract')
        tables=snapshot(text)
        scope={r['origin_system']:r['captured_at'] for r in tables.get('snapshot_scope',[])}
        for table,rs in tables.items():
            if table=='snapshot_scope':continue
            copy=table if 'replica' in table else 'primary'
            inventory={}
            for i,r in enumerate(rs):
                if 'record_json' in r:
                    obj=json.loads(r['record_json']);system,cat=COLLECTIONS.get(r['collection_name'],(None,None))
                    if system!=r['origin_system']:raise ValueError('conflicting SQL classification')
                else:
                    obj=r;system,cat=COLLECTIONS.get(table,(None,None))
                self.add(m,f'{table}/row:{i+1}',system,r['resource_id'],cat,obj,scope.get(system,m['captured_at']),copy)
                inventory.setdefault((system,cat),set()).add(r['resource_id'])
            if 'record_json' not in (rs[0] if rs else {}):
                if table in COLLECTIONS:inventory.setdefault(COLLECTIONS[table],set())
            # The generic customer_data tables contain a complete multi-service snapshot.
            if table.startswith('customer_data_'):
                for system,cat in COLLECTIONS.values():inventory.setdefault((system,cat),set())
            for (sys,cat),ids in inventory.items():self.inventories.append((m,table,sys,cat,copy,m['captured_at'],ids))
    def text_file(self,m,text):
        self.documents[m['file_id']]=self.documents.get(m['file_id'],'')+'\n'+text
        for i,l in enumerate(text.splitlines()):
            a=[s.strip() for s in l.removeprefix('- ').split('|')]
            if len(a)==6 and 'T' in a[0]:self.add(m,f'line:{i+1}',a[1],a[2],a[3],{'result':a[4],'subject_reference':a[5]},a[0])
    def log_file(self,m,text):
        traces={}
        for i,line in enumerate(text.splitlines()):
            try:tok=shlex.split(line)
            except ValueError:raise ValueError(f'malformed log line {i+1}')
            if not tok:continue
            if len(tok)>1 and line.split(' ',1)[1].startswith('{'):
                kv=json.loads(line.split(' ',1)[1])
            else:
                kv=dict(t.split('=',1) for t in tok[1:] if '=' in t)
                if 'message' in kv:
                    kv.update(dict(t.split('=',1) for t in shlex.split(kv.pop('message')) if '=' in t))
                    kv['service']=kv.pop('function');kv['trace_id']=kv.pop('requestId')
                elif len(tok)>5 and re.fullmatch(r'<\d+>1',tok[1]):
                    kv['service']=tok[3];kv['trace_id']=tok[4]
                elif len(tok)>5 and tok[1].startswith('['):
                    kv['service']=tok[2].strip('[]');kv['trace_id']=tok[3].strip('[]');kv['event']=tok[4].rstrip(':')
                elif ' | ' in line:
                    parts=[t.strip() for t in line.split('|')]
                    if len(parts)>=6:kv['service']=parts[2];kv['trace_id']=parts[3];kv['event']=parts[4]
            kv={k:(None if v=='null' else v) for k,v in kv.items()}
            trace=(kv.get('service'),kv['trace_id']) if kv.get('trace_id') else None;old=traces.get(trace,{}) if trace else {}
            obj={**old,**kv}
            if trace:traces[trace]=obj
            rid=obj.get('resource_id');event=kv.get('event','');system=kv.get('service')
            if not rid:continue
            cat=SERVICES.get(system)
            if system=='support_replica':system='support_platform';cat='SECONDARY_IDENTIFIER'
            if event=='record_lookup':
                system=obj.get('system',system);cat=obj.get('record_type')
            state=None
            if event in ('profile_lookup_completed','contact_query_completed'):state=row_presence(obj)
            elif event=='index_query_completed':state='ABSENT' if obj.get('result')=='miss' or obj.get('total_hits')=='0' else 'PRESENT'
            elif event in ('message_pii_scan','attachment_pii_scan','analytics_identity_scan'):
                cat={'message_pii_scan':'SUPPORT_MESSAGE','attachment_pii_scan':'SUPPORT_ATTACHMENT','analytics_identity_scan':'ANALYTICS_PROFILE'}[event];state='PRESENT' if event=='attachment_pii_scan' else 'IDENTIFIABLE'
            elif event in ('connector_heartbeat','connector_config_read_completed'):cat='DATA_FLOW';state='ACTIVE' if control_bool(obj.get('enabled')) else 'DISABLED'
            elif event=='restore_candidate_evaluated':cat='BACKUP_ARCHIVE';state='ACTIVE' if control_bool(obj.get('eligible')) and not control_bool(obj.get('deletion_block')) else 'BLOCKED'
            elif event=='restore_policy_read_completed':cat='BACKUP_ARCHIVE';state=infer_state(cat,obj)
            elif event in ('export_download_check_completed','export_metadata_read_completed'):cat='USER_EXPORT';state='PRESENT' if obj.get('available')=='true' else 'ABSENT'
            elif event=='contact_lookup_completed':cat='SECONDARY_IDENTIFIER';state='PRESENT'
            elif event in ('analytics_profile_read','analytics_profile_read_completed'):cat='ANALYTICS_PROFILE';state='ANONYMIZED' if obj.get('direct_identifiers')=='0' else infer_state(cat,{k:v for k,v in obj.items() if k not in ('lookup_key','correlation_key','subject_key','match_key')})
            elif event=='message_read':cat='SUPPORT_MESSAGE';state='REDACTED' if str(obj.get('message_text','')).strip()=='[REDACTED]' else infer_state(cat,{k:v for k,v in obj.items() if k not in ('lookup_key','correlation_key','subject_key','match_key')})
            elif event=='support_ticket_read_completed':cat='SUPPORT_MESSAGE';state=infer_state(cat,{k:v for k,v in obj.items() if k not in ('lookup_key','correlation_key','subject_key','match_key')})
            elif event=='audit_record_read_completed':cat='SECURITY_AUDIT_LOG';state=row_presence(obj)
            elif event=='record_lookup':state=infer_state(cat,obj)
            if state and cat:
                copy='primary'
                if 'replica' in str(obj.get('pool','')) and obj.get('route')!='primary':copy=str(obj.get('region','unknown-region'))+':'+str(obj['pool'])
                self.add(m,f'line:{i+1}',system,rid,cat,obj,tok[0],state=state,copy=copy)
    def ocr(self,p):
        key=digest(p)+'-rapidocr-1.4.4-v1.txt';out=self.cache/key
        if out.exists():
            text=out.read_text()
            if not text.strip():raise ValueError('OCR produced no readable text')
            return text
        # Run OCR outside the ingestion process to bound runtime and memory.
        script="from rapidocr_onnxruntime import RapidOCR; import sys,json; r,_=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=2)(sys.argv[1]); print(json.dumps(r))"
        result=subprocess.run([__import__('sys').executable,'-c',script,str(p)],capture_output=True,text=True,timeout=180)
        if result.returncode:raise RuntimeError('OCR failed: '+result.stderr[-300:])
        regions=json.loads(result.stdout)
        if not isinstance(regions,list) or not regions:raise ValueError('OCR produced no readable text')
        if any(not isinstance(r,(list,tuple)) or len(r)!=3 or not isinstance(r[1],str) for r in regions):raise ValueError('OCR produced malformed regions')
        text='\n'.join(r[1] for r in regions)
        if not text.strip():raise ValueError('OCR produced no readable text')
        self.cache.joinpath(key+'.regions').write_text(json.dumps(regions,ensure_ascii=False))
        out.write_text(text);return text
    def image_rows(self,m):
        p=safe_path(self.root,m['file_path']);key=digest(p)+'-rapidocr-1.4.4-v1.txt.regions'
        regions=json.loads((self.cache/key).read_text());lines=[]
        for box,text,confidence in sorted(regions or [],key=lambda r:sum(p[1] for p in r[0])/4):
            y=sum(p[1] for p in box)/4;x=min(p[0] for p in box)
            if lines and abs(lines[-1][0]-y)<9:lines[-1][1].append((x,text,confidence))
            else:lines.append((y,[(x,text,confidence)]))
        return [(y,' | '.join(t for _,t,c in sorted(a)),min(c for _,t,c in a)) for y,a in lines]
    def document(self,m,text,location):
        self.text_file(m,text)
        from .policy_support import legal_register_rows
        combined=self.documents[m['file_id']]
        compact=re.sub(r'[^a-z0-9]','',combined.casefold())
        legal_metadata=bool(legal_register_rows(combined))
        stable_registry=('customerreferenceregistry' in compact and 'customerkey' in compact and 'linked to customer' in combined.casefold() and not re.search(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\+\d[\d ()-]{7,}',combined))
        if legal_metadata or stable_registry:
            if not hasattr(self,'metadata_documents'):self.metadata_documents=set()
            self.metadata_documents.add(m['file_id'])
        if location=='image':
            lines=self.image_rows(m)
            full=' '.join(t for _,t,_ in lines).casefold()
            # Classification follows visible application headings/content, never file names.
            domains=[('customeroperations','account_service','USER_PROFILE'),('customer operations','account_service','USER_PROFILE'),('search console','search_service','SEARCH_INDEX_ENTRY'),('bridgeops','integration_service','DATA_FLOW'),('pulse analytics','analytics_platform','ANALYTICS_PROFILE'),('audience operations','marketing_platform','MARKETING_PROFILE'),('vault recovery','backup_service','BACKUP_ARCHIVE'),('export','export_service','USER_EXPORT'),('support','support_platform','SUPPORT_MESSAGE'),('deleted','identity_service','ACCOUNT_TOMBSTONE'),('audit','security_service','SECURITY_AUDIT_LOG'),('object','export_service','USER_EXPORT')]
            domain=next(((sys,cat) for word,sys,cat in domains if word in full),None)
            if not domain:return
            sys,cat=domain
            # Rows remain isolated. Header cards combine only the focused resource and its contacts.
            header=' '.join(t for y,t,c in lines if 80<=y<=300)
            prefix={'USER_PROFILE':'account','SEARCH_INDEX_ENTRY':'search','DATA_FLOW':'data_flow','ANALYTICS_PROFILE':'analytics','MARKETING_PROFILE':'marketing','BACKUP_ARCHIVE':'backup','USER_EXPORT':'export','SUPPORT_MESSAGE':'support','ACCOUNT_TOMBSTONE':'tombstone','SECURITY_AUDIT_LOG':'audit_record'}[cat]
            pattern=r'\b'+prefix+r'_\d+\b'
            candidates=[('header',header)]+[(f'row_y:{int(y)}',t) for y,t,c in lines if c>=0.8]
            for loc,t in candidates:
                rids=set(re.findall(pattern,t));emails=re.findall(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',t);uids=re.findall(r'\buser_\d+\b',t)
                if len(rids)!=1 or not (emails or uids):continue
                obj={'text':t,'email':emails[0] if emails else None,'subject_reference':uids[0] if uids else None}
                if cat in ('DATA_FLOW','BACKUP_ARCHIVE'):
                    # A healthy connector with a continuous mode is an enabled configuration.
                    if cat=='DATA_FLOW' and re.search(r'\bcontinuous\b|\benabled\b',t.casefold()):obj['enabled']=True
                    elif cat=='BACKUP_ARCHIVE':
                        # Admit physical presence/ownership only, never invented restore permission.
                        self.add(m,location+'/'+loc,sys,next(iter(rids)),cat,obj,state='PRESENT',kind='ocr',scope='presence')
                        continue
                    else:continue
                if cat=='ACCOUNT_TOMBSTONE':obj['account_status']='DELETED'
                self.add(m,location+'/'+loc,sys,next(iter(rids)),cat,obj,kind='ocr')
        elif 'Event reference' in text and 'subject reference' in text:
            rid=re.search(r'\baudit_record_\d+\b',text);uid=re.search(r'\buser_\d+\b',text)
            if rid and uid:
                payload={'subject_reference':uid[0],'text':text}
                until=labelled_utc_date(text,'retain until')
                if until:payload['retention_until']=until
                recorded=labelled_utc_date(text,'recorded')
                if recorded:payload['event_recorded_at']=recorded
                self.add(m,location,'security_service',rid[0],'SECURITY_AUDIT_LOG',payload,kind='pdf_text')
        elif 'Support reference' in text and re.search(r'\bsupport_\d+\b',text):
            rid=re.search(r'\bsupport_\d+\b',text)[0];emails=re.findall(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',text)
            if emails:self.add(m,location,'support_platform',rid,'SUPPORT_ATTACHMENT',{'uploaded_by':emails[0],'text':text},kind='pdf_text')
