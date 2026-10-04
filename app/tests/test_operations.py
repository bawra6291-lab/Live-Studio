"""Calendar, recovery, backup and device authorization regression gates."""
import copy,json,tempfile,time,unittest
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import Mock,patch
from core import IST,Journal,Scheduler,atomic_json
from schedule_config import get_schedule,validate_schedule,occurs_on,upcoming
from recovery import export_backup,import_backup,inspect_run
from dashboard import Controller,Handler
from connections import SetupError
import test_dashboard
from test_dashboard import Vault,Service
from test_scheduler import Fake

class Calendar(unittest.TestCase):
    def setUp(self):
        self.slot=get_schedule({})[0];self.slot['camera_actions']=[]
        self.now=datetime(2026,10,5,4,0,tzinfo=IST) # Monday
    def test_weekdays_and_exceptions(self):
        slot=validate_schedule([{**self.slot,'repeat':'weekdays','weekdays':[0,2],'skip_dates':['2026-10-05']}])[0]
        self.assertFalse(occurs_on(slot,self.now.date()))
        rows=upcoming([slot],self.now)
        self.assertEqual(rows[0]['due'],'2026-10-07T04:30:00+05:30')
    def test_one_date_runs_only_once(self):
        slot=validate_schedule([{**self.slot,'repeat':'once','on_date':'2026-10-05','prepare_minutes':20}])[0]
        rows=upcoming([slot],self.now)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['prepare_at'],'2026-10-05T04:10:00+05:30')
        with tempfile.TemporaryDirectory() as d:
            fake=Fake();journal=Journal(Path(d)/'journal.json');clock=self.now.replace(minute=10)
            scheduler=Scheduler(fake,journal,log=lambda _:None,clock=lambda:clock,slots=[slot])
            scheduler.tick(clock);self.assertEqual(fake.prepared,1)
            clock+=timedelta(days=1);scheduler.tick(clock);self.assertEqual(fake.prepared,1)
    def test_different_weekdays_can_share_time(self):
        other={**self.slot,'id':'other','name':'Other','title_template':'{date} | {program}','repeat':'weekdays','weekdays':[1]}
        validate_schedule([{**self.slot,'repeat':'weekdays','weekdays':[0]},other])
        other['weekdays']=[0]
        with self.assertRaises(ValueError):validate_schedule([{**self.slot,'repeat':'weekdays','weekdays':[0]},other])
    def test_far_future_oneoff_collision_checked(self):
        day='2040-01-02';other={**self.slot,'id':'other','name':'Other','title_template':'{program}','repeat':'once','on_date':day}
        with self.assertRaises(ValueError):validate_schedule([self.slot,other])
    def test_preparation_collision_and_invalid_fields(self):
        for fields in [{'repeat':'once','on_date':'2026-02-30'},{'repeat':'weekdays','weekdays':[True]},{'prepare_minutes':0},{'skip_dates':['bad']}]:
            with self.assertRaises(ValueError):validate_schedule([{**self.slot,**fields}])
        other={**self.slot,'id':'other','name':'Other','title_template':'{program}','at':'05:00','prepare_minutes':40}
        with self.assertRaises(ValueError):validate_schedule([self.slot,other])
    def test_reviewed_run_never_moves_or_restarts(self):
        with tempfile.TemporaryDirectory() as d:
            fake=Fake();j=Journal(Path(d)/'j.json');j.put(self.slot,self.now.date(),phase='reviewed',plan=self.slot)
            s=Scheduler(fake,j,clock=lambda:self.now,slots=[self.slot]);s.tick(self.now.replace(hour=5))
            self.assertEqual(fake.prepared,0);self.assertEqual(fake.started,0)

