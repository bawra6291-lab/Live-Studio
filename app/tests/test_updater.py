import hashlib,json,os,sys,tempfile,unittest,zipfile
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import updater as u
from tools.build_release import build
from dashboard import Controller
from test_dashboard import Vault,Service

class Updates(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name)
        self.app=self.base/'app';self.src=self.base/'source';self.out=self.base/'out';self.work=self.base/'work';self.work.mkdir()
        for folder,version in [(self.app,'0.5.0'),(self.src,'0.6.0')]:
            folder.mkdir()
            for name in u.REQUIRED:(folder/name).write_text('# app\n')
            (folder/'requirements.txt').write_text('requests>=2.32,<3\n')
            (folder/'version.json').write_text(json.dumps({'app_id':u.APP_ID,'version':version,'update_format':1}))
        self.package=build(self.src,self.out,'https://updates.example/app','New version')
    def tearDown(self):self.tmp.cleanup()
    def test_prepare_does_not_change_running_app(self):
        (self.app/'local-note.txt').write_text('keep')
        stage,release=u.prepare_update(self.app,self.work,archive=self.package)
        self.assertEqual(release['version'],'0.6.0');self.assertEqual(u.installed_version(self.app),'0.5.0')
        self.assertEqual((self.app/'local-note.txt').read_text(),'keep');self.assertTrue((stage/'launcher.py').exists())
    def test_download_manifest_checks_version_and_size(self):
        manifest=json.loads((self.out/'latest.json').read_text())
        with patch.object(u,'fetch',return_value=json.dumps(manifest).encode()):
            self.assertTrue(u.check_feed('https://updates.example/latest.json','0.5.0')['available'])
            self.assertFalse(u.check_feed('https://updates.example/latest.json','0.6.0')['available'])
        manifest['size']=u.MAX_ZIP+1
        with patch.object(u,'fetch',return_value=json.dumps(manifest).encode()):
            with self.assertRaises(u.UpdateError):u.check_feed('https://updates.example/latest.json','0.5.0')
    def test_non_feed_page_is_an_error_not_up_to_date(self):
        with patch.object(u,'fetch',return_value=b'<html>Login</html>'):
            with self.assertRaises(u.UpdateError):u.check_feed('https://example.com/login','0.5.0')
    def test_https_only_including_redirects(self):
        for url in ('http://example.com/update','file:///tmp/a','https://user:pass@example.com/a','https://example.com/a#frag'):
            with self.subTest(url=url),self.assertRaises(u.UpdateError):u.https_url(url)
        with self.assertRaises(u.UpdateError):u.HTTPSRedirects().redirect_request(None,None,302,'',{},'http://bad.example/a')
    def test_corrupt_download_rejected_before_extract(self):
        manifest=json.loads((self.out/'latest.json').read_text());manifest['sha256']='0'*64
        stage=self.base/'stage'
        with self.assertRaises(u.UpdateError):u.unpack_package(self.package,stage,'0.5.0',manifest)
        self.assertFalse(stage.exists())
    def test_bad_archive_paths_and_duplicates(self):
        for name in ['ISKCON-Live-Start/../outside.py','ISKCON-Live-Start/C:/bad.py','ISKCON-Live-Start/CON.txt','ISKCON-Live-Start/LAUNCHER.PY']:
            altered=self.base/'bad.zip'
            with zipfile.ZipFile(self.package) as original,zipfile.ZipFile(altered,'w') as z:
                for item in original.infolist():z.writestr(item,original.read(item))
                z.writestr(name,b'# bad')
            stage=self.base/'stage'
            with self.subTest(name=name),self.assertRaises(u.UpdateError):u.unpack_package(altered,stage,'0.5.0')
            self.assertFalse(stage.exists())
    def test_tampered_file_hash_is_rejected(self):
        altered=self.base/'bad.zip'
        with zipfile.ZipFile(self.package) as original,zipfile.ZipFile(altered,'w') as z:
            for item in original.infolist():z.writestr(item,b'print("tampered")' if item.filename.endswith('/launcher.py') else original.read(item))
        with self.assertRaises(u.UpdateError):u.unpack_package(altered,self.base/'stage','0.5.0')
    def test_no_downgrade(self):
        with self.assertRaisesRegex(u.UpdateError,'not newer'):u.unpack_package(self.package,self.base/'stage','0.6.0')
    def test_dependency_change_refused(self):
        (self.src/'requirements.txt').write_text('different-package\n');build(self.src,self.out)
        with self.assertRaisesRegex(u.UpdateError,'dependency'):u.prepare_update(self.app,self.work,archive=self.package)
        self.assertFalse(list(self.base.glob('.app-update-*')))
    def test_swap_preserves_backup_and_stable_path(self):
        stage,_=u.prepare_update(self.app,self.work,archive=self.package)
        backup=u.swap_folders(self.app,stage)
        self.assertEqual(u.installed_version(self.app),'0.6.0');self.assertEqual(u.installed_version(backup),'0.5.0')
    def test_failed_swap_restores_original(self):
        stage,_=u.prepare_update(self.app,self.work,archive=self.package)
        rename=Path.rename
        def fail_stage(path,target):
            if path==stage:raise PermissionError('locked')
            return rename(path,target)
        with patch.object(Path,'rename',fail_stage),patch.object(u.time,'sleep'),self.assertRaises(PermissionError):u.swap_folders(self.app,stage)
        self.assertEqual(u.installed_version(self.app),'0.5.0')
    def test_failed_new_process_restores_previous(self):
        stage,_=u.prepare_update(self.app,self.work,archive=self.package);job=self.work/'job';job.mkdir()
        plan={'app_dir':str(self.app),'stage':str(stage),'job':str(job),'pid':999,'python':sys.executable}
        process=Mock();process.poll.return_value=1
        with patch.object(u,'wait_for_parent'),patch.object(u.subprocess,'Popen',return_value=process) as launch:
            u.apply_plan(plan)
        self.assertEqual(u.installed_version(self.app),'0.5.0');self.assertEqual(launch.call_count,2)
        self.assertIn('restored',json.loads((self.work/'last-result.json').read_text())['message'])
    def test_successful_new_process_keeps_update(self):
        stage,_=u.prepare_update(self.app,self.work,archive=self.package);job=self.work/'job';job.mkdir()
        plan={'app_dir':str(self.app),'stage':str(stage),'job':str(job),'pid':999,'python':sys.executable}
        def launched(*args,**kwargs):(job/'ready').write_text('ready');return Mock()
        with patch.object(u,'wait_for_parent'),patch.object(u.subprocess,'Popen',side_effect=launched):u.apply_plan(plan)
        self.assertEqual(u.installed_version(self.app),'0.6.0');self.assertTrue(json.loads((self.work/'last-result.json').read_text())['ok'])
    def test_executable_launch_failure_rolls_back(self):
        stage,_=u.prepare_update(self.app,self.work,archive=self.package);job=self.work/'job';job.mkdir()
        plan={'app_dir':str(self.app),'stage':str(stage),'job':str(job),'pid':999,'python':sys.executable}
        with patch.object(u,'wait_for_parent'),patch.object(u.subprocess,'Popen',side_effect=[OSError('launch failed'),Mock()]):u.apply_plan(plan)
        self.assertEqual(u.installed_version(self.app),'0.5.0')
    def test_install_requires_paused_and_blocks_new_operations(self):
        c=Controller(self.base/'settings',Service,Vault());c.cfg['armed']=True
        with self.assertRaises(u.UpdateError):u.reserve_install(c)
        c.cfg['armed']=False;u.reserve_install(c)
        with self.assertRaisesRegex(ValueError,'update'):c.run('check')
        with self.assertRaisesRegex(ValueError,'update'):c.save({})
        u.release_install(c);c.require_idle();c.shutdown()
    def test_obs_active_or_unreachable_blocks_install(self):
        c=NS(cfg={},vault=Mock());obs=Mock();obs.idle.side_effect=RuntimeError('active')
        with patch.dict(sys.modules,{'pythoncom':Mock()}),patch('obs_windows._processes',return_value={1}),patch('connections.OBS',return_value=obs):
            with self.assertRaises(u.UpdateError):u.check_obs_idle(c)
        obs.close.assert_called_once()
        obs=Mock();obs.connect.side_effect=RuntimeError('unreachable')
        with patch.dict(sys.modules,{'pythoncom':Mock()}),patch('obs_windows._processes',return_value={1}),patch('connections.OBS',return_value=obs):
            with self.assertRaises(u.UpdateError):u.check_obs_idle(c)
        obs.idle.assert_not_called()

if __name__=='__main__':unittest.main()
