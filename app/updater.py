"""User-requested app updates. No elevation, credential migration or platform writes.
Only configure an HTTPS release feed controlled by the app's maintainer.
SHA-256 detects corrupt downloads; it is not a publisher signature.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

APP_ID = 'iskcon-live-desk'
DEFAULT_FEED = 'https://raw.githubusercontent.com/bawra6291-lab/Live-Studio/main/updates/latest.json'
MAX_ZIP = 20 * 1024 * 1024
MAX_EXPANDED = 50 * 1024 * 1024
REQUIRED = {'launcher.py','updater.py','version.json','requirements.txt','dashboard.py','config.py'}

class UpdateError(RuntimeError):
    pass

def version_key(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{1,4}\.\d{1,4}\.\d{1,4}', value):
        raise UpdateError('Invalid update version.')
    return tuple(map(int, value.split('.')))

def installed_version(folder):
    return json.loads((Path(folder)/'version.json').read_text('utf-8'))['version']

def https_url(url):
    p = urlsplit(url)
    if (p.scheme != 'https' or not p.hostname or p.username or p.password
            or p.fragment or any(c.isspace() for c in url)):
        raise UpdateError('Use a direct HTTPS update address without a login or fragment.')
    return url

class HTTPSRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        https_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def fetch(url, limit, destination=None):
    https_url(url)
    request = Request(url, headers={'User-Agent':'ISKCON-Live-Desk-Updater/1','Cache-Control':'no-cache'})
    try:
        with build_opener(HTTPSRedirects()).open(request, timeout=25) as response:
            https_url(response.url)
            data = bytearray(); total = 0
            out = open(destination,'wb') if destination else None
            try:
                while True:
                    chunk = response.read(64*1024)
                    if not chunk:break
                    total += len(chunk)
                    if total > limit:raise UpdateError('Update download exceeds its size limit.')
                    if out:out.write(chunk)
                    else:data.extend(chunk)
            finally:
                if out:out.close()
            return bytes(data) if destination is None else total
    except UpdateError:raise
    except Exception as exc:
        raise UpdateError('Download failed. Check internet and the update address; your installed app is unchanged.') from exc

def check_feed(url, current):
    try:
        manifest=json.loads(fetch(url,128*1024))
        if manifest['app_id'] != APP_ID or manifest['update_format'] != 1:
            raise UpdateError('This is not a supported Live Desk update feed.')
        version_key(manifest['version']);https_url(manifest['package_url'])
        if not re.fullmatch('[0-9a-f]{64}',manifest['sha256']):raise ValueError()
        if not isinstance(manifest['size'],int) or not 0 < manifest['size'] <= MAX_ZIP:raise ValueError()
        manifest['notes']=str(manifest.get('notes',''))[:4000]
        manifest['available']=version_key(manifest['version']) > version_key(current)
        return manifest
    except UpdateError:raise
    except Exception as exc:raise UpdateError('The update address did not return a valid release manifest.') from exc

def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(65536),b''):h.update(chunk)
    return h.hexdigest()

def safe_member(name):
    if '\\' in name or ':' in name or '\x00' in name:raise UpdateError('Unsafe update filename.')
    p=PurePosixPath(name)
    if p.is_absolute() or not p.parts or any(x in ('.','..') for x in name.split('/')):
        raise UpdateError('Unsafe update path.')
    for part in p.parts:
        if part.endswith(('.', ' ')) or re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?',part):
            raise UpdateError('Unsupported Windows filename in update.')
    return p

def unpack_package(archive, stage, current, expected=None):
    """Extract to a NEW sibling directory, verifying exact declared file hashes."""
    archive=Path(archive);stage=Path(stage)
    if archive.stat().st_size > MAX_ZIP:raise UpdateError('Update package is too large.')
    if expected and (archive.stat().st_size != expected['size'] or sha256(archive) != expected['sha256']):
        raise UpdateError('Download checksum does not match. Current app was not changed.')
    stage.mkdir(exist_ok=False)
    try:
        with zipfile.ZipFile(archive) as z:
            members=z.infolist()
            if len(members)>1000 or sum(x.file_size for x in members)>MAX_EXPANDED:
                raise UpdateError('Update archive exceeds extraction limits.')
            files={};seen=set()
            for item in members:
                name=item.filename.rstrip('/')
                p=safe_member(name)
                if p.parts[0]!='ISKCON-Live-Start':raise UpdateError('Wrong update package root.')
                if stat.S_ISLNK(item.external_attr>>16):raise UpdateError('Links are not allowed in updates.')
                if item.is_dir():continue
                rel='/'.join(p.parts[1:])
                if not rel or rel.casefold() in seen:raise UpdateError('Duplicate update filename.')
                seen.add(rel.casefold());files[rel]=item
            if 'release.json' not in files:raise UpdateError('Use an updater-ready release (v0.5 or later).')
            release=json.loads(z.read(files['release.json']))
            if release['app_id']!=APP_ID or release['update_format']!=1:raise UpdateError('Wrong update application.')
            if version_key(release['version'])<=version_key(current):raise UpdateError('This package is not newer than your installed version.')
            if expected and release['version']!=expected['version']:raise UpdateError('Release version does not match the download.')
            hashes=release['files']
            if not isinstance(hashes,dict) or set(files)!=(set(hashes)|{'release.json'}) or not REQUIRED<=set(hashes):
                raise UpdateError('The update is incomplete or contains undeclared files.')
            for rel, item in files.items():
                content=z.read(item)
                if rel!='release.json' and hashlib.sha256(content).hexdigest()!=hashes[rel]:
                    raise UpdateError('An update file failed its checksum.')
                target=stage.joinpath(*PurePosixPath(rel).parts)
                target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
                if rel.endswith('.py'):compile(content,rel,'exec')
            if installed_version(stage)!=release['version']:raise UpdateError('App and release versions differ.')
        return release
    except Exception as exc:
        shutil.rmtree(stage,ignore_errors=True)
        if isinstance(exc,UpdateError):raise
        raise UpdateError('Update package validation failed; current app was not changed.') from exc

def prepare_update(app_dir, work_dir, archive=None, manifest=None):
    app_dir=Path(app_dir).resolve();work_dir=Path(work_dir);work_dir.mkdir(parents=True,exist_ok=True)
    stage=app_dir.with_name('.'+app_dir.name+'-update-'+uuid.uuid4().hex)
    downloaded=None
    try:
        if archive is None:
            if manifest is None:raise UpdateError('Check for updates first.')
            fd,name=tempfile.mkstemp(suffix='.zip',dir=work_dir);os.close(fd);downloaded=Path(name)
            fetch(manifest['package_url'],MAX_ZIP,downloaded);archive=downloaded
        release=unpack_package(archive,stage,installed_version(app_dir),manifest)
        if (stage/'requirements.txt').read_bytes()!=(app_dir/'requirements.txt').read_bytes():
            raise UpdateError('This release needs a dependency upgrade. Use its one-time installer instructions.')
        return stage,release
    except Exception:
        shutil.rmtree(stage,ignore_errors=True);raise
    finally:
        if downloaded:downloaded.unlink(missing_ok=True)

def reserve_install(controller):
    """Block all new dashboard operations while an update checks OBS and exits."""
    with controller.lock:
        controller.require_idle()
        if controller.armed or controller.cfg.get('armed'):
            raise UpdateError('Pause automation before installing an update.')
        controller.maintenance=True

def release_install(controller):
    with controller.lock:controller.maintenance=False

def check_obs_idle(controller):
    import pythoncom
    from obs_windows import _processes
    from connections import OBS
    pythoncom.CoInitialize()
    try:
        if not _processes():return
        obs=OBS(dict(controller.cfg),controller.vault)
        try:obs.connect();obs.idle()
        except Exception as exc:
            raise UpdateError('OBS is active or its idle state could not be verified. End the live/recording normally, then retry the update.') from exc
        finally:obs.close()
    finally:pythoncom.CoUninitialize()

def start_installer(app_dir, stage, work_dir):
    work_dir=Path(work_dir);job=work_dir/uuid.uuid4().hex;job.mkdir(parents=True)
    worker=job/'updater_worker.py';shutil.copyfile(Path(__file__).resolve(),worker)
    plan={'app_dir':str(Path(app_dir).resolve()),'stage':str(Path(stage).resolve()),
          'pid':os.getpid(),'python':sys.executable,'job':str(job.resolve())}
    path=job/'plan.json';path.write_text(json.dumps(plan),encoding='utf-8')
    # The worker must live outside the app folder being renamed. No shell/UAC.
    process=subprocess.Popen([sys.executable,str(worker),'--apply',str(path)],cwd=str(job),
                             creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    return process,job

def rename_when_released(source,target):
    # The py.exe / CMD parent can release its working directory just after Python exits.
    for attempt in range(20):
        try:return source.rename(target)
        except PermissionError:
            if attempt==19:raise
            time.sleep(0.25)

def swap_folders(app_dir,stage):
    app_dir=Path(app_dir);stage=Path(stage)
    # Reject redirected endpoints before resolving Windows short-name aliases.
    # prepare_update resolves its path; callers can still hold the 8.3 spelling.
    if any(p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()) for p in (app_dir,stage)):
        raise UpdateError('Unsafe installation directory.')
    app_dir=app_dir.resolve();stage=stage.resolve()
    if stage.parent!=app_dir.parent or stage==app_dir or not app_dir.is_dir() or not stage.is_dir():
        raise UpdateError('Unsafe installation directory.')
    backup=app_dir.with_name(app_dir.name+'-previous-'+uuid.uuid4().hex[:8])
    rename_when_released(app_dir,backup)
    try:rename_when_released(stage,app_dir)
    except Exception:
        rename_when_released(backup,app_dir);raise
    return backup

def wait_for_parent(pid):
    import ctypes
    from ctypes import wintypes
    k=ctypes.WinDLL('kernel32',use_last_error=True)
    k.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];k.OpenProcess.restype=wintypes.HANDLE
    k.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD];k.WaitForSingleObject.restype=wintypes.DWORD
    k.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=k.OpenProcess(0x00100000,False,pid)
    if not handle:
        if ctypes.get_last_error()==87:return
        raise UpdateError('Cannot confirm the old app has exited; update cancelled.')
    try:
        if k.WaitForSingleObject(handle,120000)!=0:raise UpdateError('Old app did not exit; update cancelled.')
    finally:k.CloseHandle(handle)

def apply_plan(plan):
    app_dir=Path(plan['app_dir']);stage=Path(plan['stage']);job=Path(plan['job'])
    status=job.parent/'last-result.json'
    def record(message,ok=False):
        status.write_text(json.dumps({'ok':ok,'message':message,'at':time.time()}),encoding='utf-8')
    backup=None;proc=None
    try:
        wait_for_parent(int(plan['pid']))
        # Refuse to swap if another Live Desk instance has already taken over.
        with socket.socket() as guard:
            guard.bind(('127.0.0.1',47639))
            backup=swap_folders(app_dir,stage)
        health=job/'ready'
        env=dict(os.environ);env['ISKCON_UPDATE_READY']=str(health)
        proc=subprocess.Popen([plan['python'],str(app_dir/'launcher.py')],cwd=str(app_dir),env=env)
        for _ in range(90):
            if health.exists():
                record('Update installed. Previous app backup: '+str(backup)+'. Run Check connections, then enable automation.',True);return
            if proc.poll() is not None:break
            time.sleep(1)
        if proc.poll() is None:
            record('Update installed but startup is not confirmed. Check the app on this PC. Backup: '+str(backup));return
        # The failed new process is already gone; never kill a potentially live app.
        failed=app_dir.with_name(app_dir.name+'-failed-'+uuid.uuid4().hex[:8])
        app_dir.rename(failed);backup.rename(app_dir);backup=None
        record('New app could not start. Previous app restored; check dependencies and the update source.')
        subprocess.Popen([plan['python'],str(app_dir/'launcher.py')],cwd=str(app_dir))
    except Exception as exc:
        if backup is not None and proc is None:
            # Launch itself failed; no new process can be streaming.
            try:
                app_dir.rename(app_dir.with_name(app_dir.name+'-failed-'+uuid.uuid4().hex[:8]))
                backup.rename(app_dir);backup=None
                record('New app could not launch. Previous app restored.')
                subprocess.Popen([plan['python'],str(app_dir/'launcher.py')],cwd=str(app_dir))
                return
            except Exception:pass
        # Keep all remaining files available for recovery. No credential writes.
        record('Update stopped ('+type(exc).__name__+'). Open the app again. '+('Backup: '+str(backup) if backup else 'Previous files retained.'))

if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--apply':
        apply_plan(json.loads(Path(sys.argv[2]).read_text('utf-8')))
