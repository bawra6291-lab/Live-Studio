import sys,os,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from connections import OBS,SetupError

class FakeOBS(OBS):
    def __init__(self,cfg):
        super().__init__(cfg,None);self.current=cfg['obs_profile'];self.active=False;self.calls=[]
        self.profiles=[self.current];self.pending=None;self.lag=0;self.fail_return=False
        self.layout_calls=[];self.layout_error=None
    def layout_request(self,action,token=''):
        self.layout_calls.append((action,token,self.current,len(self.calls)))
        if self.layout_error and action==self.layout_error:
            self.layout_error=None
            raise SetupError('Layout could not be confirmed.')
        return {'token':'captured-layout'}
    def idle(self):
        if self.active:raise SetupError('Active')
    def check_profile(self):
        if self.current!=self.cfg['obs_profile']:raise SetupError('Wrong profile')
    def call(self,kind,**data):
        self.calls.append((kind,data))
        if kind=='GetProfileList':
            if self.pending:
                if self.lag:self.lag-=1
                else:self.current=self.pending;self.profiles.append(self.pending);self.pending=None
            return {'currentProfileName':self.current,'profiles':list(self.profiles)}
        if kind=='CreateProfile':self.pending=data['profileName']
        if kind=='SetCurrentProfile':
            if data['profileName'] not in self.profiles:
                raise SetupError('OBS SetCurrentProfile failed (code 600).',request_type=kind,code=600)
            if self.fail_return and data['profileName']==self.cfg['obs_profile']:
                self.fail_return=False
                raise SetupError('OBS SetCurrentProfile failed (code 500).',request_type=kind,code=500)
            self.current=data['profileName']
        if kind=='RemoveProfile':self.profiles.remove(data['profileName'])
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
        self.assertEqual(self.obs.layout_calls[0],('capture','','Untitled',0))
        self.assertEqual(self.obs.layout_calls[-1][:3],('restore','captured-layout','Untitled'))
        self.assertEqual(self.obs.layout_calls[-1][3],len(self.obs.calls))
    def test_active_output_prevents_mutation(self):
        raw=self.path.read_bytes();self.obs.active=True
        with self.assertRaises(SetupError):self.obs.prepare_fb_output('rtmps://live-api-s.facebook.com/rtmp/key')
        self.assertEqual(self.path.read_bytes(),raw);self.assertFalse(self.obs.calls)
        self.assertFalse(self.obs.layout_calls)
    def test_async_create_is_polled_before_mutating_or_switching(self):
        self.obs.lag=3
        with patch('connections.time.sleep') as sleep:
            self.obs.prepare_fb_output('rtmps://live-api-s.facebook.com/rtmp/key')
        self.assertEqual(sleep.call_count,3)
        self.assertEqual(self.obs.current,'Untitled')
        self.assertEqual(self.obs.profiles,['Untitled'])
        switches=[data['profileName'] for kind,data in self.obs.calls if kind=='SetCurrentProfile']
        self.assertEqual(switches,['Untitled'])
    def test_create_timeout_keeps_original_file_and_names_failed_stage(self):
        raw=self.path.read_bytes();self.obs.lag=1000
        with patch('connections.time.sleep'),self.assertRaisesRegex(SetupError,'wait for temporary profile.*10 seconds') as err:
            self.obs.prepare_fb_output('rtmps://live-api-s.facebook.com/rtmp/private-key')
        self.assertEqual(self.path.read_bytes(),raw)
        self.assertEqual(self.obs.current,'Untitled')
        self.assertNotIn('private-key',str(err.exception))
    def test_missing_helper_blocks_before_switch_and_keeps_fb_key(self):
        raw=self.path.read_bytes();self.obs.layout_error='capture'
        with self.assertRaisesRegex(SetupError,'capture OBS layout.*Layout could not'):
            self.obs.prepare_fb_output('rtmps://live-api-s.facebook.com/rtmp/private-key')
        self.assertEqual(self.path.read_bytes(),raw)
        self.assertFalse(any(kind=='CreateProfile' for kind,_ in self.obs.calls))
    def test_failed_final_layout_restore_recovers_fb_backup_and_retries_layout(self):
        raw=self.path.read_bytes();self.obs.layout_error='restore'
        with self.assertRaisesRegex(SetupError,'restore OBS layout.*Original profile restored'):
            self.obs.prepare_fb_output('rtmps://live-api-s.facebook.com/rtmp/private-key')
        self.assertEqual(self.path.read_bytes(),raw)
        self.assertEqual(self.obs.current,'Untitled')
        self.assertEqual([a for a,_,_,_ in self.obs.layout_calls],['capture','restore','restore'])
    def test_switch_failure_restores_backup_and_preserves_actual_error(self):
        raw=self.path.read_bytes();self.obs.fail_return=True
        with patch('connections.time.sleep'),self.assertRaisesRegex(SetupError,'restore original profile.*code 500') as err:
            self.obs.prepare_fb_output('rtmps://live-api-s.facebook.com/rtmp/private-key')
        self.assertEqual(self.path.read_bytes(),raw)
        self.assertEqual(self.obs.current,'Untitled')
        self.assertIn('Original profile restored',str(err.exception))
        self.assertNotIn('private-key',str(err.exception))
    def test_file_error_does_not_disclose_exception_values(self):
        with patch('connections.time.sleep'),patch('connections.atomic_json',side_effect=OSError('private-key')):
            with self.assertRaisesRegex(SetupError,'write FB target: OSError') as err:
                self.obs.prepare_fb_output('rtmps://live-api-s.facebook.com/rtmp/private-key')
        self.assertNotIn('private-key',str(err.exception))
    def test_another_auto_start_target_blocks(self):
        self.source['targets'][1]['sync-start']=True;self.path.write_text(json.dumps(self.source));raw=self.path.read_bytes()
        with self.assertRaises(SetupError):self.obs.prepare_fb_output('rtmps://live-api-s.facebook.com/rtmp/key')
        self.assertEqual(self.path.read_bytes(),raw);self.assertFalse(self.obs.calls)
    def test_bad_ingest_url_prevents_mutation(self):
        raw=self.path.read_bytes()
        with self.assertRaises(SetupError):self.obs.prepare_fb_output('https://example.com/key')
        self.assertEqual(self.path.read_bytes(),raw)

if __name__=='__main__':unittest.main()
