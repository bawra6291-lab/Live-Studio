"""Persistent phone trust, migration and revoke tests against the actual relay."""
import json,secrets,sqlite3,sys,tempfile,time,unittest,threading,urllib.request,urllib.error
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'remote'))
from store import Store,digest,SESSION_AGE
from server import Server

class PersistentPhones(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'relay.db';self.store=Store(self.path)
        self.workspace=self.store.create_workspace('Temple');self.owner=self.store.grant(self.workspace,'owner')
        self.token,self.csrf=self.store.login(self.owner['token']);self.principal=self.store.authenticate(self.token)
    def tearDown(self):self.tmp.cleanup()
    def test_pair_once_survives_restart_and_twelve_hour_limit(self):
        with patch('store.time.time',return_value=time.time()+86400*30):
            restarted=Store(self.path);principal=restarted.authenticate(self.token)
            self.assertEqual(principal['id'],self.owner['id'])
            with restarted.db() as db:self.assertGreater(db.execute('SELECT expires FROM sessions').fetchone()[0],time.time()+SESSION_AGE-1)
    def test_each_phone_independent_revocation_and_logout(self):
        another,_=self.store.login(self.owner['token']);p=self.store.authenticate(another)
        self.store.revoke(self.principal,p['session_id'],'phone')
        with self.assertRaises(PermissionError):self.store.authenticate(another)
        self.store.authenticate(self.token)
        self.store.logout(self.token)
        with self.assertRaises(PermissionError):self.store.authenticate(self.token)
    def test_forgetting_phone_cancels_its_queued_commands(self):
        a=self.store.grant(self.workspace,'agent');agent=self.store.authenticate(a['token'],agent=True)
        self.store.poll(agent,{'boot':'a'*32,'snapshot':{}})
        self.store.enqueue(self.principal,{'device':agent['id'],'boot':'a'*32,'action':'arm','nonce':'b'*32,'confirmed':True})
        self.store.revoke(self.principal,self.principal['session_id'],'phone')
        self.assertIsNone(self.store.poll(agent,{'boot':'a'*32,'snapshot':{}}))
    def test_foreign_owner_cannot_revoke_phone(self):
        other=self.store.create_workspace('Other');grant=self.store.grant(other,'owner');token,_=self.store.login(grant['token'])
        self.store.revoke(self.store.authenticate(token),self.principal['session_id'],'phone')
        self.store.authenticate(self.token)
    def test_inactive_expiry_and_principal_revoke_still_apply(self):
        with patch('store.time.time',return_value=time.time()+SESSION_AGE+1):
            with self.assertRaises(PermissionError):self.store.authenticate(self.token)
        with self.store.db() as db:db.execute('UPDATE principals SET enabled=0 WHERE id=?',(self.owner['id'],))
        with self.assertRaises(PermissionError):self.store.authenticate(self.token)
    def test_bootstrap_does_not_reset_existing_revocations(self):
        seed={'workspace':secrets.token_hex(16),'owner':secrets.token_hex(16),'agent':secrets.token_hex(16),'owner_hash':digest('owner-code'),'agent_hash':digest('agent-code'),'name':'Temple'}
        self.store.bootstrap(seed)
        with self.store.db() as db:db.execute('UPDATE principals SET enabled=0 WHERE id=?',(seed['owner'],))
        Store(self.path).bootstrap(seed)
        with self.store.db() as db:self.assertEqual(db.execute('SELECT enabled FROM principals WHERE id=?',(seed['owner'],)).fetchone()[0],0)
    def test_server_restart_does_not_claim_old_pc_online(self):
        agent=self.store.grant(self.workspace,'agent');a=self.store.authenticate(agent['token'],agent=True)
        self.store.poll(a,{'boot':'a'*32,'snapshot':{'armed':False}})
        self.assertTrue(self.store.state(self.principal)['devices'][0]['online']);self.store.mark_offline()
        self.assertFalse(self.store.state(self.principal)['devices'][0]['online'])
    def test_schema_migration_retains_existing_pairing(self):
        path=Path(self.tmp.name)/'old.db'
        db=sqlite3.connect(path);db.execute('CREATE TABLE sessions(secret TEXT PRIMARY KEY,principal TEXT NOT NULL,csrf TEXT NOT NULL,expires REAL NOT NULL)');db.commit();db.close()
        old=Store(path);w=old.create_workspace('Old');g=old.grant(w,'owner');token,_=old.login(g['token'])
        self.assertEqual(Store(path).authenticate(token)['id'],g['id'])
    def test_unconfigured_deployment_health_only_no_controls(self):
        server=Server(('127.0.0.1',0),self.store,'');threading.Thread(target=server.serve_forever,daemon=True).start()
        base='http://127.0.0.1:'+str(server.server_port)
        try:
            with urllib.request.urlopen(base+'/health') as r:self.assertFalse(json.load(r)['configured'])
            with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(base+'/api/state')
            self.assertEqual(e.exception.code,503)
            req=urllib.request.Request(base+'/api/login',data=b'{}',headers={'Content-Type':'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(req)
            self.assertEqual(e.exception.code,503)
        finally:server.shutdown();server.server_close()
    def test_http_persistent_cookie_csrf_and_agent_auth(self):
        server=Server(('127.0.0.1',0),self.store,'https://desk.test');threading.Thread(target=server.serve_forever,daemon=True).start()
        base='http://127.0.0.1:'+str(server.server_port)
        def request(path,data=None,headers=None):
            raw=None if data is None else json.dumps(data).encode()
            req=urllib.request.Request(base+path,data=raw,headers={'Content-Type':'application/json',**(headers or {})})
            return urllib.request.urlopen(req,timeout=3)
        try:
            with request('/api/login',{'code':self.owner['token']},{'Origin':'https://desk.test'}) as r:
                cookie=r.headers['Set-Cookie'];self.assertIn('Max-Age='+str(SESSION_AGE),cookie);self.assertIn('HttpOnly',cookie);self.assertIn('Secure',cookie);self.assertIn('SameSite=Strict',cookie)
            with request('/api/state',headers={'Cookie':cookie.split(';')[0]}) as r:
                self.assertIn('Max-Age='+str(SESSION_AGE),r.headers['Set-Cookie']);state=json.load(r);self.assertEqual(state['role'],'owner')
            with self.assertRaises(urllib.error.HTTPError) as e:request('/api/logout',{}, {'Origin':'https://evil.test','Cookie':cookie.split(';')[0],'X-CSRF-Token':state['csrf']})
            self.assertEqual(e.exception.code,403)
            with self.assertRaises(urllib.error.HTTPError):request('/api/agent/poll',{'boot':'a'*32,'snapshot':{}},{'Authorization':'Bearer bad'})
            with request('/health') as r:self.assertTrue(json.load(r)['ok'])
        finally:server.shutdown();server.server_close()
if __name__=='__main__':unittest.main()
