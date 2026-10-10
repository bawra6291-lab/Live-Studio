"""Product foundation: real settings/journal boundaries, mocked external destinations."""
import copy, json, sys, tempfile, unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from config import DEFAULTS
from workspace import load_settings
from dashboard import Controller
from core import Journal, Scheduler, IST, atomic_json, now_ist, title_for
from schedule_config import get_schedule, validate_schedule
from connections import YouTube, Facebook, Camera, SetupError, Vault
from test_dashboard import Vault as FakeVault, Service

CHANNEL='UC'+'a'*22
ROW=dict(id='weekly_service',name='Weekly Service',reference='abcdefghijk',title_template='{date} | {program}',at='12:00',enabled=True,end_at='',end_next_day=False,camera_actions=[])

class WorkspaceTests(unittest.TestCase):
    def test_fresh_workspace_has_no_iskcon_bindings_or_camera_actions(self):
        with tempfile.TemporaryDirectory() as d:
            c=Controller(d,Service,FakeVault());cfg=c.cfg
            self.assertEqual(get_schedule(cfg),[])
            self.assertFalse(cfg['armed']);self.assertFalse(cfg['legacy_setup'])
            for k in ('youtube_channel_id','facebook_page_id','youtube_stream_title','camera_url','obs_collection'):self.assertEqual(cfg[k],'')
            with self.assertRaisesRegex(ValueError,'at least one'):c.run('arm')
            self.assertTrue(all(not x['done'] for x in c.snapshot()['setup_steps']))
    def test_legacy_migration_preserves_settings_schedule_and_vault(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'settings.json';schedule=get_schedule({});schedule[0]['at']='04:45'
            original={'schedule':schedule,'armed':True,'obs_profile':'Operator','future_option':'retained'}
            atomic_json(path,original);before=path.read_bytes();cfg=load_settings(path)
            self.assertEqual(cfg['schedule'],schedule);self.assertEqual(cfg['obs_profile'],'Operator');self.assertTrue(cfg['armed'])
            self.assertEqual(cfg['credential_service'],'ISKCON-Live-Start');self.assertEqual(cfg['facebook_page_id'],'113962385367196')
            self.assertEqual(cfg['youtube_stream_title'],'YouTube Official Livestream')
            self.assertEqual(path.with_name('settings.before-workspace-migration.json').read_bytes(),before)
            self.assertEqual(load_settings(path),cfg)
    def test_fresh_namespaces_are_unique_and_stable(self):
        with tempfile.TemporaryDirectory() as a,tempfile.TemporaryDirectory() as b:
            one=load_settings(Path(a)/'settings.json');two=load_settings(Path(b)/'settings.json')
            self.assertNotEqual(one['credential_service'],two['credential_service'])
            self.assertEqual(one['credential_service'],load_settings(Path(a)/'settings.json')['credential_service'])
    def test_vault_never_falls_back_to_legacy_secrets(self):
        backend=type('Backend',(),{'__module__':'keyring.backends.Windows'})()
        fake=Mock();fake.get_keyring.return_value=backend;fake.get_password.return_value=None
        with patch.dict(sys.modules,{'keyring':fake}),patch('connections.os.name','nt'):
            vault=Vault('Live-Desk-'+'a'*32);self.assertEqual(vault.get('youtube_oauth'),'')
            fake.get_password.assert_called_once_with('Live-Desk-'+'a'*32,'youtube_oauth')
    def test_settings_cannot_switch_namespace_or_enable_legacy_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            c=Controller(d,Service,FakeVault());service=c.cfg['credential_service']
            c.save({'credential_service':'ISKCON-Live-Start','legacy_setup':True,'workspace_id':'changed'})
            self.assertEqual(c.cfg['credential_service'],service);self.assertFalse(c.cfg['legacy_setup'])
    def test_invalid_identity_save_does_not_change_settings_or_secret(self):
        with tempfile.TemporaryDirectory() as d:
            vault=FakeVault();c=Controller(d,Service,vault);before=c.path.read_bytes()
            with self.assertRaises(ValueError):c.save({'youtube_channel_id':'wrong','facebook_page_token':'replacement'})
            self.assertEqual(c.path.read_bytes(),before);self.assertEqual(vault.get('facebook_page_token'),'sensitive-page-token')
    def test_active_run_blocks_destination_changes_and_program_removal(self):
        with tempfile.TemporaryDirectory() as d:
            c=Controller(d,Service,FakeVault());c.save_schedule({'schedule':[ROW]})
            j=Journal(c.base/'journal.json');j.put(ROW,now_ist().date(),phase='live',yt_id='event',plan=ROW)
            with self.assertRaisesRegex(ValueError,'recent run'):c.save({'facebook_page_id':'123456789'})
            with self.assertRaisesRegex(ValueError,'recent run'):c.save_schedule({'schedule':[]})
            c.save({'workspace_name':'Renamed'})
            j.put(ROW,now_ist().date(),phase='ended',end_state='ended')
            c.save_schedule({'schedule':[]});self.assertEqual(get_schedule(c.cfg),[])
    def test_custom_schedule_and_title_persist(self):
        with tempfile.TemporaryDirectory() as d:
            c=Controller(d,Service,FakeVault());c.save_schedule({'schedule':[ROW]})
            out=Controller(d,Service,FakeVault()).snapshot()['schedule'][0]
            self.assertEqual(out,ROW)
            self.assertEqual(title_for('Any old reference title',out,datetime(2026,9,28).date()),'28th Sept 2026 | Weekly Service')
    def test_invalid_custom_programs(self):
        for values in ({'id':'../bad'},{'reference':'https://youtube.com/watch?v=secret'},{'name':''},{'title_template':'{account}'},{'title_template':'<script>'}):
            with self.subTest(values=values),self.assertRaises(ValueError):validate_schedule([{**ROW,**values}])
        with self.assertRaises(ValueError):validate_schedule([ROW]*25)
        self.assertEqual(validate_schedule([]),[])
        with self.assertRaisesRegex(ValueError,'different name'):validate_schedule([ROW,{**ROW,'id':'other','at':'15:00'}])
    def test_custom_journal_without_plan_never_gains_new_actions(self):
        with tempfile.TemporaryDirectory() as d:
            j=Journal(Path(d)/'journal.json');now=datetime(2026,9,28,12,0,tzinfo=IST)
            j.put(ROW,now.date(),phase='done',yt_id='existing')
            service=Mock();scheduler=Scheduler(service,j,log=Mock(),clock=lambda:now,slots=[ROW])
            scheduler.run_slot(ROW,now.date(),now)
            self.assertEqual(j.get(ROW,now.date())['phase'],'needs_review');self.assertEqual(service.mock_calls,[])

class DestinationTests(unittest.TestCase):
    def test_channel_binding_rejects_wrong_account_without_legacy_lookup(self):
        yt=YouTube({'youtube_channel_id':CHANNEL},None);yt.list=Mock(return_value=[{'id':'UC'+'b'*22}])
        with self.assertRaisesRegex(SetupError,'does not own'):yt.owned_channel()
        self.assertEqual(yt.list.call_count,1)
        yt.list.return_value=[{'id':CHANNEL,'snippet':{'title':'My Channel'}}];self.assertEqual(yt.owned_channel()['id'],CHANNEL)
    def test_fresh_account_cannot_use_iskcon_reference_fallback(self):
        yt=YouTube({},None);yt.list=Mock(return_value=[])
        with self.assertRaisesRegex(SetupError,'Save your YouTube channel ID'):yt.owned_channel()
        self.assertEqual(yt.list.call_count,1)
    def test_page_token_must_match_selected_page_and_missing_id_sends_no_request(self):
        fb=Facebook({'facebook_page_id':'123456789'},None);fb.api=Mock(return_value={'id':'113962385367196'})
        with self.assertRaisesRegex(SetupError,'does not match'):fb.identity()
        fb.api.return_value={'id':'123456789','name':'Selected'};self.assertEqual(fb.identity()['name'],'Selected')
        fb.cfg={};fb.api.reset_mock()
        with self.assertRaises(SetupError):fb.identity()
        fb.api.assert_not_called()
    def test_stream_reuses_exact_configured_key_without_write(self):
        yt=YouTube({'youtube_stream_title':'My existing key'},None)
        yt.list=Mock(return_value=[{'id':'stream','snippet':{'title':'My existing key'},'cdn':{'ingestionInfo':{'streamName':'private'}}}]);yt.api=Mock()
        self.assertEqual(yt.stream_for_obs('private')['id'],'stream');yt.api.assert_not_called()
        yt.cfg['youtube_stream_title']='Different'
        with self.assertRaises(SetupError):yt.stream_for_obs('private')
        yt.api.assert_not_called()
    def test_custom_template_uses_explicit_reference_and_preflights_before_write(self):
        yt=YouTube({'youtube_channel_id':CHANNEL},None)
        yt.owned_channel=Mock(return_value={'id':CHANNEL});yt.no_other_live=Mock()
        yt.stream_for_obs=Mock(return_value={'id':'stream'});yt.api=Mock()
        def listing(resource,**params):
            self.assertEqual(resource,'liveBroadcasts')
            if params.get('id')==ROW['reference']:
                return [{'id':ROW['reference'],'snippet':{'channelId':CHANNEL,'title':'An older unrelated title'},'status':{},'contentDetails':{}}]
            self.assertEqual(params.get('broadcastStatus'),'upcoming');return []
        yt.list=Mock(side_effect=listing);yt.video_template=Mock(side_effect=SetupError('preflight stop'))
        with self.assertRaisesRegex(SetupError,'preflight stop'):yt.prepare(ROW,datetime(2026,9,28,12,tzinfo=IST),'key',Mock())
        yt.video_template.assert_called_once_with(ROW['reference'],ROW['reference'],'28th Sept 2026 | Weekly Service',CHANNEL)
        yt.api.assert_not_called()
    def test_foreign_reference_blocks_before_stream_or_broadcast_write(self):
        yt=YouTube({},None);yt.owned_channel=Mock(return_value={'id':CHANNEL});yt.no_other_live=Mock()
        yt.list=Mock(return_value=[{'id':ROW['reference'],'snippet':{'channelId':'other','title':'Reference'}}])
        yt.api=Mock();yt.stream_for_obs=Mock()
        with self.assertRaisesRegex(SetupError,'another channel'):yt.prepare(ROW,datetime(2026,9,28,12,tzinfo=IST),'key',Mock())
        yt.api.assert_not_called();yt.stream_for_obs.assert_not_called()
    def test_camera_routes_selected_channel(self):
        import xml.etree.ElementTree as ET
        camera=Camera({'camera_channel':'2'},None);camera.request=Mock(return_value=ET.fromstring('<root><id>3</id></root>'))
        camera.action({'kind':'preset','number':3})
        self.assertEqual(camera.request.call_args_list[0].args,('GET','/ISAPI/PTZCtrl/channels/2/presets'))
        self.assertEqual(camera.request.call_args_list[1].args,('PUT','/ISAPI/PTZCtrl/channels/2/presets/3/goto'))

if __name__=='__main__':unittest.main()
