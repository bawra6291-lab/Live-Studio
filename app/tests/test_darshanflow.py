"""The supplied studio stays byte-for-byte intact and behind pairing."""
import hashlib,http.client,json,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dashboard import WEB,Controller
import test_dashboard

ORIGINAL_SHA256='662e41b5b4b8a03922446dc4fbe731a2ea52676f9670a9d6fabd3b03885aabcb'

class Studio(unittest.TestCase):
    setUp=test_dashboard.Tests.setUp;tearDown=test_dashboard.Tests.tearDown;request=test_dashboard.Tests.request;login=test_dashboard.Tests.login
    def test_original_document_is_exact_and_old_interface_is_not_loaded(self):
        self.assertEqual(hashlib.sha256((WEB/'darshanflow.html').read_bytes()).hexdigest(),ORIGINAL_SHA256)
        self.assertEqual(self.request('/darshanflow.html')[0],401)
        self.login();status,body,_=self.request('/darshanflow.html');self.assertEqual(status,200)
        self.assertEqual(hashlib.sha256(body).hexdigest(),ORIGINAL_SHA256)
        shell=self.request('/')[1].decode()
        self.assertIn('darshanflow-frame',shell);self.assertIn('/darshanflow-host.js',shell)
        for asset in ('/social.js','/social-batch.js','/social-arrange.js','/social.css'):
            self.assertNotIn(asset,shell);self.assertEqual(self.request(asset)[0],404)
        for asset in ('/darshanflow-host.js','/darshanflow-host.css','/darshanflow-theme.css','/darshanflow-studio.js','/darshanflow-studio.css'):self.assertEqual(self.request(asset)[0],200)
    def test_viewer_cannot_load_studio_and_inline_policy_is_scoped(self):
        self.login()
        def policy(path):
            conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
            conn.request('GET',path,headers={'Host':self.host,'Cookie':self.cookie})
            response=conn.getresponse();result=response.getheader('Content-Security-Policy');response.read();conn.close();return result
        self.assertIn("script-src 'unsafe-inline'",policy('/darshanflow.html'))
        self.assertIn("connect-src 'self'",policy('/darshanflow.html'))
        self.assertIn("frame-ancestors 'self'",policy('/darshanflow.html'))
        self.assertNotIn('unsafe-inline',policy('/'))
        with self.server.auth_lock:self.server.sessions[self.cookie.split('=',1)[1]]['role']='viewer'
        self.assertEqual(self.request('/darshanflow.html')[0],403)
    def test_previous_posting_queue_is_paused_but_its_records_remain(self):
        old=self.c.social
        old.data.update(enabled=True,jobs=[{'id':'retained-draft','status':'queued','title':'Retained draft'}])
        old.persist();before=old.data['jobs'].copy()
        replacement=Controller(self.c.base,test_dashboard.Service,self.vault)
        try:
            self.assertFalse(replacement.social.data['enabled']);self.assertEqual(replacement.social.data['jobs'],before)
            persisted=json.loads(old.path.read_text());self.assertFalse(persisted['enabled']);self.assertEqual(persisted['jobs'],before)
        finally:replacement.shutdown()
