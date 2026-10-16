"""Existing live attachment never creates/starts a broadcast; fakes only."""
import copy, json, tempfile, unittest, sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import IST, Journal, Scheduler, atomic_json
from connections import Services, SetupError
from dashboard import Controller
from schedule_config import get_schedule
from takeover import discover, attach_record, preview, same_live, select_plan, require_unused, digest
import test_dashboard
from test_dashboard import Vault, Handler

NOW=datetime(2026,10,15,4,36,tzinfo=IST)

def fixture():
    s=Services({},Vault());s.obs=Mock();s.yt=Mock();s.fb=Mock();s.cam=Mock()
    s.yt.owned_channel.return_value={'id':'channel'};s.fb.identity.return_value={'id':'page'}
    s.yt.stream_for_obs.return_value={'id':'official'}
    s.yt.list.return_value=[{'id':'abcdefghijk','snippet':{'channelId':'channel','title':'Mangal live','actualStartTime':NOW.replace(minute=30).isoformat()},'status':{'lifeCycleStatus':'live'},'contentDetails':{'boundStreamId':'official'}}]
    s.yt.event.return_value=copy.deepcopy(s.yt.list.return_value[0])
    s.fb.recent.return_value=[{'id':'123456789','status':'LIVE'}]
    s.fb.api.return_value={'id':'123456789','status':'LIVE','title':'Mangal FB','secure_stream_url':'rtmps://live-api-s.facebook.com:443/rtmp/private-key','broadcast_start_time':NOW.replace(minute=30).isoformat()}
    s.obs.plugin_target.return_value=(None,None,{'service-param':{'server':'rtmps://live-api-s.facebook.com:443/rtmp/','key':'private-key'}})
    def call(kind,**kw):
        if kind=='GetOutputList':return {'outputs':[{'outputName':'multi-output-owned','outputActive':True}]}
        if kind in ('GetStreamStatus','GetOutputStatus'):return {'outputActive':True,'outputDuration':360000}
        raise AssertionError('Unexpected OBS request '+kind)
    s.obs.call.side_effect=call;s.verify_run_outputs=Mock(return_value=({'outputActive':True},{'outputActive':True}))
    s.both_live=Mock(return_value=True)
    return s

def plan():
    slot=get_schedule({})[0];slot['end_at']='05:25'
    slot['camera_actions'] += [dict(kind='preset',number=2,timing='clock',at='04:40',next_day=False,only_if_live=True,delay_seconds=0)]
    return slot

class Discovery(unittest.TestCase):
    def test_read_only_matches_existing_official_key_and_no_secret_in_record(self):
        s=fixture()
        with patch('time.time',return_value=NOW.timestamp()):r=discover(s,NOW)
        self.assertEqual(r['confirmed_at'],NOW.replace(minute=30).isoformat());self.assertEqual(r['obs_start_epoch'],NOW.timestamp()-360)
        self.assertNotIn('private-key',json.dumps(r));self.assertTrue(all(c.args[0]=='GET' for c in s.fb.api.call_args_list))
        s.yt.api.assert_not_called();s.obs.start.assert_not_called();s.obs.connect.assert_called_once_with(launch=False)
    def test_wrong_channel_binding_missing_platform_and_duplicate_are_refused(self):
        for mutate in [lambda s:s.yt.list.return_value[0]['snippet'].update(channelId='other'),lambda s:s.yt.list.return_value[0]['contentDetails'].update(boundStreamId='other'),lambda s:s.yt.list.return_value.append(copy.deepcopy(s.yt.list.return_value[0])),lambda s:setattr(s.fb.recent,'return_value',[]),lambda s:s.fb.api.return_value.update(secure_stream_url='rtmps://elsewhere/rtmp/wrong')]:
            with self.subTest(mutate=mutate):
                s=fixture();mutate(s)
                with self.assertRaises(ValueError):discover(s,NOW)
                s.yt.api.assert_not_called();s.obs.start.assert_not_called()
    def test_missing_actual_start_and_unstable_outputs_are_refused(self):
        s=fixture();s.fb.api.return_value.pop('broadcast_start_time')
        with self.assertRaises(ValueError):discover(s,NOW)
        s=fixture();old=s.obs.call.side_effect
        s.obs.call.side_effect=lambda kind,**kw:{'outputActive':True,'outputDuration':360000,'outputReconnecting':True} if kind=='GetStreamStatus' else old(kind,**kw)
        with self.assertRaises(ValueError):discover(s,NOW)
    def test_live_or_output_changes_after_preview_are_not_the_same_run(self):
        r=discover(fixture(),NOW)
        for field,value in [('yt_id','other'),('fb_id','other'),('fb_output_name','other'),('title','Changed'),('obs_start_epoch',r['obs_start_epoch']+5)]:
            after={**r,field:value};self.assertFalse(same_live(r,after))
        self.assertTrue(same_live(r,{**r,'obs_start_epoch':r['obs_start_epoch']+.5}))

