import copy,json,tempfile,threading,unittest
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import Mock,patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import atomic_json, SLOTS,IST,Journal,Scheduler
from schedule_config import get_schedule,validate_schedule
from connections import Services,SetupError,Camera
from dashboard import Controller
from test_dashboard import Vault,Service
from test_scheduler import Fake

class FullFake(Fake):
    def __init__(self):super().__init__();self.ends=[];self.actions=[]
    def start(self,record):
        self.persist_run(obs_start_epoch=1234)
        super().start(record)
    def camera_action(self,action):self.actions.append(action['kind']);self.patrols+=action['kind']=='patrol_start'
    def end(self,record,persist):
        self.ends.append(record['yt_id'])
        if self.fail=='end':raise RuntimeError('Ambiguous end')
        self.active=False

class Scheduling(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.j=Journal(Path(self.tmp.name)/'journal.json');self.f=FullFake();self.slots=get_schedule({});self.slot=self.slots[0]
        self.now=datetime(2026,9,22,4,30,tzinfo=IST);self.logs=[]
    def tearDown(self):self.tmp.cleanup()
    def scheduler(self,grace=120):return Scheduler(self.f,self.j,self.logs.append,clock=lambda:self.now,slots=self.slots,grace_seconds=grace)
    def tick(self,s,delta=0):self.now+=timedelta(seconds=delta);s.tick(self.now)
    def test_custom_start_and_exactly_one_end(self):
        self.slot['at']='04:40';self.slot['end_at']='04:50';s=self.scheduler()
        self.tick(s);self.assertEqual(self.f.started,0)
        self.tick(s,600);self.assertEqual(self.f.started,1)
        self.tick(s,599);self.assertEqual(self.f.ends,[])
        self.tick(s,1);self.tick(s,1);self.assertEqual(self.f.ends,['yt']);self.assertEqual(self.j.get(self.slot,self.now.date())['phase'],'ended')
    def test_overnight_run_ends_after_restart(self):
        for slot in self.slots:slot['enabled']=slot is self.slot
        self.slot.update(at='23:55',end_at='00:10',end_next_day=True);self.now=self.now.replace(hour=23,minute=55)
        self.tick(self.scheduler());self.now+=timedelta(minutes=15)
        self.tick(self.scheduler());self.assertEqual(self.f.ends,['yt']);self.assertEqual(self.f.started,1)
    def test_prepare_before_midnight(self):
        for slot in self.slots:slot['enabled']=slot is self.slot
        self.slot['at']='00:02';self.now=self.now.replace(hour=23,minute=57)
        self.tick(self.scheduler());self.assertEqual(self.f.prepared,1);self.assertEqual(self.f.started,0)
        self.assertTrue(self.j.get(self.slot,self.now.date()+timedelta(days=1)))
    def test_fixed_clock_before_live_and_delayed_camera(self):
        self.slot['camera_actions']=[dict(kind='preset',number=2,timing='clock',at='04:20',next_day=False,only_if_live=False,delay_seconds=0),dict(kind='patrol_start',number=8,timing='after_live',delay_seconds=30,at='',next_day=False,only_if_live=True)]
        self.now=self.now.replace(minute=20);s=self.scheduler();self.tick(s);self.assertEqual(self.f.actions,['preset']);self.assertEqual(self.f.started,0)
        self.tick(s,600);self.tick(s,29);self.assertEqual(self.f.actions,['preset'])
        self.tick(s,1);self.tick(s,1);self.assertEqual(self.f.actions,['preset','patrol_start'])
    def test_patrol_stop_at_end_runs_before_end(self):
        self.slot['end_at']='04:35';self.slot['camera_actions']=[dict(kind='patrol_stop',number=8,timing='clock',at='04:35',next_day=False,only_if_live=True,delay_seconds=0)]
        s=self.scheduler();self.tick(s);self.tick(s,300);self.assertEqual(self.f.actions,['patrol_stop']);self.assertEqual(self.f.ends,['yt'])
    def test_failed_camera_does_not_cancel_authorized_end(self):
        self.slot['end_at']='04:35';self.f.camera_action=Mock(side_effect=RuntimeError('camera failed'))
        s=self.scheduler();self.tick(s);self.tick(s,120);self.tick(s,180);self.assertEqual(self.f.ends,['yt'])
    def test_end_without_app_start_is_skipped(self):
        self.slot['end_at']='04:35';self.now=self.now.replace(minute=35);self.tick(self.scheduler())
        self.assertEqual(self.f.ends,[]);self.assertEqual(self.j.get(self.slot,self.now.date())['end_state'],'not_started')
    def test_late_end_not_replayed(self):
        self.slot['end_at']='04:35';s=self.scheduler();self.tick(s);self.tick(s,481)
        self.assertEqual(self.f.ends,[]);self.assertEqual(self.j.get(self.slot,self.now.date())['end_state'],'missed')
    def test_ambiguous_end_not_retried(self):
        self.slot['end_at']='04:35';self.f.fail='end';s=self.scheduler();self.tick(s);self.tick(s,300);self.tick(s,1)
        self.assertEqual(self.f.ends,['yt']);self.assertEqual(self.j.get(self.slot,self.now.date())['end_state'],'needs_review')
    def test_pause_prevents_camera_and_end(self):
        self.slot['end_at']='04:35';s=self.scheduler();self.tick(s);s.cancelled=lambda:True;self.tick(s,300)
        self.assertEqual(self.f.ends,[]);self.assertEqual(self.f.actions,[])
    def test_plan_stays_frozen(self):
        self.slot['end_at']='04:35';s=self.scheduler();self.tick(s);self.slot['end_at']='05:00';self.tick(s,300);self.assertEqual(self.f.ends,['yt'])
    def test_new_end_not_added_to_legacy_journal(self):
        self.slot['end_at']='04:35';self.j.put(self.slot,self.now.date(),phase='live',yt_id='yt',fb_id='fb',patrol_due=(self.now+timedelta(seconds=120)).isoformat())
        s=self.scheduler();self.tick(s);self.tick(s,300);self.assertEqual(self.f.ends,[]);self.assertEqual(self.j.get(self.slot,self.now.date())['plan']['end_at'],'')
    def test_configurable_late_start_allowance(self):
        self.now+=timedelta(minutes=3);self.tick(self.scheduler(grace=300));self.assertEqual(self.f.started,1)
    def test_disabled_program_does_not_run(self):
        self.slot['enabled']=False;self.tick(self.scheduler());self.assertEqual(self.f.started,0)

class Validation(unittest.TestCase):
    def test_invalid_time_overlap_and_special_preset_rejected(self):
        for mutation in [lambda s:s[0].update(at='25:00'),lambda s:s[0].update(end_at='04:20'),lambda s:s[0].update(end_at='07:29'),lambda s:s[0]['camera_actions'][0].update(kind='preset',number=94)]:
            schedule=get_schedule({});mutation(schedule)
            with self.assertRaises(ValueError):validate_schedule(schedule)
    def test_default_preserves_manual_end(self):self.assertTrue(all(s['end_at']=='' for s in get_schedule({})))
    def test_camera_adapter_rejects_service_preset(self):
        c=Camera({},Vault());c.request=Mock()
        with self.assertRaises(SetupError):c.action({'kind':'preset','number':94})
        c.request.assert_not_called()
    def test_restarted_obs_cannot_be_stopped(self):
        with patch('connections.time.time',return_value=1000):
            Services.check_output_epoch({'outputActive':True,'outputDuration':100000},900)
            with self.assertRaises(SetupError):Services.check_output_epoch({'outputActive':True,'outputDuration':5000},900)
            with self.assertRaises(SetupError):Services.check_output_epoch({'outputActive':True},900)
    def test_end_without_explicit_plan_is_refused(self):
        s=Services({},Vault());s.fb=Mock();s.yt=Mock()
        with self.assertRaises(SetupError):s.end({'plan':{'end_at':''}},lambda **kw:None)
        s.fb.identity.assert_not_called();s.yt.owned_channel.assert_not_called()
    def test_preflight_failure_keeps_enabled_intent_until_pause(self):
        class Broken(Service):
            failed=threading.Event()
            def check(self):self.failed.set();raise SetupError('Network unavailable')
        with tempfile.TemporaryDirectory() as d:
            atomic_json(Path(d)/'settings.json',{});c=Controller(d,Broken,Vault());c.run('arm');self.assertTrue(Broken.failed.wait(2))
            with c.lock:self.assertTrue(c.cfg['armed'])
            c.pause();c.worker.join(3);self.assertFalse(c.cfg['armed']);self.assertFalse(c.armed)
    def test_diagnostics_retains_date_and_does_not_export_secrets(self):
        with tempfile.TemporaryDirectory() as d:
            v=Vault();c=Controller(d,Service,v);c.log('Test event '+v.get('facebook_page_token'));report=c.diagnostics()
            self.assertIn('app_started_at',report);self.assertIn('Test event',json.dumps(report))
            for secret in v.values.values():self.assertNotIn(secret,json.dumps(report))
            self.assertIn('20',c.logs[-1]['time'][:2])


class TargetedEnding(unittest.TestCase):
    def setup_service(self,fail_fb=False):
        s=Services({},Vault());s.obs=Mock();s.yt=Mock();s.fb=Mock();state={'yt':'live','fb':'LIVE','main':True,'output':True};calls=[]
        record={'plan':{'end_at':'05:00'},'yt_id':'recorded-yt','fb_id':'recorded-fb','yt_stream_id':'recorded-stream','fb_output_name':'multi-output-owned','obs_start_epoch':900}
        s.yt.event.side_effect=lambda _:{'status':{'lifeCycleStatus':state['yt']},'contentDetails':{'boundStreamId':'recorded-stream'}}
        s.yt.live.side_effect=lambda _:state['yt']=='live';s.fb.live.side_effect=lambda _:state['fb']=='LIVE';s.fb.recent.return_value=[{'id':'recorded-fb'}]
        def yt_api(method,path,params):calls.append(('yt',method,path,params));state['yt']='complete'
        def fb_api(method,path,params):
            calls.append(('fb',method,path,params))
            if method=='POST':
                if fail_fb:raise SetupError('Facebook end denied')
                state['fb']='VOD'
            return {'status':state['fb']}
        def obs_call(kind,**kw):
            calls.append(('obs',kind,kw))
            if kind=='GetStreamStatus':return {'outputActive':state['main'],'outputDuration':100000}
            if kind=='GetOutputStatus':return {'outputActive':state['output']}
            if kind=='StopOutput':state['output']=False
            if kind=='StopStream':state['main']=False
            if kind=='GetOutputList':return {'outputs':[{'outputName':'multi-output-owned','outputActive':state['output']}]}
            return {}
        s.yt.api.side_effect=yt_api;s.fb.api.side_effect=fb_api;s.obs.call.side_effect=obs_call;s.verify_run_outputs=Mock(return_value=({'outputActive':True},{'outputName':'multi-output-owned'}))
        return s,record,calls
    def test_exact_ids_and_exact_output_only(self):
        s,record,calls=self.setup_service();persist=Mock()
        with patch('connections.time.time',return_value=1000):s.end(record,persist)
        self.assertIn(('yt','POST','liveBroadcasts/transition',{'id':'recorded-yt','broadcastStatus':'complete','part':'id,status'}),calls)
        self.assertIn(('fb','POST','recorded-fb',{'end_live_video':'true'}),calls)
        self.assertIn(('obs','StopOutput',{'outputName':'multi-output-owned'}),calls)
        self.assertIn(('obs','StopStream',{}),calls)
        s.yt.no_other_live.assert_called_once_with('recorded-yt');s.fb.no_other_live.assert_called_once_with('recorded-fb')
    def test_partial_platform_end_leaves_obs_for_manual_review(self):
        s,record,calls=self.setup_service(fail_fb=True)
        with self.assertRaises(SetupError):s.end(record,Mock())
        self.assertFalse(any(c[0]=='obs' and c[1].startswith('Stop') for c in calls))
    def test_changed_binding_refuses_all_end_writes(self):
        s,record,calls=self.setup_service();s.yt.event.side_effect=None;s.yt.event.return_value={'contentDetails':{'boundStreamId':'someone-else'}}
        with self.assertRaises(SetupError):s.end(record,Mock())
        self.assertFalse(calls)

if __name__=='__main__':unittest.main()
