"""Real HTTP boundary tests, with no calls to OBS, YouTube, Facebook or the camera."""
import http.client, json, sys, tempfile, threading, time, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dashboard import Controller, DashboardServer, Handler
from core import atomic_json

class Vault:
    def __init__(self):self.values={'facebook_page_token':'sensitive-page-token','camera_password':'private-camera-password'}
    def get(self,key):return self.values.get(key,'')
    def set(self,key,value):self.values[key]=value

class Service:
    calls=0; gate=None
    def __init__(self,cfg,vault,log):self.log=log
    def check(self):
        type(self).calls+=1
        if type(self).gate:type(self).gate.wait(2)
        for line in ['OBS connected. Program scene: Main','YouTube channel verified: Example','Facebook Page verified: Example','Camera reachable; Patrol 8 exists.']:
            self.log(line)
    def close(self):pass

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();Service.calls=0;Service.gate=None
        self.vault=Vault();self.c=Controller(self.tmp.name,Service,self.vault)
        self.server=DashboardServer(('127.0.0.1',0),self.c,'test-pairing-code')
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.host=f'127.0.0.1:{self.server.server_port}';self.cookie='';self.csrf=''
    def tearDown(self):
        self.c.shutdown()
        if Service.gate:Service.gate.set()
        if self.c.worker:self.c.worker.join(3)
        self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
    def request(self,path,data=None,**headers):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=4)
        defaults={'Host':self.host,'Origin':'http://'+self.host,'Content-Type':'application/json','Cookie':self.cookie,'X-CSRF-Token':self.csrf};defaults.update(headers)
        conn.request('POST' if data is not None else 'GET',path,json.dumps(data) if data is not None else None,defaults)
        r=conn.getresponse();body=r.read();cookie=r.getheader('Set-Cookie');ctype=r.getheader('Content-Type','');status=r.status;conn.close()
        return status,json.loads(body) if 'application/json' in ctype else body,cookie
    def login(self):
        status,_,cookie=self.request('/api/login',{'code':'test-pairing-code'});self.assertEqual(status,200)
        self.cookie=cookie.split(';')[0]
        status,body,_=self.request('/api/state');self.assertEqual(status,200);self.csrf=body['csrf'];return body
    def test_pair_required_and_logout_invalidates(self):
        self.assertEqual(self.request('/api/state')[0],401)
        self.login();self.assertEqual(self.request('/api/logout',{})[0],200)
        self.assertEqual(self.request('/api/state')[0],401)
    def test_updates_panel_is_local_and_authenticated(self):
        from unittest.mock import Mock
        self.c.open_updates=Mock()
        self.assertEqual(self.request('/api/updates/open',{})[0],401)
        self.login()
        with patch.object(Handler,'local',return_value=False):
            self.assertEqual(self.request('/api/updates/open',{})[0],403)
        self.c.open_updates.assert_not_called()
        self.assertEqual(self.request('/api/updates/open',{},**{'X-CSRF-Token':'wrong'})[0],403)
        self.assertEqual(self.request('/api/updates/open',{})[0],200)
        self.c.open_updates.assert_called_once()
    def test_wrong_code_and_rate_limit(self):
        for _ in range(8):self.assertEqual(self.request('/api/login',{'code':'bad'})[0],401)
        self.assertEqual(self.request('/api/login',{'code':'test-pairing-code'})[0],429)
    def test_host_origin_and_csrf_are_required(self):
        self.login()
        self.assertEqual(self.request('/api/action',{'action':'check'},Host='evil.example')[0],403)
        self.assertEqual(self.request('/api/action',{'action':'check'},Origin='http://evil.example')[0],403)
        self.assertEqual(self.request('/api/action',{'action':'check'},**{'X-CSRF-Token':''})[0],403)
        self.assertEqual(Service.calls,0)
    def test_arming_requires_explicit_confirmation(self):
        self.login();self.assertEqual(self.request('/api/action',{'action':'arm'})[0],409);self.assertEqual(Service.calls,0)
    def test_token_values_never_in_state(self):
        data=self.login();raw=json.dumps(data)
        for secret in self.vault.values.values():self.assertNotIn(secret,raw)
        self.assertNotIn('facebook_page_token',data['settings'])
    def test_remote_cannot_read_or_change_settings(self):
        self.login()
        with patch.object(Handler,'local',return_value=False):
            data=self.request('/api/state')[1];self.assertIsNone(data['settings']);self.assertFalse(data['local'])
            self.assertEqual(self.request('/api/settings',{'camera_password':'new'})[0],403)
            self.assertEqual(self.request('/api/action',{'action':'youtube'})[0],403)
        self.assertEqual(self.vault.get('camera_password'),'private-camera-password')
    def test_save_preserves_blank_credentials_and_unknown_settings(self):
        self.login();self.c.cfg['future_option']='keep'
        self.assertEqual(self.request('/api/settings',{'obs_scene':'Main 2','facebook_page_token':''})[0],200)
        cfg=json.loads(self.c.path.read_text());self.assertEqual(cfg['future_option'],'keep');self.assertEqual(cfg['obs_scene'],'Main 2')
        self.assertEqual(self.vault.get('facebook_page_token'),'sensitive-page-token')
    def test_pause_during_check_cannot_rearm(self):
        Service.gate=threading.Event();self.login()
        self.assertEqual(self.request('/api/action',{'action':'arm','confirmed':True})[0],200)
        self.assertEqual(self.request('/api/action',{'action':'check'})[0],409)
        self.assertEqual(self.request('/api/settings',{'obs_scene':'changed'})[0],409)
        self.assertEqual(self.request('/api/action',{'action':'pause'})[0],200)
        Service.gate.set();self.c.worker.join(3)
        self.assertFalse(self.c.armed);self.assertFalse(json.loads(self.c.path.read_text())['armed'])
        self.assertEqual(Service.calls,1)
    def test_broken_settings_not_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'settings.json';path.write_text('{broken')
            with self.assertRaises(json.JSONDecodeError):Controller(directory,Service,self.vault)
            self.assertEqual(path.read_text(),'{broken')
    def test_missing_and_traversal_paths_rejected(self):
        self.login()
        for path in ['/settings.json','/../connections.py','/api/stop','/api/end']:
            self.assertEqual(self.request(path)[0],404)
    def test_check_has_no_broadcast_side_effects(self):
        self.login();self.assertEqual(self.request('/api/action',{'action':'check'})[0],200);self.c.worker.join(3)
        self.assertEqual(Service.calls,1);self.assertFalse(self.c.armed);self.assertIsNotNone(self.c.checked)
        self.assertFalse((self.c.base/'journal.json').exists())

if __name__=='__main__':unittest.main()