class Recovery(unittest.TestCase):
    def test_backup_cannot_export_secrets_or_import_code_paths(self):
        with tempfile.TemporaryDirectory() as d:
            c=Controller(d,Service,Vault());c.cfg['facebook_page_token']='secret';c.cfg['schedule']=get_schedule({})
            backup=c.backup();text=json.dumps(backup)
            self.assertNotIn('secret',text);self.assertNotIn('credential_service',text);self.assertNotIn('obs_exe',text)
            oldnamespace=c.cfg['credential_service'];c.restore({'backup':backup,'confirmed':True})
            self.assertEqual(c.cfg['credential_service'],oldnamespace);self.assertFalse(c.cfg['armed'])
            self.assertTrue((Path(d)/'settings.before-restore.json').exists())
            backup['settings']['obs_exe']='malicious.exe'
            with self.assertRaises(ValueError):c.restore({'backup':backup,'confirmed':True})
    def test_active_run_blocks_restore(self):
        with tempfile.TemporaryDirectory() as d:
            c=Controller(d,Service,Vault());s=get_schedule({})[0]
            from core import now_ist
            Journal(c.base/'journal.json').put(s,now_ist().date(),yt_id='abcdefghijk',phase='prepared')
            with self.assertRaises(ValueError):c.restore({'backup':c.backup(),'confirmed':True})
    def test_inspection_is_read_only_and_never_assumes_active_is_safe(self):
        service=Mock();service.obs.call.side_effect=lambda kind:{'outputActive':False} if kind=='GetStreamStatus' else {'outputs':[]}
        service.yt.event.return_value={'status':{'lifeCycleStatus':'live'}};service.fb.recent.return_value=[{'id':'12345'}]
        service.fb.api.return_value={'status':'LIVE'}
        result=inspect_run(service,{'yt_id':'abcdefghijk','fb_id':'12345'})
        self.assertFalse(result['can_review']);service.obs.connect.assert_called_once_with(launch=False)
        self.assertTrue(all(call.args[0]=='GET' for call in service.fb.api.call_args_list))
        service.yt.event.return_value={'status':{'lifeCycleStatus':'complete'}};service.fb.api.return_value={'status':'VOD'}
        self.assertTrue(inspect_run(service,{'yt_id':'abcdefghijk','fb_id':'12345'})['can_review'])
        service.obs.call.side_effect=lambda kind:{'outputActive':False} if kind=='GetStreamStatus' else {'outputs':[{'outputActive':True}]}
        self.assertFalse(inspect_run(service,{})['can_review'])
    def test_auth_failure_does_not_retry_forever(self):
        class Expired(Service):
            attempts=0
            def check(self):type(self).attempts+=1;raise SetupError('Token expired',retryable=False)
        with tempfile.TemporaryDirectory() as d:
            atomic_json(Path(d)/'settings.json',{});c=Controller(d,Expired,Vault());c.run('arm');c.worker.join(3)
            self.assertFalse(c.worker.is_alive());self.assertFalse(c.cfg['armed']);self.assertEqual(Expired.attempts,1)

# Reuse just the HTTP fixture; do not duplicate all inherited tests.
class Boundaries(unittest.TestCase):
    setUp=test_dashboard.Tests.setUp;tearDown=test_dashboard.Tests.tearDown;request=test_dashboard.Tests.request;login=test_dashboard.Tests.login
    def test_viewer_cannot_mutate_but_can_logout(self):
        self.server.pair_role='viewer'
        with patch.object(Handler,'local',return_value=False):
            self.login()
            self.assertEqual(self.request('/api/state')[1]['role'],'viewer')
            self.assertEqual(self.request('/api/action',{'action':'pause'})[0],403)
            self.assertEqual(self.request('/api/schedule',{'confirmed':True,'schedule':[]})[0],403)
            self.assertEqual(self.request('/api/logout',{})[0],200)
    def test_remote_expired_pairing_and_local_regeneration(self):
        self.server.pair_expires=time.monotonic()-1
        with patch.object(Handler,'local',return_value=False):self.assertEqual(self.request('/api/login',{'code':'test-pairing-code'})[0],401)
        self.login();status,body,_=self.request('/api/devices/rotate',{'role':'viewer'})
        self.assertEqual(status,200);self.assertEqual(self.server.pair_role,'viewer');self.assertGreater(self.server.pair_expires,time.monotonic())
    def test_device_revoke_and_remote_backup_restrictions(self):
        self.login();devices=self.request('/api/devices')[1]['devices'];self.assertEqual(len(devices),1)
        with patch.object(Handler,'local',return_value=False):
            for path in ['/api/devices','/api/backup']:self.assertEqual(self.request(path)[0],403)
            self.assertEqual(self.request('/api/restore',{'confirmed':True})[0],403)
        self.assertEqual(self.request('/api/devices/revoke',{'id':devices[0]['id']})[0],200)
        self.assertEqual(self.request('/api/state')[0],401)
