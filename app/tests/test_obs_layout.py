import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import obs_layout as layout
from core import atomic_json

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.folder=Path(self.tmp.name)
        self.p=patch.object(layout,'directory',return_value=self.folder);self.p.start()
    def tearDown(self):self.p.stop();self.tmp.cleanup()
    def reply(self,path,value):
        atomic_json(path,value)
        atomic_json(self.folder/'response.json',{'id':value['id'],'protocol':1,'ok':True,'token':value['id']})
    def test_capture_matches_fresh_nonce_and_cleans_request(self):
        with patch.object(layout,'atomic_json',side_effect=self.reply):token=layout.capture()
        self.assertRegex(token,r'^[a-f0-9]{32}$')
        self.assertFalse((self.folder/'request.json').exists())
    def test_stale_reply_cannot_authorize_reload_and_request_expires(self):
        def stale(path,value):
            atomic_json(path,value);atomic_json(self.folder/'response.json',{'id':'old','protocol':1,'ok':True})
        with patch.object(layout,'atomic_json',side_effect=stale),patch.object(layout.time,'monotonic',side_effect=[0,1,5]),patch.object(layout.time,'sleep'):
            with self.assertRaisesRegex(layout.LayoutError,'Set up OBS layout protection'):layout.capture()
        self.assertFalse((self.folder/'request.json').exists())
    def test_unconfirmed_restore_is_blocking(self):
        def fail(path,value):
            atomic_json(path,value);atomic_json(self.folder/'response.json',{'id':value['id'],'protocol':1,'ok':False})
        with patch.object(layout,'atomic_json',side_effect=fail):
            with self.assertRaisesRegex(layout.LayoutError,'No new live'):layout.restore('known')
    def test_capture_requires_snapshot_token_to_match_request(self):
        def wrong(path,value):
            atomic_json(path,value);atomic_json(self.folder/'response.json',{'id':value['id'],'protocol':1,'ok':True,'token':'old'})
        with patch.object(layout,'atomic_json',side_effect=wrong):
            with self.assertRaisesRegex(layout.LayoutError,'capture was not confirmed'):layout.capture()
    def test_no_arbitrary_action_is_written(self):
        with self.assertRaises(ValueError):layout.request('start-stream')
        self.assertFalse(list(self.folder.iterdir()))

if __name__=='__main__':unittest.main()