class Management(unittest.TestCase):
    def test_only_future_camera_and_exact_saved_end_after_restart(self):
        with tempfile.TemporaryDirectory() as d:
            slot=plan();j=Journal(Path(d)/'journal.json');rec=attach_record(slot,NOW.date(),discover(fixture(),NOW),NOW)
            self.assertEqual(rec['camera_states'],{'0':'skipped_before_takeover'})
            j.put(slot,NOW.date(),**rec);s=Mock();s.takeover_live.return_value=True;s.both_live.return_value=True
            clock=NOW
            def scheduler():return Scheduler(s,Journal(j.path),log=lambda _:None,clock=lambda:clock,slots=[slot])
            scheduler().run_slot(slot,NOW.date(),clock);s.camera_action.assert_not_called()
            clock=NOW.replace(minute=40);scheduler().run_slot(slot,NOW.date(),clock);scheduler().run_slot(slot,NOW.date(),clock)
            self.assertEqual(s.camera_action.call_count,1);self.assertEqual(s.camera_action.call_args.args[0]['number'],2)
            clock=NOW.replace(hour=5,minute=25);scheduler().run_slot(slot,NOW.date(),clock);scheduler().run_slot(slot,NOW.date(),clock)
            s.end.assert_called_once();s.start.assert_not_called();s.prepare.assert_not_called()
    def test_wrong_or_restarted_output_never_moves_camera(self):
        with tempfile.TemporaryDirectory() as d:
            slot=plan();j=Journal(Path(d)/'j.json');j.put(slot,NOW.date(),**attach_record(slot,NOW.date(),discover(fixture(),NOW),NOW))
            s=Mock();s.takeover_live.side_effect=SetupError('Output changed')
            clock=NOW.replace(minute=40);Scheduler(s,j,log=lambda _:None,clock=lambda:clock,slots=[slot]).run_slot(slot,NOW.date(),clock)
            s.camera_action.assert_not_called();self.assertEqual(j.get(slot,NOW.date())['camera_states']['1'],'needs_review')
    def test_pause_does_not_move_or_end(self):
        with tempfile.TemporaryDirectory() as d:
            slot=plan();j=Journal(Path(d)/'j.json');j.put(slot,NOW.date(),**attach_record(slot,NOW.date(),discover(fixture(),NOW),NOW))
            s=Mock();clock=NOW.replace(hour=5,minute=25)
            Scheduler(s,j,log=lambda _:None,clock=lambda:clock,slots=[slot],cancelled=lambda:True).tick(clock)
            s.end.assert_not_called();s.camera_action.assert_not_called()
    def test_pause_during_verification_prevents_camera_write(self):
        with tempfile.TemporaryDirectory() as d:
            slot=plan();j=Journal(Path(d)/'j.json');j.put(slot,NOW.date(),**attach_record(slot,NOW.date(),discover(fixture(),NOW),NOW))
            stopped=[False];s=Mock();s.both_live.return_value=True
            def read(record):stopped[0]=True;return True
            s.takeover_live.side_effect=read;clock=NOW.replace(minute=40)
            Scheduler(s,j,log=lambda _:None,clock=lambda:clock,slots=[slot],cancelled=lambda:stopped[0]).run_slot(slot,NOW.date(),clock)
            s.camera_action.assert_not_called();s.end.assert_not_called()
    def test_program_window_overnight_and_duplicate_journal(self):
        slot=plan()
        select_plan([slot],slot['id'],'2026-10-15',NOW)
        for now in [NOW.replace(hour=4,minute=29),NOW.replace(hour=5,minute=25)]:
            with self.assertRaises(ValueError):select_plan([slot],slot['id'],'2026-10-15',now)
        night={**slot,'at':'23:00','end_at':'01:00','end_next_day':True}
        select_plan([night],night['id'],'2026-10-14',NOW.replace(hour=0,minute=30))
        with tempfile.TemporaryDirectory() as d:
            j=Journal(Path(d)/'j.json');j.put(slot,NOW.date(),phase='needs_review',yt_id='abcdefghijk')
            require_unused(j,slot,NOW.date())
            candidate=discover(fixture(),NOW);require_unused(j,slot,NOW.date(),candidate)
            with self.assertRaises(ValueError):require_unused(j,slot,NOW.date(),{**candidate,'yt_id':'other-live'})
            j.put(slot,NOW.date(),obs_start_epoch=1)
            with self.assertRaises(ValueError):require_unused(j,slot,NOW.date())

