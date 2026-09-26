import sys,os,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from connections import OBS,SetupError

class FakeOBS(OBS):
    def __init__(self,cfg):
        super().__init__(cfg,None);self.current=cfg['obs_profile'];self.active=False;self.calls=[]
    def idle(self):
        if self.active:raise SetupError('Active')
    def check_profile(self):
        if self.current!=self.cfg['obs_profile']:raise SetupError('Wrong profile')
    def call(self,kind,**data):
        self.calls.append((kind,data))
        if kind in ('CreateProfile','SetCurrentProfile'):self.current=data['profileName']
        return {}

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'APPDATA':self.tmp.name});self.env.start()
        self.folder=Path(self.tmp.name)/'obs-studio/basic/profiles/Untitled';self.folder.mkdir(parents=True)
        (self.folder/'basic.ini').write_text('[General]\nName=Untitled\n')
        self.path=self.folder/'obs-multi-rtmp.json'
        self.source={'targets':[{'id':'f','name':'FB Live','service-param':{'server':'old','key':'oldkey'},'sync-start':False,'sync-stop':True,'video-config':'v'}, {'id':'b','name':'FB Backup','service-param':{'key':'backupkey'},'sync-start':False}], 'video_configs':[{'id':'v','encoder':'shared'}]}
        self.path.write_text(json.dumps(self.source))
        self.obs=FakeOBS({'obs_profile':'Untitled','fb_target':'FB Live'})
    def tearDown(self):self.env.stop();self.tmp.cleanup()
    def test_only_chosen_target_changes_and_backup_preserved(self):
        raw=self.path.read_bytes()
        with patch('connections.time.sleep'):self.obs.prepare_fb_output('rtmps://live-api-s.facebook.com:443/rtmp/example-key?x=1')
        result=json.loads(self.path.read_text())
        self.assertEqual(result['targets'][1],self.source['targets'][1])
        self.assertEqual(result['video_configs'],self.source['video_configs'])
        self.assertEqual(result['targets'][0]['service-param']['key'],'example-key?x=1')
        self.assertTrue(result['targets'][0]['sync-start'])
        self.assertTrue(result['targets'][0]['sync-stop'])
        self.assertEqual(self.obs.current,'Untitled')
        backups=list(self.folder.glob('obs-multi-rtmp.before-iskcon-*.json'))
        self.assertEqual(len(backups),1);self.assertEqual(backups[0].read_bytes(),raw)
    def test_active_output_prevents_mutation(self):
        raw=self.path.read_bytes();self.obs.active=True
        with self.assertRaises(SetupError):self.obs.prepare_fb_output('rtmps://live-api-s.facebook.com/rtmp/key')
        self.assertEqual(self.path.read_bytes(),raw);self.assertFalse(self.obs.calls)
    def test_another_auto_start_target_blocks(self):
        self.source['targets'][1]['sync-start']=True;self.path.write_text(json.dumps(self.source));raw=self.path.read_bytes()
        with self.assertRaises(SetupError):self.obs.prepare_fb_output('rtmps://live-api-s.facebook.com/rtmp/key')
        self.assertEqual(self.path.read_bytes(),raw);self.assertFalse(self.obs.calls)
    def test_bad_ingest_url_prevents_mutation(self):
        raw=self.path.read_bytes()
        with self.assertRaises(SetupError):self.obs.prepare_fb_output('https://example.com/key')
        self.assertEqual(self.path.read_bytes(),raw)

if __name__=='__main__':unittest.main()
