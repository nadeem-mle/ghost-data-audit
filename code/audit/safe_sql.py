"""Execute only snapshot DDL/DML in a resource-limited isolated subprocess."""
import sqlite3, re, multiprocessing, resource

def _worker(script,send):
    try:
        resource.setrlimit(resource.RLIMIT_CPU,(5,5))
        resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2))
        db=sqlite3.connect(':memory:')
        if len(script.encode())>16*1024**2:raise ValueError('SQL size limit')
        if hasattr(db,'setlimit'):
            db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH,8*1024**2)
            db.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH,16*1024**2)
        calls=0
        def progress():
            nonlocal calls
            calls+=1
            return calls>10000
        db.set_progress_handler(progress,1000)
        allowed={sqlite3.SQLITE_CREATE_INDEX,sqlite3.SQLITE_REINDEX,sqlite3.SQLITE_CREATE_TABLE,sqlite3.SQLITE_INSERT,sqlite3.SQLITE_UPDATE,sqlite3.SQLITE_READ,sqlite3.SQLITE_SELECT,sqlite3.SQLITE_TRANSACTION}
        def auth(action,a,b,c,d):
            if action==sqlite3.SQLITE_PRAGMA:return sqlite3.SQLITE_OK if a=='foreign_keys' and b in ('ON','1') else sqlite3.SQLITE_DENY
            if action==sqlite3.SQLITE_FUNCTION:return sqlite3.SQLITE_OK if (b or '').lower()=='json_valid' else sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY
        db.set_authorizer(auth)
        # Parse statement boundaries with SQLite, then constrain statement class.
        acc=''
        for line in script.splitlines(True):
            acc+=line
            if sqlite3.complete_statement(acc):
                clean=re.sub(r'--[^\n]*','',acc).strip()
                if clean and not re.match(r'^(BEGIN(?: TRANSACTION)?;|COMMIT;|PRAGMA foreign_keys\s*=\s*ON;|CREATE INDEX\s|CREATE TABLE\s|INSERT INTO\s)',clean,re.I):raise ValueError('unsafe snapshot statement')
                db.execute(acc);acc=''
        if re.sub(r'--[^\n]*','',acc).strip():raise ValueError('incomplete SQL')
        tables=[r[0] for r in db.execute("select name from sqlite_master where type='table'")]
        result={}
        for t in tables:
            if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',t):raise ValueError('invalid table name')
            q=db.execute('select * from "'+t+'"'); cols=[r[0] for r in q.description]
            result[t]=[dict(zip(cols,r)) for r in q.fetchall()]
        send.send(('ok',result))
    except Exception as e:send.send(('error',str(e)))
    finally:send.close()

def snapshot(script):
    parent,child=multiprocessing.Pipe(False)
    p=multiprocessing.Process(target=_worker,args=(script,child));p.start();child.close()
    if not parent.poll(12):p.terminate();p.join();raise ValueError('SQL timeout')
    kind,value=parent.recv();p.join(2)
    if p.is_alive():p.terminate();p.join()
    if kind!='ok':raise ValueError(value)
    return value
