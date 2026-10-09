"""Local-owner dashboard updater using the existing verified staging and rollback worker."""
import json, shutil, threading
from pathlib import Path
import updater
from core import atomic_json

class UpdateService:
    def __init__(self,controller,app_dir=None):
        self.c=controller;self.app=Path(app_dir or Path(__file__).parent);self.work=controller.base/'updates';self.work.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock();self.worker=None;self.manifest=None;self.exit_ready=threading.Event()
        self.prefs=self.work/'source.json'
        source=json.loads(self.prefs.read_text('utf-8')).get('manifest_url') if self.prefs.exists() else None
        self.info={'source':source or updater.DEFAULT_FEED,'busy':False,'state':'idle','message':'Check for a new version here. Saved setup is preserved.','percent':None,'available':False,'version':'','notes':''}
        last=self.work/'last-result.json'
        if last.exists():
            try:self.info['last_result']=json.loads(last.read_text('utf-8'))
            except (ValueError,OSError):pass
    def snapshot(self):
        with self.lock:return dict(self.info)
    def set(self,**values):
        with self.lock:self.info.update(values)
    def begin(self,work):
        with self.lock:
            if self.info['busy']:raise ValueError('Wait for the current update operation.')
            self.info['busy']=True
        self.worker=threading.Thread(target=work,daemon=True);self.worker.start()
    def check(self,data):
        value=data.get('source',self.info['source'])
        if not isinstance(value,str):raise ValueError('Enter the maintainer update address.')
        url=updater.https_url(value.strip())
        if url!=self.info['source'] and data.get('confirmed') is not True:raise ValueError('Confirm the maintainer update address before saving.')
        def work():
            try:
                self.set(state='checking',message='Checking the update feed…',percent=None,available=False)
                self.manifest=None
                result=updater.check_feed(url,updater.installed_version(self.app));self.manifest=result
                atomic_json(self.prefs,{'manifest_url':url})
                self.set(source=url,state='available' if result['available'] else 'current',available=result['available'],version=result['version'],notes=result['notes'],message='Version '+result['version']+' is available.' if result['available'] else 'No newer version at this address.')
            except Exception as exc:self.set(state='failed',message=str(exc) if isinstance(exc,updater.UpdateError) else 'Update check failed. Current app is unchanged.')
            finally:self.set(busy=False)
        self.begin(work)
    def install(self,data):
        if data.get('confirmed') is not True:raise ValueError('Confirm installation and app restart.')
        with self.c.lock,self.lock:
            if self.info['busy'] or not self.manifest or not self.manifest.get('available'):raise ValueError('Check for an available update first.')
            manifest=dict(self.manifest)
            updater.reserve_install(self.c)
            self.info['busy']=True
        def work():
            stage=None;archive=self.work/'dashboard-download.zip'
            try:
                self.set(state='checking_obs',message='Verifying that OBS outputs are idle…',percent=0)
                updater.check_obs_idle(self.c)
                self.set(state='downloading',message='Downloading the verified update…')
                def progress(done,total):self.set(percent=min(99,round(done*100/total)) if total else None)
                updater.fetch(manifest['package_url'],updater.MAX_ZIP,archive,progress=progress)
                self.set(state='verifying',message='Verifying checksum and preparing the backup…',percent=100)
                stage,_=updater.prepare_update(self.app,self.work,archive=archive,manifest=manifest)
                updater.check_obs_idle(self.c)
                updater.start_installer(self.app,stage,self.work)
                self.set(state='restarting',message='Restarting Live Desk. Keep this page open; the app will reopen the dashboard.')
                self.exit_ready.set()
            except Exception as exc:
                if stage:shutil.rmtree(stage,ignore_errors=True)
                updater.release_install(self.c)
                self.set(busy=False,state='failed',message=str(exc) if isinstance(exc,(updater.UpdateError,ValueError)) else 'Installation could not be prepared. Your app is unchanged.')
            finally:archive.unlink(missing_ok=True)
        self.worker=threading.Thread(target=work,daemon=True);self.worker.start()
    def rollback(self,data):
        if data.get('confirmed') is not True:raise ValueError('Confirm rollback and app restart.')
        with self.c.lock,self.lock:
            if self.info['busy']:raise ValueError('Wait for the update operation.')
            candidates=sorted(self.app.parent.glob(self.app.name+'-previous-*'),key=lambda p:p.stat().st_mtime,reverse=True)
            backup=next((p for p in candidates if p.is_dir() and not p.is_symlink() and not getattr(p,'is_junction',lambda:False)() and (p/'version.json').is_file()),None)
            if not backup:raise ValueError('No previous-version backup exists on this PC.')
            updater.reserve_install(self.c);self.info['busy']=True
        def work():
            stage=None
            try:
                updater.check_obs_idle(self.c)
                # Backups are local app code. Only the updater-created sibling is used;
                # no HTTP path or download is accepted for rollback.
                import uuid
                stage=self.app.with_name('.'+self.app.name+'-rollback-'+uuid.uuid4().hex)
                import hashlib
                release=json.loads((backup/'release.json').read_text('utf-8'))
                if release.get('app_id')!=updater.APP_ID or not updater.REQUIRED<=set(release.get('files',{})):raise updater.UpdateError('Previous app backup is incomplete.')
                for path in backup.rglob('*'):
                    if path.is_symlink() or getattr(path,'is_junction',lambda:False)():raise updater.UpdateError('Previous app backup contains links.')
                for name,digest in release['files'].items():
                    rel=updater.safe_member(name);path=backup.joinpath(*rel.parts)
                    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise updater.UpdateError('Previous app backup failed verification.')
                shutil.copytree(backup,stage)
                if (stage/'requirements.txt').read_bytes()!=(self.app/'requirements.txt').read_bytes():raise updater.UpdateError('Previous runtime dependencies differ. Restore with its installer.')
                for path in stage.rglob('*.py'):compile(path.read_bytes(),str(path),'exec')
                updater.check_obs_idle(self.c);updater.start_installer(self.app,stage,self.work)
                self.set(state='restarting',message='Restoring the previous app version. Saved operator data stays in place.');self.exit_ready.set()
            except Exception as exc:
                if stage:shutil.rmtree(stage,ignore_errors=True)
                updater.release_install(self.c);self.set(busy=False,state='failed',message=str(exc) if isinstance(exc,(ValueError,updater.UpdateError)) else 'Rollback preparation failed; current app retained.')
        self.worker=threading.Thread(target=work,daemon=True);self.worker.start()
