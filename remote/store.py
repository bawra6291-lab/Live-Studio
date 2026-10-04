"""Tenant-scoped relay storage. Commands are delivered once, never replayed."""
import hashlib,json,re,secrets,sqlite3,time
from contextlib import contextmanager

def digest(value):return hashlib.sha256(value.encode()).hexdigest()

class Store:
    def __init__(self,path):
        self.path=str(path)
        with self.db() as db:db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS workspaces(id TEXT PRIMARY KEY,name TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS principals(id TEXT PRIMARY KEY,workspace TEXT NOT NULL,role TEXT NOT NULL,secret TEXT UNIQUE NOT NULL,enabled INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS sessions(secret TEXT PRIMARY KEY,principal TEXT NOT NULL,csrf TEXT NOT NULL,expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY,workspace TEXT NOT NULL,name TEXT NOT NULL,secret TEXT UNIQUE NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,seen REAL NOT NULL DEFAULT 0,boot TEXT NOT NULL DEFAULT '',snapshot TEXT NOT NULL DEFAULT '{}');
        CREATE TABLE IF NOT EXISTS commands(id TEXT PRIMARY KEY,device TEXT NOT NULL,workspace TEXT NOT NULL,actor TEXT NOT NULL,nonce TEXT NOT NULL,action TEXT NOT NULL,args TEXT NOT NULL,boot TEXT NOT NULL,created REAL NOT NULL,expires REAL NOT NULL,status TEXT NOT NULL,result TEXT NOT NULL DEFAULT '',UNIQUE(device,nonce));
        ''')
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row
        try:
            db.execute('PRAGMA foreign_keys=ON');yield db;db.commit()
        except Exception:db.rollback();raise
        finally:db.close()
    def create_workspace(self,name):
        if not isinstance(name,str) or not 1<=len(name)<=80:raise ValueError('Workspace name must be 1–80 characters.')
        ident=secrets.token_hex(16)
        with self.db() as db:db.execute('INSERT INTO workspaces VALUES(?,?)',(ident,name))
        return ident
    def grant(self,workspace,role,name='Livestream PC'):
        if role not in ('owner','operator','viewer','agent'):raise ValueError('Invalid role.')
        token=secrets.token_urlsafe(32);ident=secrets.token_hex(16)
        with self.db() as db:
            if not db.execute('SELECT 1 FROM workspaces WHERE id=?',(workspace,)).fetchone():raise ValueError('Unknown workspace.')
            if role=='agent':db.execute('INSERT INTO devices(id,workspace,name,secret) VALUES(?,?,?,?)',(ident,workspace,name[:80],digest(token)))
            else:db.execute('INSERT INTO principals(id,workspace,role,secret) VALUES(?,?,?,?)',(ident,workspace,role,digest(token)))
        return {'id':ident,'token':token,'role':role}
    def login(self,token):
        with self.db() as db:
            principal=db.execute('SELECT * FROM principals WHERE secret=? AND enabled=1',(digest(token),)).fetchone()
            if not principal:raise PermissionError('Invalid or revoked access code.')
            session=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(24)
            db.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
            db.execute('INSERT INTO sessions VALUES(?,?,?,?)',(digest(session),principal['id'],csrf,time.time()+43200))
            return session,csrf
    def authenticate(self,token,agent=False):
        with self.db() as db:
            if agent:row=db.execute('SELECT * FROM devices WHERE secret=? AND enabled=1',(digest(token),)).fetchone()
            else:row=db.execute('SELECT p.*,s.csrf FROM sessions s JOIN principals p ON p.id=s.principal WHERE s.secret=? AND s.expires>? AND p.enabled=1',(digest(token),time.time())).fetchone()
            if not row:raise PermissionError('Sign in again; authorization expired or was revoked.')
            return dict(row)
    def logout(self,token):
        with self.db() as db:db.execute('DELETE FROM sessions WHERE secret=?',(digest(token),))
    def state(self,principal):
        now=time.time()
        with self.db() as db:
            db.execute("UPDATE commands SET status='expired',result='Expired without execution' WHERE status='queued' AND expires<?",(now,))
            db.execute("UPDATE commands SET status='unknown',result='No acknowledgement; inspect PC before retrying' WHERE status='dispatched' AND expires<?",(now-120,))
            devices=[{'id':row['id'],'name':row['name'],'online':now-row['seen']<=15,'seen':row['seen'],'boot':row['boot'],'snapshot':json.loads(row['snapshot'])} for row in db.execute('SELECT * FROM devices WHERE workspace=? AND enabled=1',(principal['workspace'],))]
            commands=[{k:row[k] for k in ('id','device','action','created','status','result')} for row in db.execute('SELECT * FROM commands WHERE workspace=? ORDER BY created DESC LIMIT 50',(principal['workspace'],))]
            members=[{k:row[k] for k in ('id','role','enabled')} for row in db.execute('SELECT * FROM principals WHERE workspace=?',(principal['workspace'],))] if principal['role']=='owner' else []
        return {'role':principal['role'],'csrf':principal['csrf'],'devices':devices,'commands':commands,'members':members}
    def enqueue(self,principal,data):
        if principal['role'] not in ('owner','operator'):raise PermissionError('View-only access.')
        action=data.get('action');args=data.get('args',{});nonce=data.get('nonce')
        if action not in ('check','arm','pause','end') or data.get('confirmed') is not True:raise ValueError('Confirm a supported action.')
        if not isinstance(nonce,str) or not re.fullmatch(r'[a-f0-9-]{16,64}',nonce):raise ValueError('Invalid command nonce.')
        if not isinstance(args,dict) or set(args)-{'key'} or (action=='end' and not re.fullmatch(r'\d{4}-\d{2}-\d{2}:[a-z][a-z0-9_-]{0,47}',str(args.get('key','')))):raise ValueError('Invalid command arguments.')
        now=time.time()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            device=db.execute('SELECT * FROM devices WHERE id=? AND workspace=? AND enabled=1',(data.get('device'),principal['workspace'])).fetchone()
            if not device:raise PermissionError('Device unavailable in this workspace.')
            existing=db.execute('SELECT * FROM commands WHERE device=? AND nonce=?',(device['id'],nonce)).fetchone()
            if existing:
                if existing['actor']!=principal['id'] or existing['action']!=action or json.loads(existing['args'])!=args:raise ValueError('Nonce already used for a different command.')
                return existing['id']
            if now-device['seen']>15 or data.get('boot')!=device['boot']:raise ValueError('PC offline or restarted. Refresh before issuing a command.')
            if db.execute("SELECT 1 FROM commands WHERE device=? AND status='queued' AND expires>?",(device['id'],now)).fetchone():raise ValueError('Wait for the pending command.')
            ident=secrets.token_hex(16)
            db.execute('INSERT INTO commands VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(ident,device['id'],principal['workspace'],principal['id'],nonce,action,json.dumps(args),device['boot'],now,now+45,'queued',''))
            return ident
    def poll(self,agent,data):
        boot=data.get('boot');snapshot=data.get('snapshot');ack=data.get('ack')
        if not isinstance(boot,str) or not re.fullmatch(r'[a-f0-9]{32}',boot) or not isinstance(snapshot,dict):raise ValueError('Invalid heartbeat.')
        # Never store settings, cookies, stream keys, workflow recipes or diagnostics.
        allowed=('workspace_name','now','armed','busy','mode','message','error','connections','checked','next','slots','last_tick','app_version')
        snapshot={k:snapshot[k] for k in allowed if k in snapshot}
        if len(json.dumps(snapshot))>50000:raise ValueError('Snapshot too large.')
        now=time.time()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            # Recheck revocation in the transaction; a request may have authenticated earlier.
            if not db.execute('SELECT 1 FROM devices WHERE id=? AND enabled=1',(agent['id'],)).fetchone():raise PermissionError('Device revoked.')
            db.execute('UPDATE devices SET seen=?,boot=?,snapshot=? WHERE id=?',(now,boot,json.dumps(snapshot),agent['id']))
            if isinstance(ack,dict) and ack.get('status') in ('accepted','rejected'):
                db.execute("UPDATE commands SET status=?,result=? WHERE id=? AND device=? AND status='dispatched'",(ack['status'],str(ack.get('message',''))[:200],ack.get('id'),agent['id']))
            db.execute("UPDATE commands SET status='expired',result='Expired or PC restarted' WHERE device=? AND status='queued' AND (expires<? OR boot!=?)",(agent['id'],now,boot))
            command=db.execute("SELECT c.* FROM commands c JOIN principals p ON p.id=c.actor WHERE c.device=? AND c.status='queued' AND c.expires>? AND c.boot=? AND p.enabled=1 ORDER BY c.created LIMIT 1",(agent['id'],now,boot)).fetchone()
            if not command:return None
            db.execute("UPDATE commands SET status='dispatched' WHERE id=?",(command['id'],))
            return {k:json.loads(command[k]) if k=='args' else command[k] for k in ('id','action','args','expires','boot')}
    def revoke(self,principal,ident,kind):
        if principal['role']!='owner':raise PermissionError('Owner access required.')
        if kind not in ('principal','device'):raise ValueError('Unknown revocation type.')
        if kind=='principal' and ident==principal['id']:raise ValueError('Owner cannot revoke their own access here.')
        table='principals' if kind=='principal' else 'devices'
        with self.db() as db:
            db.execute(f'UPDATE {table} SET enabled=0 WHERE id=? AND workspace=?',(ident,principal['workspace']))
            if kind=='principal':db.execute("UPDATE commands SET status='revoked' WHERE actor=? AND workspace=? AND status='queued'",(ident,principal['workspace']))
