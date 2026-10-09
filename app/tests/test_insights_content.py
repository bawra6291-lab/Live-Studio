import base64,json,struct,tempfile,unittest
from pathlib import Path
from datetime import timedelta
from unittest.mock import Mock,patch
from core import Journal,now_ist,atomic_json
from dashboard import Controller
from content import ContentStore
from insights import LiveMonitor,progress
from schedule_config import get_schedule,validate_schedule
from update_service import UpdateService
from test_dashboard import Vault,Service

PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAIAAAABCAIAAAB7QOjdAAAAD0lEQVR4nGN4sKBAxtYIAAsnAnyYPiW8AAAAAElFTkSuQmCC')
class FeatureTests(unittest.TestCase):
    def test_content_asset_bounded_hash_verified_and_path_guarded(self):
        with tempfile.TemporaryDirectory() as d:
            c=ContentStore(d);item=c.add(base64.b64encode(PNG).decode());self.assertEqual(c.get(item['id'])[0],PNG)
            self.assertEqual(Path(c.path_for(item['id'])).suffix,'.png')
            with self.assertRaises(ValueError):c.get('../outside')
            with self.assertRaises(ValueError):c.add(base64.b64encode(b'notimage').decode())
            (c.folder/item['id']).write_bytes(PNG+b'damaged')
            with self.assertRaises(ValueError):c.get(item['id'])
    def test_content_validation_and_legacy_plan_stable(self):
        slot=get_schedule({})[0];self.assertNotIn('description_mode',slot)
        new=validate_schedule([{**slot,'description_mode':'custom','description':'Same description','thumbnail_days':{'1':'a'*64}}])[0]
        self.assertEqual(new['description'],'Same description')
        for changes in [{'thumbnail_days':{'32':'a'*64}},{'description_mode':'custom','description':'<script>'},{'thumbnail_days':{'1':'../foo'}}]:
            with self.assertRaises(ValueError):validate_schedule([{**slot,**changes}])
    def test_content_preview_keeps_program_date_and_official_key_policy(self):
        with tempfile.TemporaryDirectory() as d:
            c=ContentStore(d);s={**get_schedule({})[0],'title_template':'{date} | {program}','description_mode':'custom','description':'Saved text'}
            p=c.preview(s,now_ist().date());self.assertIn(s['name'],p['title']);self.assertEqual(p['description'],'Saved text');self.assertIn('never create',p['stream_key_policy'])
    def test_progress_prioritizes_started_run_and_exact_camera_due(self):
        with tempfile.TemporaryDirectory() as d:
            j=Journal(Path(d)/'journal.json');s=get_schedule({})[0];now=now_ist()
            j.data={'2026-10-09:a':{'phase':'live','plan':s,'confirmed_at':now.isoformat(),'scheduled_at':now.isoformat(),'obs_start_epoch':1,'yt_id':'abcdefghijk','fb_id':'12345'},'2026-10-10:b':{'phase':'needs_review','plan':s,'scheduled_at':(now+timedelta(days=1)).isoformat()}}
            p=progress(j);self.assertEqual(p['key'],'2026-10-09:a');self.assertEqual(p['steps'][4]['status'],'done');self.assertTrue(p['camera'][0]['due'])
    def test_monitor_never_launches_or_writes_and_validates_page_event(self):
        with tempfile.TemporaryDirectory() as d:
            c=Controller(d,Service,Vault());service=Mock();service.obs.call.side_effect=lambda name,**kw: {'outputActive':True,'outputBytes':100} if name=='GetStreamStatus' else {'outputs':[]} if name=='GetOutputList' else {'currentProgramSceneName':'Main'} if name=='GetCurrentProgramScene' else {'imageData':'data:image/jpeg;base64,'+base64.b64encode(b'\xff\xd8test').decode()}
            service.fb.recent.return_value=[];c.factory=lambda *a:service
            atomic_json(c.base/'journal.json',{'2026-10-09:a':{'phase':'live','fb_id':'12345'}})
            c.monitor.sample();service.obs.connect.assert_called_once_with(launch=False);self.assertEqual(c.monitor.snapshot()['facebook'],'unavailable');service.fb.api.assert_not_called();service.yt.api.assert_not_called();self.assertTrue(c.monitor.snapshot()['obs']['active'])
    def test_readiness_repairs_missing_json_and_damaged_thumbnail(self):
        with tempfile.TemporaryDirectory() as d:
            c=Controller(d,Service,Vault());c.cfg['google_client_file']=str(c.base/'deleted.json');c.cfg['schedule']=[{**get_schedule({})[0],'thumbnail_days':{'1':'a'*64}}]
            items=c.snapshot(True)['readiness']['items'];self.assertTrue(any(x['id']=='oauth_file' and x['status']=='blocked' for x in items));self.assertTrue(any(x['id'].startswith('content_') for x in items));self.assertIsNone(c.snapshot(False)['updates'])
    def test_retry_requires_fresh_exact_inspection(self):
        with tempfile.TemporaryDirectory() as d:
            c=Controller(d,Service,Vault());s=get_schedule({})[0];c.cfg['schedule']=[s];now=now_ist().replace(hour=4,minute=30,second=0,microsecond=0);j=Journal(c.base/'journal.json');j.put(s,now.date(),phase='needs_review',yt_id='abcdefghijk')
            with patch('dashboard.now_ist',return_value=now):
                with self.assertRaisesRegex(ValueError,'Inspect'):c.retry(s['id'])
                j.put(s,now.date(),inspection={'checked_at':now.isoformat(),'can_review':True,'youtube_id':'wrong','facebook_id':''})
                with self.assertRaises(ValueError):c.retry(s['id'])
                j.put(s,now.date(),inspection={'checked_at':now.isoformat(),'can_review':True,'youtube_id':'abcdefghijk','facebook_id':''})
                c.retry(s['id']);self.assertEqual(Journal(j.path).get(s,now.date())['phase'],'new')
    def test_dashboard_update_failure_releases_install_guard(self):
        with tempfile.TemporaryDirectory() as d:
            c=Controller(d,Service,Vault());u=c.updates;u.manifest={'available':True,'version':'9.0.0','package_url':'https://example.com/a.zip'}
            with patch('updater.check_obs_idle',side_effect=ValueError('OBS active')):
                u.install({'confirmed':True});u.worker.join(2)
            self.assertFalse(c.maintenance);self.assertEqual(u.snapshot()['state'],'failed');self.assertFalse(u.exit_ready.is_set())
    def test_update_success_verified_before_exit_and_progress(self):
        with tempfile.TemporaryDirectory() as d:
            c=Controller(d,Service,Vault());u=c.updates;u.manifest={'available':True,'version':'9.0.0','package_url':'https://example.com/a.zip'}
            def fetch(url,limit,destination,progress):destination.write_bytes(b'fixture');progress(50,100)
            with patch('updater.check_obs_idle') as idle,patch('updater.fetch',side_effect=fetch),patch('updater.prepare_update',return_value=(Path(d)/'stage',{})) as prepare,patch('updater.start_installer') as installer:
                u.install({'confirmed':True});u.worker.join(2)
            self.assertEqual(idle.call_count,2);prepare.assert_called_once();installer.assert_called_once();self.assertTrue(u.exit_ready.is_set());self.assertTrue(c.maintenance);self.assertEqual(u.snapshot()['state'],'restarting')
    def test_corrupt_update_preference_does_not_prevent_dashboard_start(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'updates').mkdir();(Path(d)/'updates'/'source.json').write_text('corrupt')
            c=Controller(d,Service,Vault());self.assertTrue(c.updates.snapshot()['source'].startswith('https://'))
    def test_update_feed_failure_is_reported_without_install(self):
        with tempfile.TemporaryDirectory() as d:
            c=Controller(d,Service,Vault());u=c.updates
            with patch('updater.check_feed',side_effect=ValueError('Bad feed')):
                u.check({'confirmed':True});u.worker.join(2)
            self.assertEqual(u.snapshot()['state'],'failed');self.assertFalse(c.maintenance);self.assertFalse(u.snapshot()['available'])
    def test_update_guard_blocks_pc_action_and_requires_confirmation(self):
        with tempfile.TemporaryDirectory() as d:
            from desktop_host import DesktopHost
            c=Controller(d,Service,Vault());c.desktop_host=DesktopHost();c.desktop_host.submit({'action':'obs'});c.updates.manifest={'available':True}
            with self.assertRaises(ValueError):c.updates.install({})
            with self.assertRaises(Exception):c.updates.install({'confirmed':True})
            self.assertFalse(c.maintenance)
    def test_check_receipt_completed_only_after_worker(self):
        with tempfile.TemporaryDirectory() as d:
            c=Controller(d,Service,Vault());c.run('check');c.worker.join(2);self.assertEqual(c.operation_results[1]['status'],'completed')

if __name__=='__main__':unittest.main()