class ControllerFlow(unittest.TestCase):
    def test_preview_cancel_recheck_attach_pause_and_secret_free_state(self):
        services=[]
        def factory(*args):
            s=fixture();services.append(s);return s
        with tempfile.TemporaryDirectory() as d:
            c=Controller(d,factory,Vault());c.cfg['schedule']=[plan()]
            with patch('dashboard.now_ist',return_value=NOW),patch('core.now_ist',return_value=NOW):
                c.take_control({'action':'inspect','slot':'mangal','date':'2026-10-15'});c.worker.join(3)
                self.assertEqual(c.takeover_state['status'],'ready');self.assertFalse((c.base/'journal.json').exists())
                self.assertNotIn('private-key',json.dumps(c.snapshot(True)));token=c.takeover_state['token']
                with self.assertRaises(ValueError):c.take_control({'action':'confirm','slot':'mangal','date':'2026-10-15','token':token})
                c.take_control({'action':'confirm','slot':'mangal','date':'2026-10-15','token':token,'confirmed':True})
                import time
                for _ in range(100):
                    if c.armed:break
                    time.sleep(.01)
                self.assertTrue(c.armed);c.pause();c.worker.join(3)
            rec=Journal(c.base/'journal.json').get(plan(),NOW.date());self.assertEqual(rec['origin'],'manual_takeover');self.assertEqual(rec['phase'],'live')
            for s in services:s.obs.start.assert_not_called();s.yt.api.assert_not_called();s.cam.action.assert_not_called()
    def test_expired_and_changed_schedule_preview_cannot_attach(self):
        with tempfile.TemporaryDirectory() as d:
            c=Controller(d,lambda *args:fixture(),Vault());c.cfg['schedule']=[plan()]
            with patch('dashboard.now_ist',return_value=NOW),patch('core.now_ist',return_value=NOW):
                c.take_control({'action':'inspect','slot':'mangal','date':'2026-10-15'});c.worker.join(3)
                token=c.takeover_state['token'];c.cfg['schedule'][0]['end_at']='05:20'
                with self.assertRaises(ValueError):c.take_control({'action':'confirm','slot':'mangal','date':'2026-10-15','token':token,'confirmed':True})
                c.cfg['schedule'][0]['end_at']='05:25';c.takeover_preview['expires']=0
                with self.assertRaises(ValueError):c.take_control({'action':'confirm','slot':'mangal','date':'2026-10-15','token':token,'confirmed':True})
            self.assertFalse((c.base/'journal.json').exists())

class Boundaries(unittest.TestCase):
    setUp=test_dashboard.Tests.setUp;tearDown=test_dashboard.Tests.tearDown;request=test_dashboard.Tests.request;login=test_dashboard.Tests.login
    def test_takeover_requires_auth_csrf_operator_and_explicit_confirmation(self):
        payload={'action':'confirm','slot':'mangal','date':NOW.date().isoformat()}
        self.assertEqual(self.request('/api/takeover',payload)[0],401);self.login()
        self.assertEqual(self.request('/api/takeover',payload,**{'X-CSRF-Token':'wrong'})[0],403)
        with self.server.auth_lock:self.server.sessions[self.cookie.split('=',1)[1]]['role']='viewer'
        self.assertEqual(self.request('/api/takeover',payload)[0],403)
        with self.server.auth_lock:self.server.sessions[self.cookie.split('=',1)[1]]['role']='owner'
        with patch('dashboard.now_ist',return_value=NOW),patch('core.now_ist',return_value=NOW):self.assertEqual(self.request('/api/takeover',payload)[0],409)
        self.assertFalse((self.c.base/'journal.json').exists())
