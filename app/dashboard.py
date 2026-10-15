"""Local dashboard. One serialized controller; scheduled ends require explicit saved end times."""
from __future__ import annotations
import ipaddress, json, secrets, socket, threading, time, re, platform
from collections import deque
from datetime import timedelta
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from config import BASE, DEFAULTS
from workspace import load_settings, validate_settings, setup_steps, IDENTITY_FIELDS
from schedule_config import get_schedule,validate_schedule,occurs_on,upcoming
from recovery import export_backup, import_backup, run_history, inspect_run
from core import SLOTS, Journal, Scheduler, atomic_json, now_ist, slot_time
from updater import installed_version

WEB = Path(__file__).parent / 'web'
SECRET_FIELDS = {'obs_password', 'facebook_page_token', 'camera_password','remote_agent_token'}

def safe_error(exc):
    from connections import SetupError
    return str(exc) if isinstance(exc, SetupError) else f'{type(exc).__name__}: operation failed. Check settings and network on the PC.'

class Controller:
    def __init__(self, base=BASE, factory=None, vault=None):
        self.base = Path(base); self.base.mkdir(parents=True, exist_ok=True)
        self.path = self.base / 'settings.json'
        self.cfg = load_settings(self.path)
        from connections import Services, Vault
        self.factory = factory or Services
        self.vault = vault if vault is not None else Vault(self.cfg['credential_service'])
        self.lock = threading.RLock(); self.stop = threading.Event()
        from visible import Visible
        self.visible=Visible(self.base,self.stop,self.log)
        self.maintenance = False; self.open_updates = None; self.desktop_host = None
        self.worker = None; self.mode = ''; self.armed = False; self.closing = False
        self.logs = deque(maxlen=160); self.message = 'Ready. Check connections before enabling daily starts.'
        self.checked = None; self.error = False
        self.connections = {k: 'unchecked' for k in ('obs','youtube','facebook','camera')}
        self.mobile_urls = []; self.desktop_url = ''; self.mobile_enabled = False
        self.servers=[]
        from content import ContentStore
        from insights import LiveMonitor
        from update_service import UpdateService
        self.content=ContentStore(self.base);self.monitor=LiveMonitor(self);self.updates=UpdateService(self)
        from social import Social
        self.social=Social(self)
        from studio import Studio
        self.studio=Studio(self)
        # The previous posting interface is replaced. Preserve records, but never
        # resume a hidden queue when opening the supplied standalone studio.
        if self.social.data.get('enabled'):
            self.social.data['enabled']=False;self.social.persist()
            self.log('Previous Social Media posting paused. DARSHANFLOW replaces that page; saved photos and drafts are retained.')
        self.operation_serial=0;self.operation_results={}
        self.takeover_state={'status':'idle'};self.takeover_preview=None
        from remote_agent import Agent
        self.remote=Agent(self)
        self.started_at=now_ist().isoformat();self.last_tick=None;self.last_heartbeat=0
        self.previous_heartbeat=json.loads((self.base/'heartbeat.json').read_text('utf-8')) if (self.base/'heartbeat.json').exists() else None
        self.log('Live Desk v'+installed_version(Path(__file__).parent)+' opened. Saved enabled preference: '+str(bool(self.cfg.get('armed')))+'.')

    def log(self, message):
        message = str(message)
        with self.lock:
            for prefix, key in [('OBS connected.', 'obs'), ('YouTube channel verified:', 'youtube'),
                                ('Facebook Page verified:', 'facebook'), ('Camera reachable;', 'camera')]:
                if message.startswith(prefix): self.connections[key] = 'verified'
            if message.startswith('Camera skipped;'):self.connections['camera']='skipped'
            row = {'time': now_ist().strftime('%Y-%m-%d %H:%M:%S'), 'message': message}
            self.logs.append(row)
            with (self.base/'activity.log').open('a', encoding='utf-8') as f:
                f.write(row['time']+'  '+message+'\n')

    def snapshot(self, local=False):
        with self.lock:
            now = now_ist(); journal = Journal(self.base/'journal.json')
            slots = []
            schedule=get_schedule(self.cfg)
            for slot in schedule:
                rec = journal.get(slot, now.date())
                slots.append({**{k:slot[k] for k in ('id','name','at')},
                              'phase': rec.get('phase','waiting') if occurs_on(slot,now.date()) or rec.get('plan') else 'disabled', 'title': rec.get('title',''),
                              'end_at':rec.get('plan',slot)['end_at'],'end_next_day':rec.get('plan',slot)['end_next_day'],'enabled':slot['enabled'],
                              'run_start_at':rec.get('plan',slot)['at'],
                              'camera_states':rec.get('camera_states',{}),'end_state':rec.get('end_state',''),
                              'last_error':rec.get('last_error',''),'stage':rec.get('stage',''),
                              'patrol': rec.get('patrol_result',''), 'patrol_due': rec.get('patrol_due','')})
            calendar=upcoming(schedule,now,days=400,limit=32)
            next_run=calendar[0] if calendar else {'name':'No upcoming programs','at':'—','due':None}
            issue=next((x for x in slots if x.get('last_error') and (x['phase'] in ('needs_review','missed') or x['end_state'] in ('needs_review','missed') or 'needs_review' in x['camera_states'].values())),None)
            return {'now':now.isoformat(), 'date':now.strftime('%A, %d %B %Y'),
                    'workspace_name':self.cfg['workspace_name'], 'setup_steps':setup_steps(self.cfg,self.checked),
                    'visible':self.visible.snapshot(local),
                    'takeover':dict(self.takeover_state),
                    'remote':{'enabled':bool(self.cfg.get('remote_enabled')),'status':self.remote.status,
                        'last_seen':self.remote.last_seen,'url':self.cfg.get('remote_url','') if local else ''},
                    'destinations':{k:self.cfg.get(k,'') for k in ('youtube_channel_id','facebook_page_id','youtube_stream_title','camera_channel')},
                    'progress':__import__('insights').progress(journal,self.mode,self.armed),
                    'readiness':__import__('insights').readiness(self),'monitor':self.monitor.snapshot(),
                    'updates':self.updates.snapshot() if local else None,
                    'social':{'enabled':self.social.data['enabled'],'busy':self.social.busy,'error':self.social.error},
                    'schedule':schedule,'grace_minutes':int(self.cfg.get('grace_minutes',2)),
                    'upcoming':calendar,'runs':run_history(journal),'run_attention':issue,
                    'last_tick':self.last_tick,'started_at':self.started_at,'arm_requested':bool(self.cfg.get('armed')),
                    'armed':self.armed, 'busy':bool(self.maintenance or (self.worker and self.worker.is_alive())),
                    'app_version':json.loads((Path(__file__).parent/'version.json').read_text('utf-8'))['version'],
                    'mode':self.mode, 'message':self.message, 'error':self.error,
                    'connections':dict(self.connections), 'checked':self.checked,
                    'slots':slots, 'next':{k:next_run[k] for k in ('name','due','at')},
                    'logs':list(self.logs), 'local':local, 'mobile_enabled':self.mobile_enabled,
                    'mobile_urls':self.mobile_urls if local else [],
                    'desktop_host':self.desktop_host.snapshot() if local and self.desktop_host else None,
                    'settings':{k:self.cfg.get(k,v) for k,v in DEFAULTS.items() if k!='armed'} if local else None}

    def pause(self):
        # Cancellation is set before taking the state lock, including during connection checks.
        self.stop.set()
        with self.lock:
            self.stop.set()
            self.armed = False; self.cfg['armed'] = False; atomic_json(self.path, self.cfg)
            self.message = 'Paused: future starts, scheduled ends and camera actions are stopped. An operation already underway may finish.'
            self.log(self.message)

    def take_control(self, data):
        """Inspect first, then recheck and manage only the explicitly selected existing run."""
        from copy import deepcopy
        from takeover import select_plan, require_unused, discover, same_live, attach_record, preview, digest
        with self.lock:
            self.require_idle()
            if self.visible.browser.recording:raise ValueError('Finish browser workflow recording first.')
            action=data.get('action')
            if action not in ('inspect','confirm'):raise ValueError('Choose inspect or confirm existing live.')
            now=now_ist();schedule=get_schedule(self.cfg)
            slot,day=select_plan(schedule,data.get('slot'),data.get('date'),now)
            journal=Journal(self.base/'journal.json');require_unused(journal,slot,day)
            expected=self.takeover_preview if action=='confirm' else None
            if action=='confirm':
                if data.get('confirmed') is not True:raise ValueError('Review and confirm this existing live first.')
                if not expected or expected['expires']<time.monotonic() or not secrets.compare_digest(str(data.get('token','')),expected['token']):
                    raise ValueError('Existing live preview expired. Inspect again before taking control.')
                if expected['slot']!=slot or expected['day']!=day or expected['cfg_hash']!=digest(self.cfg) or expected['journal_hash']!=digest(journal.data):
                    raise ValueError('Settings or run history changed. Inspect the running live again.')
                if self.visible.config['mode']=='visible' and slot['end_at']:
                    if not {'youtube_end','facebook_end'}.issubset(self.visible.config['recipes']):raise ValueError('Record both visible end workflows before taking control with an end time.')
                    self.visible.browser.ready()
            self.takeover_preview=None
            cfg={**self.cfg,'_data_base':str(self.base)};cfg_hash=digest(self.cfg);journal_hash=digest(journal.data)
            self.stop.clear();self.mode='takeover';self.error=False
            self.takeover_state={'status':'checking','message':'Reading the active live and OBS outputs; no start/end or camera command is sent.'}
            self.message=self.takeover_state['message']
            def work():
                service=None
                try:
                    service=self.factory(cfg,self.vault,self.log)
                    observed=discover(service,now_ist())
                    if expected and not same_live(expected['observed'],observed):raise ValueError('The live or OBS output changed after preview. Inspect again; no control was taken.')
                    for a in slot['camera_actions']:service.cam.check_action(a)
                    with self.lock:
                        if self.stop.is_set():return
                        if cfg_hash!=digest(self.cfg) or journal_hash!=digest(Journal(self.base/'journal.json').data):raise ValueError('Settings or run history changed during inspection. Inspect again.')
                        select_plan(get_schedule(self.cfg),slot['id'],day.isoformat(),now_ist())
                        latest=Journal(self.base/'journal.json');require_unused(latest,slot,day,observed)
                        record=attach_record(slot,day,observed,now_ist())
                        record['camera_states'].update(latest.get(slot,day).get('camera_states',{}))
                        details=preview(record,day)
                        if action=='inspect':
                            token=secrets.token_urlsafe(24)
                            self.takeover_preview=dict(slot=slot,day=day,observed=observed,token=token,expires=time.monotonic()+90,cfg_hash=cfg_hash,journal_hash=journal_hash)
                            self.takeover_state={'status':'ready','token':token,**details}
                            self.message='Running live verified. Review the titles, remaining camera steps and end time before taking control.'
                            return
                        # Old missed-window diagnostics are retained in the audit, not replayed.
                        previous=deepcopy(latest.get(slot,day))
                        record['audit']=[{'action':'explicit_manual_takeover','at':record['adopted_at'],'previous_phase':previous.get('phase'),'previous_error':previous.get('last_error','')}]
                        latest.data[latest.key(slot,day)]=record
                        atomic_json(latest.path,latest.data)
                        self.armed=True;self.mode='arm'
                        self.takeover_state={'status':'active',**details}
                        self.message='Controlling this existing live only: future camera steps and its saved end time. No new broadcast or OBS restart was sent.'
                        self.log(slot['name']+': '+self.message)
                    if self.visible.config['mode']=='visible':
                        service.close()
                        from visible import VisibleServices
                        service=VisibleServices(cfg,self.vault,self.log,self.visible)
                    scheduler=Scheduler(service,Journal(self.base/'journal.json'),self.log,self.stop.is_set,slots=[slot])
                    while not self.stop.is_set():
                        self.heartbeat();scheduler.run_slot(slot,day,now_ist())
                        if Journal(self.base/'journal.json').get(slot,day).get('phase')=='ended':
                            with self.lock:self.takeover_state={'status':'ended','name':slot['name']};self.message='The controlled live ended at its saved end time.'
                            break
                        self.stop.wait(1)
                except Exception as exc:
                    with self.lock:
                        self.error=True;self.message=str(exc) if isinstance(exc,ValueError) else safe_error(exc)
                        self.takeover_state={'status':'failed','message':self.message};self.log(self.message)
                finally:
                    if service:
                        try:service.close()
                        except Exception:pass
                    with self.lock:
                        self.armed=False;self.mode=''
                        if self.stop.is_set():
                            self.takeover_state={'status':'paused','message':'Existing live control paused. Handle the live manually or resume the recorded plan.'}
                            self.message=self.takeover_state['message']
            self.worker=threading.Thread(target=work,daemon=True);self.worker.start()

    def save_visible(self,data):
        with self.lock:
            self.require_idle()
            if self.armed:raise ValueError('Pause automation before changing browser or workflow settings.')
            if data.get('confirmed') is not True:raise ValueError('Review and confirm the visible workflow or mode before saving.')
            # Browser transport selection does not alter destinations, recipes,
            # execution mode or the frozen plan of an unresolved run. Permit it
            # so the operator can connect/inspect Chrome during recovery.
            browser_only=('browser_source' in data and set(data)<= {'browser_source','mode','confirmed'}
                          and data.get('mode',self.visible.config['mode'])==self.visible.config['mode'])
            if not browser_only:self.require_no_recent_runs()
            self.visible.save(data)

    def visible_browser(self,data):
        with self.lock:
            self.require_idle()
            self.mode='visible_setup';self.error=False
            cfg={**self.cfg,'_data_base':str(self.base)}
            def work():
                try:self.visible.command(data,cfg)
                except Exception as exc:
                    message=safe_error(exc)
                    self.visible.update(state='needs_review',message=message)
                    self.log(message)
                finally:
                    with self.lock:self.mode=''
            self.worker=threading.Thread(target=work,daemon=True);self.worker.start()

    def save(self, values):
        with self.lock:
            self.require_idle()
            if not isinstance(values, dict): raise ValueError('Invalid settings.')
            cfg = dict(self.cfg)
            for key in DEFAULTS:
                if key != 'armed' and key in values:
                    if not isinstance(values[key],str) or len(values[key])>2048: raise ValueError('Invalid settings value.')
                    cfg[key] = values[key].strip()
            if not 1 <= int(cfg['obs_port']) <= 65535: raise ValueError('OBS port must be 1–65535.')
            validate_settings(cfg)
            if any(cfg.get(k)!=self.cfg.get(k) for k in IDENTITY_FIELDS):
                self.require_no_recent_runs()
            for key in SECRET_FIELDS:
                value = values.get(key,'')
                if not isinstance(value,str) or len(value)>12000: raise ValueError('Invalid credential.')
            for key in SECRET_FIELDS:
                if values.get(key): self.vault.set(key, values[key].strip())
            atomic_json(self.path,cfg); self.cfg = cfg
            self.checked=None; self.connections={k:'unchecked' for k in self.connections}
            self.log('Settings saved. Blank secret fields kept their saved values.')

    def require_no_recent_runs(self, slot_ids=None):
        cutoff=(now_ist().date()-timedelta(days=1)).isoformat()
        for key,rec in Journal(self.base/'journal.json').data.items():
            if key[:10]<cutoff or (slot_ids is not None and key.split(':',1)[-1] not in slot_ids):continue
            if rec.get('end_state')=='ended' or rec.get('phase') in ('ended','reviewed'):continue
            if rec.get('yt_id') or rec.get('fb_id') or rec.get('camera_states') or rec.get('phase') in ('preparing','starting'):
                raise ValueError('A recent run still needs review. Keep its destination and program until it is ended; inspect OBS and both platforms.')

    def require_idle(self):
        if self.closing: raise ValueError('App is closing.')
        if self.maintenance: raise ValueError('An app update is in progress.')
        if self.social.busy:raise ValueError('Wait for the social posting operation to finish.')
        if self.worker and self.worker.is_alive(): raise ValueError('Pause automation and wait for the current operation to finish first.')

    def backup(self):
        with self.lock:return export_backup(self.cfg)

    def restore(self,data):
        with self.lock:
            self.require_idle();self.require_no_recent_runs()
            if self.visible.browser.recording:raise ValueError('Finish recording first.')
            if data.get('confirmed') is not True:raise ValueError('Review and confirm the backup before restoring.')
            cfg=import_backup(data.get('backup'),self.cfg)
            atomic_json(self.base/'settings.before-restore.json',self.cfg)
            atomic_json(self.path,cfg);self.cfg=cfg;self.armed=False;self.checked=None
            self.connections={k:'unchecked' for k in self.connections}
            self.log('Settings backup restored. Saved credentials and run history retained. Automation is paused; check connections before enabling.')

    def save_remote(self,data):
        from remote_agent import remote_origin
        with self.lock:
            if data.get('confirmed') is not True:raise ValueError('Confirm remote access settings.')
            if type(data.get('enabled'))!=bool:raise ValueError('Choose whether to enable remote access.')
            if data['enabled']:
                address=remote_origin(data.get('url'))
                token=data.get('token','')
                if not isinstance(token,str) or len(token)>128:raise ValueError('Invalid enrollment token.')
                if address!=self.cfg.get('remote_url') and not token:raise ValueError('Enter a new enrollment token when changing the server.')
                if not token and not self.vault.get('remote_agent_token'):raise ValueError('Enter the agent enrollment token from your remote server administrator.')
                if token:self.vault.set('remote_agent_token',token.strip())
                self.cfg['remote_url']=address
            self.cfg['remote_enabled']=data['enabled'];atomic_json(self.path,self.cfg)
            self.remote.start();self.log('Remote access '+('enabled' if data['enabled'] else 'disabled')+'. Local automation remains independent.')

    def review_run(self,data):
        with self.lock:
            self.require_idle()
            if data.get('action') not in ('inspect','review','end'):raise ValueError('Unknown run action.')
            if data['action'] in ('review','end') and data.get('confirmed') is not True:raise ValueError('Confirm the selected run action first.')
            key=data.get('key');journal=Journal(self.base/'journal.json')
            if not isinstance(key,str) or key not in journal.data:raise ValueError('Unknown recorded run.')
            from copy import deepcopy
            record=deepcopy(journal.data[key]);cfg={**self.cfg,'_data_base':str(self.base)}
            if record.get('phase')=='reviewed':raise ValueError('This run is already reviewed.')
            if data['action']=='end' and not record.get('obs_start_epoch'):raise ValueError('This app did not record starting the selected run. End it manually in OBS and both platforms.')
            self.operation_serial+=1;operation=self.operation_serial
            self.operation_results[operation]={'status':'running','message':'Inspecting the selected recorded run.'}
            self.stop.clear()
            self.mode='inspect_run';self.error=False
            self.message='Reading the recorded run from OBS and both platforms…'
            def work():
                service=None
                try:
                    if data['action']=='end' and self.visible.config['mode']=='visible':
                        from visible import VisibleServices
                        if not {'youtube_end','facebook_end'}.issubset(self.visible.config['recipes']):raise ValueError('Record and review both visible end workflows first.')
                        service=VisibleServices(cfg,self.vault,self.log,self.visible)
                    else:service=self.factory(cfg,self.vault,self.log)
                    if data['action']=='end':
                        def persist(**changes):
                            with self.lock:
                                latest=Journal(self.base/'journal.json');latest.data[key].update(changes);atomic_json(latest.path,latest.data)
                        persist(end_state='sending',stage='operator_ending',operator_end_requested_at=now_ist().isoformat())
                        service.end(record,persist,manual=True)
                        persist(phase='ended',end_state='ended',stage='finished',ended_at=now_ist().isoformat())
                        with self.lock:self.message='Selected run ended. Only its verified broadcasts and OBS outputs were stopped.';self.log(self.message)
                        return
                    result=inspect_run(service,record)
                    with self.lock:
                        latest=Journal(self.base/'journal.json');rec=latest.data[key]
                        rec['inspection']=result
                        if data['action']=='review':
                            if not result['can_review']:raise ValueError('Outputs or platforms are active/unconfirmed. End or inspect them manually before marking reviewed.')
                            rec.update(phase='reviewed',reviewed_at=now_ist().isoformat(),stage='manual_review_complete')
                            rec.setdefault('audit',[]).append({'action':'operator_review','at':rec['reviewed_at'],'previous_phase':record.get('phase')})
                        atomic_json(latest.path,latest.data)
                        self.message='Run '+('marked reviewed; draft broadcasts and journal retained. Future actions for this run are cancelled.' if data['action']=='review' else 'inspection finished. Open Run history for the platform states.')
                        self.log(self.message)
                except Exception as exc:
                    with self.lock:
                        if data['action']=='end':
                            latest=Journal(self.base/'journal.json');latest.data[key].update(end_state='needs_review',last_error=safe_error(exc));atomic_json(latest.path,latest.data)
                        self.error=True;self.message=str(exc) if isinstance(exc,ValueError) else safe_error(exc);self.log(self.message)
                finally:
                    if service:
                        try:service.close()
                        except Exception:pass
                    with self.lock:
                        self.mode=''
                        self.operation_results[operation]={'status':'failed' if self.error else 'completed','message':self.message[:200]}
            self.worker=threading.Thread(target=work,daemon=True);self.worker.start()

    def retry(self, slot_id):
        with self.lock:
            self.require_idle()
            slot = next((s for s in get_schedule(self.cfg) if s['id']==slot_id), None)
            if slot is None: raise ValueError('Unknown program.')
            now = now_ist()
            if now > slot_time(now.date(),slot)+timedelta(minutes=int(self.cfg.get('grace_minutes',2))): raise ValueError('This start window has passed. Wait for tomorrow or start manually in OBS.')
            journal=Journal(self.base/'journal.json')
            if journal.get(slot,now.date()).get('phase') not in ('needs_review','prepared'):
                raise ValueError('Only a failed or prepared slot can be reset.')
            rec=journal.get(slot,now.date())
            if rec.get('obs_start_epoch') or rec.get('confirmed_at'):raise ValueError('This run already started. Inspect and end it manually; it cannot be reset here.')
            inspection=rec.get('inspection',{})
            from datetime import datetime
            fresh=inspection.get('checked_at') and datetime.fromisoformat(inspection['checked_at'])>now-timedelta(seconds=60)
            if not fresh or not inspection.get('can_review') or inspection.get('youtube_id','')!=rec.get('yt_id','') or inspection.get('facebook_id','')!=rec.get('fb_id',''):
                raise ValueError('Inspect this exact recorded run first. A fresh inactive result is required before reset.')
            journal.put(slot,now.date(),phase='new')
            self.log('Slot reset after manual review. Enable daily starts to retry within its scheduled window.')

    def save_schedule(self,data):
        with self.lock:
            self.require_idle()
            schedule=validate_schedule(data.get('schedule'))
            grace=data.get('grace_minutes',2)
            if type(grace)!=int or not 1<=grace<=15:raise ValueError('Late-start allowance must be 1–15 minutes.')
            removed={s['id'] for s in get_schedule(self.cfg)}-{s['id'] for s in schedule}
            self.require_no_recent_runs(removed)
            journal=Journal(self.base/'journal.json');now=now_ist()
            for day in [now.date()-timedelta(days=1),now.date(),now.date()+timedelta(days=1)]:
                for slot in schedule:
                    rec=journal.get(slot,day)
                    if rec.get('plan') and rec['plan']!=slot:
                        unfinished=rec.get('phase') in ('preparing','prepared','starting','needs_review') and not rec.get('confirmed_at')
                        if unfinished:raise ValueError(slot['name']+': a prepared/started run keeps its original plan. Finish or review it before editing this program.')
            old=self.path.read_bytes() if self.path.exists() else None
            if old:(self.base/'settings.before-schedule-edit.json').write_bytes(old)
            cfg={**self.cfg,'schedule':schedule,'grace_minutes':grace}
            atomic_json(self.path,cfg);self.cfg=cfg
            # A skipped run without any external event can be scheduled later today.
            for slot in schedule:
                rec=journal.get(slot,now.date())
                if rec.get('phase') in ('new','missed') and not rec.get('yt_id') and not rec.get('fb_id'):
                    if slot_time(now.date(),slot)>now and not any(v=='sent' for v in rec.get('camera_states',{}).values()):
                        journal.data.pop(journal.key(slot,now.date()),None)
            if journal.path.exists():atomic_json(journal.path,journal.data)
            self.log('Schedule saved. Enable automation to apply your selected start, end and camera times.')

    def heartbeat(self):
        with self.lock:
            self.last_tick=now_ist().isoformat()
            if time.monotonic()-self.last_heartbeat>=15:
                atomic_json(self.base/'heartbeat.json',{'at':self.last_tick,'armed':self.armed,'arm_requested':bool(self.cfg.get('armed')),'mode':self.mode,'app_started_at':self.started_at})
                self.last_heartbeat=time.monotonic()

    def diagnostics(self):
        # Redact known stored secrets even if an older app put one in an error line.
        known=[]
        for key in SECRET_FIELDS | {'youtube_oauth','instagram_login_token','instagram_imgbb_key'}:
            value=self.vault.get(key)
            if value:known.append(value)
            if key=='youtube_oauth' and value:
                try:
                    oauth=json.loads(value)
                    known.extend(str(oauth[k]) for k in ('token','refresh_token','client_secret') if oauth.get(k))
                except (ValueError,TypeError):pass
        def clean(value):
            text=str(value)
            for secret in known:text=text.replace(secret,'[secret omitted]')
            text=re.sub(r'(?:https?|rtmps?)://[^\s]+','[address omitted]',text)
            text=re.sub(r'[A-Za-z0-9_/-]{40,}','[long value omitted]',text)
            return text
        with self.lock:
            journal=Journal(self.base/'journal.json');allowed={'phase','stage','scheduled_at','attempt_at','confirmed_at','ended_at','end_state','last_error','camera_states','yt_end_requested','fb_end_requested'}
            rows={k:{f:clean(v) if isinstance(v,str) else v for f,v in rec.items() if f in allowed} for k,rec in journal.data.items() if k[:10]>=(now_ist().date()-timedelta(days=7)).isoformat()}
            log_path=self.base/'activity.log';lines=[]
            if log_path.exists():
                with log_path.open('rb') as f:
                    f.seek(max(0,log_path.stat().st_size-64000));lines=f.read().decode('utf-8',errors='replace').splitlines()[-200:]
            return {'version':installed_version(Path(__file__).parent),'exported_at_ist':now_ist().isoformat(),'system':platform.system(),
                    'app_started_at':self.started_at,'armed_now':self.armed,'enabled_preference':bool(self.cfg.get('armed')),
                    'mode':self.mode,'last_tick':self.last_tick,'previous_session_heartbeat':self.previous_heartbeat,
                    'last_full_check':self.checked,'message':clean(self.message),'schedule':get_schedule(self.cfg),
                    'grace_minutes':self.cfg.get('grace_minutes',2),'recent_runs':rows,'recent_activity':[clean(line) for line in lines],
                    'note':'No credential values, OAuth JSON or stream keys included. Missing old heartbeat does not prove the PC was off.'}

    def run(self, mode):
        if mode not in ('check','arm','youtube'):raise ValueError('Unknown action.')
        with self.lock:
            self.require_idle()
            if self.visible.browser.recording:raise ValueError('Finish the visible workflow recording first.')
            if mode=='arm' and self.visible.config['mode']=='visible':self.visible.ready(self.cfg)
            if mode=='arm' and not any(s['enabled'] for s in get_schedule(self.cfg)):raise ValueError('Enable at least one program in Schedule.')
            self.operation_serial+=1;operation=self.operation_serial
            self.operation_results[operation]={'status':'running','message':'Checking connections.'}
            self.operation_results=dict(list(self.operation_results.items())[-50:])
            self.stop.clear();self.mode=mode;self.error=False
            self.message='Checking connections…' if mode!='youtube' else 'Complete Google sign-in on the Windows PC.'
            self.connections={k:'unchecked' for k in self.connections};self.checked=None
            if mode=='arm':self.cfg['armed']=True;atomic_json(self.path,self.cfg)
            cfg={**self.cfg,'_data_base':str(self.base)}
            def factory():
                if self.visible.config['mode']=='visible' and mode=='arm':
                    from visible import VisibleServices
                    return VisibleServices(cfg,self.vault,self.log,self.visible)
                return self.factory(cfg,self.vault,self.log)
            def work():
                service=None
                try:
                    if mode=='youtube':
                        service=self.factory(cfg,self.vault,self.log);service.yt.connect(interactive=True)
                        channel=service.yt.owned_channel();self.log('YouTube channel verified: '+channel['snippet']['title'])
                    else:
                        failures=0
                        while not self.stop.is_set():
                            service=factory()
                            try:service.check();break
                            except Exception as exc:
                                failures+=1
                                if mode!='arm' or not getattr(exc,'retryable',True) or failures>=5:raise
                                with self.lock:
                                    self.message=f'Waiting for connections; attempt {failures}/5 failed, retry in 30 seconds. '+safe_error(exc)
                                    self.log(self.message)
                                service.close();service=None
                                for _ in range(30):
                                    self.heartbeat()
                                    if self.stop.wait(1):break
                        with self.lock:
                            if not self.stop.is_set():self.checked=now_ist().isoformat()
                            if mode=='arm' and not self.stop.is_set():
                                self.armed=True;self.message='Automation enabled: your saved start, end and camera times are active.'
                                self.log(self.message)
                                self.operation_results[operation]={'status':'completed','message':'Automation enabled for the saved schedule; this does not mean live has started.'}
                        if mode=='arm' and not self.stop.is_set():
                            scheduler=Scheduler(service,Journal(self.base/'journal.json'),self.log,self.stop.is_set,slots=get_schedule(cfg),grace_seconds=int(cfg.get('grace_minutes',2))*60)
                            while not self.stop.is_set():
                                self.heartbeat();scheduler.tick(now_ist());self.stop.wait(1)
                except Exception as exc:
                    with self.lock:
                        self.error=True;self.armed=False;self.cfg['armed']=False
                        atomic_json(self.path,self.cfg);self.message=safe_error(exc);self.log(self.message)
                finally:
                    if service:
                        try:service.close()
                        except Exception:pass
                    with self.lock:
                        self.mode=''
                        if self.operation_results[operation]['status']=='running':
                            self.operation_results[operation]={'status':'failed' if self.error else 'cancelled' if self.stop.is_set() else 'completed','message':self.message[:200]}
                        if self.stop.is_set():self.message='Paused. Scheduled endings and camera actions are also paused; handle any live manually.'
                        elif not self.error:self.message='Connection operation finished. Automation is paused.'
                    self.heartbeat()
            self.worker=threading.Thread(target=work,daemon=True);self.worker.start()

    def shutdown(self):
        with self.lock: self.closing=True
        self.stop.set()  # Keep saved armed preference for the next Windows launch.
        self.remote.close();self.monitor.close();self.social.close()

class DashboardServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self, address, controller, pair_code=None):
        super().__init__(address, Handler)
        self.controller=controller; self.pair_code=pair_code or secrets.token_urlsafe(12)
        self.auth_lock=threading.Lock(); self.sessions={}; self.failures={}
        self.pair_expires=time.monotonic()+1800;self.pair_role='operator'
        self.allowed_hosts={'127.0.0.1','localhost'}
        controller.servers.append(self)
    def session(self, token):
        with self.auth_lock:
            item=self.sessions.get(token)
            if item and item['expires']>time.monotonic():return item
            self.sessions.pop(token,None)
        return None
    def server_close(self):
        if hasattr(self,'auth_lock'):
            with self.auth_lock:self.sessions.clear()
            with self.controller.lock:
                if self in self.controller.servers:self.controller.servers.remove(self)
        super().server_close()

class Handler(BaseHTTPRequestHandler):
    server_version='ISKCON-Dashboard'
    def log_message(self,*args):pass  # Never write URLs, cookies or credentials to logs.
    def setup(self):
        super().setup(); self.connection.settimeout(8)
    def local(self):return ipaddress.ip_address(self.client_address[0]).is_loopback
    def valid_host(self):
        host=self.headers.get('Host','')
        return host in {f'{h}:{self.server.server_port}' for h in self.server.allowed_hosts}
    def reply(self,status,data,ctype='application/json',cookie=None,csp=None):
        raw=json.dumps(data).encode() if ctype=='application/json' else data
        self.send_response(status); self.send_header('Content-Type',ctype)
        self.send_header('Content-Length',str(len(raw))); self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',csp or "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie:self.send_header('Set-Cookie',cookie)
        self.end_headers()
        try:self.wfile.write(raw)
        except (BrokenPipeError,ConnectionResetError):pass
    def auth(self):
        cookie=SimpleCookie()
        try:cookie.load(self.headers.get('Cookie',''))
        except Exception:return None
        self.token=cookie['iskcon_session'].value if 'iskcon_session' in cookie else ''
        return self.server.session(self.token)
    def do_GET(self):
        if not self.valid_host():return self.reply(403,{'error':'Invalid host.'})
        path=urlsplit(self.path).path
        if path=='/darshanflow.html':
            session=self.auth()
            if not session:return self.reply(401,{'error':'Pair this device to continue.'})
            if session.get('role')=='viewer':return self.reply(403,{'error':'DARSHANFLOW is available to operators only.'})
            # Scoped to this document only: its inline UI and direct HTTPS API
            # connectors work without relaxing the rest of the dashboard policy.
            policy="default-src 'none'; script-src 'unsafe-inline' 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; manifest-src data:; frame-ancestors 'self'; base-uri 'none'; form-action 'none'"
            return self.reply(200,(WEB/'darshanflow.html').read_bytes(),'text/html; charset=utf-8',csp=policy)
        if path=='/api/studio/state':
            session=self.auth()
            if not session:return self.reply(401,{'error':'Pair this device to continue.'})
            if session.get('role')=='viewer':return self.reply(403,{'error':'Posting is available to operators only.'})
            return self.reply(200,self.server.controller.studio.state(self.local()))
        if path=='/api/social/references':
            session=self.auth()
            if not session:return self.reply(401,{'error':'Pair this device to continue.'})
            if session.get('role')=='viewer':return self.reply(403,{'error':'References are available to operators only.'})
            try:return self.reply(200,self.server.controller.social.references())
            except (ValueError,OSError):return self.reply(409,{'error':'Could not read the private reference template.'})
        if path=='/api/social/state':
            session=self.auth()
            if not session:return self.reply(401,{'error':'Pair this device to continue.'})
            snapshot=self.server.controller.social.snapshot()
            if session.get('role')=='viewer':
                snapshot.update(assets=[],accounts={},instagram_id='',batch={},account_message='Status-only device. Post content is available to operators.')
                for job in snapshot['jobs']:
                    job.update(title='Social post',caption='',media=[],targets={})
                    job['results']={p:{k:v for k,v in r.items() if k in ('status','stage','percent')} for p,r in (job['results'] or {}).items()}
            return self.reply(200,snapshot)
        if path.startswith('/api/social/export/'):
            session=self.auth()
            if not session:return self.reply(401,{'error':'Pair this device to continue.'})
            if session.get('role')=='viewer':return self.reply(403,{'error':'Photo packages are available to operators only.'})
            try:archive=self.server.controller.social.export_post(path.rsplit('/',1)[1])
            except (ValueError,OSError) as exc:return self.reply(409,{'error':str(exc) if isinstance(exc,ValueError) else 'Could not prepare the photo package.'})
            try:
                archive.seek(0,2);size=archive.tell();archive.seek(0)
                self.send_response(200);self.send_header('Content-Type','application/zip')
                self.send_header('Content-Length',str(size));self.send_header('Content-Disposition','attachment; filename="Live-Desk-photo-post.zip"')
                self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers()
                for chunk in iter(lambda:archive.read(512*1024),b''):self.wfile.write(chunk)
            except (BrokenPipeError,ConnectionResetError,TimeoutError):pass
            finally:archive.close()
            return
        if path.startswith('/api/social/media/'):
            session=self.auth()
            if not session:return self.reply(401,{'error':'Pair this device to continue.'})
            if session.get('role')=='viewer':return self.reply(403,{'error':'Post media is available to operators only.'})
            return self.social_media(path.rsplit('/',1)[1])
        if path=='/api/diagnostics':
            if not self.auth():return self.reply(401,{'error':'Pair this device to continue.'})
            if not self.local():return self.reply(403,{'error':'Export diagnostics from the PC dashboard.'})
            return self.reply(200,self.server.controller.diagnostics())
        if path=='/api/backup':
            if not self.auth():return self.reply(401,{'error':'Pair this device to continue.'})
            if not self.local():return self.reply(403,{'error':'Export settings backups on the PC.'})
            return self.reply(200,self.server.controller.backup())
        if path=='/api/state':
            session=self.auth()
            if not session:return self.reply(401,{'error':'Pair this device to continue.'})
            try:return self.reply(200,{**self.server.controller.snapshot(self.local()),'csrf':session['csrf'],'role':session.get('role','operator')})
            except Exception:return self.reply(500,{'error':'Could not read app state. Check the PC.'})
        if path.startswith('/api/media/'):
            if not self.auth():return self.reply(401,{'error':'Pair this device to continue.'})
            try:
                raw,kind=self.server.controller.content.get(path.rsplit('/',1)[1]);return self.reply(200,raw,kind)
            except ValueError as exc:return self.reply(404,{'error':str(exc)})
        if path=='/api/devices':
            if not self.auth():return self.reply(401,{'error':'Pair this device to continue.'})
            if not self.local():return self.reply(403,{'error':'Manage paired devices on the PC.'})
            rows=[]
            for server in self.server.controller.servers:
                with server.auth_lock:
                    for token,item in server.sessions.items():
                        if item['expires']>time.monotonic():rows.append({k:item.get(k,'') for k in ('id','label','role','created_at')})
            return self.reply(200,{'devices':rows,'pairing_minutes_left':max(0,int((self.server.pair_expires-time.monotonic())/60))})
        assets={'/takeover.js':('takeover.js','text/javascript; charset=utf-8'),'/':('index.html','text/html; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/icon.svg':('icon.svg','image/svg+xml'),'/features.js':('features.js','text/javascript; charset=utf-8'),'/darshanflow-host.js':('darshanflow-host.js','text/javascript; charset=utf-8'),'/darshanflow-host.css':('darshanflow-host.css','text/css; charset=utf-8'),'/darshanflow-theme.css':('darshanflow-theme.css','text/css; charset=utf-8')}
        assets.update({'/darshanflow-studio.js':('darshanflow-studio.js','text/javascript; charset=utf-8'),'/darshanflow-studio.css':('darshanflow-studio.css','text/css; charset=utf-8')})
        if path not in assets:return self.reply(404,{'error':'Not found.'})
        name,ctype=assets[path];return self.reply(200,(WEB/name).read_bytes(),ctype)
    def social_media(self,ident):
        try:
            path,asset=self.server.controller.social.media_path(ident);size=asset['size'];start=0;end=size-1;status=200
            request_range=self.headers.get('Range','')
            if request_range:
                match=re.fullmatch(r'bytes=(\d+)-(\d*)',request_range)
                if not match:raise ValueError('Use a single byte range.')
                start=int(match[1]);end=min(size-1,int(match[2]) if match[2] else size-1);status=206
                if not 0<=start<=end<size:raise ValueError('Invalid media byte range.')
            self.send_response(status);self.send_header('Content-Type',asset['type']);self.send_header('Content-Length',str(end-start+1));self.send_header('Accept-Ranges','bytes');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
            self.end_headers()
            with path.open('rb') as f:
                f.seek(start);remaining=end-start+1
                while remaining:
                    chunk=f.read(min(512*1024,remaining))
                    if not chunk:break
                    self.wfile.write(chunk);remaining-=len(chunk)
        except (ValueError,OSError) as exc:
            if isinstance(exc,ValueError):return self.reply(404,{'error':str(exc)})

    def do_POST(self):
        if not self.valid_host():return self.reply(403,{'error':'Invalid host.'})
        # No cross-origin writes, including requests from malicious sites targeting the LAN.
        if self.headers.get('Origin')!='http://'+self.headers.get('Host',''):
            return self.reply(403,{'error':'Invalid origin.'})
        if self.headers.get('Content-Type','').split(';')[0]!='application/json':
            return self.reply(415,{'error':'JSON required.'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            path=urlsplit(self.path).path
            limit=800000 if path=='/api/social/upload/chunk' and self.auth() else 2800000 if path=='/api/media/upload' and self.local() and self.auth() else 65536
            if not 0<size<=limit:raise ValueError()
            data=json.loads(self.rfile.read(size))
            if not isinstance(data,dict):raise ValueError()
        except Exception:return self.reply(400,{'error':'Invalid request.'})
        path=urlsplit(self.path).path
        if path=='/api/login':return self.login(data)
        session=self.auth()
        if not session:return self.reply(401,{'error':'Pair this device to continue.'})
        if not secrets.compare_digest(self.headers.get('X-CSRF-Token',''),session['csrf']):
            return self.reply(403,{'error':'Session check failed. Refresh this page.'})
        c=self.server.controller
        try:
            if path=='/api/logout':
                with self.server.auth_lock:self.server.sessions.pop(self.token,None)
                return self.reply(200,{'ok':True},cookie='iskcon_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
            if session.get('role')=='viewer':return self.reply(403,{'error':'This device has view-only access. Pair with an operator code to control the PC.'})
            if path.startswith('/api/studio/'):
                if path in ('/api/studio/instagram','/api/studio/check') and not self.local():return self.reply(403,{'error':'Set up posting accounts on this PC.'})
                routes={'/api/studio/save':c.studio.save,'/api/studio/instagram':c.studio.save_instagram,'/api/studio/check':c.studio.check,'/api/studio/prepare':c.studio.prepare,'/api/studio/send':c.studio.send,'/api/studio/receipt':c.studio.receipt}
                if path not in routes:return self.reply(404,{'error':'Posting action not found.'})
                return self.reply(200,routes[path](data))
            if path.startswith('/api/social/'):
                if path in ('/api/social/account','/api/social/check') and not self.local():return self.reply(403,{'error':'Set up posting accounts on the PC.'})
                routes={'/api/social/upload/begin':c.social.begin_upload,'/api/social/upload/chunk':c.social.upload_chunk,'/api/social/upload/finish':c.social.finish_upload,'/api/social/asset':c.social.asset_update,'/api/social/assets/bulk':c.social.assets_bulk,'/api/social/draft':c.social.draft,'/api/social/batch':c.social.batch,'/api/social/references':c.social.references,'/api/social/action':c.social.command,'/api/social/account':c.social.save_account,'/api/social/reconcile':c.social.reconcile}
                if path=='/api/social/check':return self.reply(202,c.social.check_accounts())
                if path not in routes:return self.reply(404,{'error':'Posting action not found.'})
                return self.reply(200,routes[path](data))
            if path=='/api/devices/revoke':
                if not self.local():return self.reply(403,{'error':'Manage paired devices on the PC.'})
                ident=data.get('id')
                for server in c.servers:
                    with server.auth_lock:
                        for token,item in list(server.sessions.items()):
                            if item.get('id')==ident:server.sessions.pop(token,None)
                return self.reply(200,{'ok':True})
            if path=='/api/devices/rotate':
                if not self.local():return self.reply(403,{'error':'Manage pairing on the PC.'})
                role=data.get('role','operator')
                if role not in ('operator','viewer'):raise ValueError('Choose operator or viewer.')
                code=secrets.token_urlsafe(12)
                for server in c.servers:
                    with server.auth_lock:server.pair_code=code;server.pair_expires=time.monotonic()+1800;server.pair_role=role
                return self.reply(200,{'code':code,'role':role,'minutes':30})
            if path=='/api/desktop/action':
                if not self.local():return self.reply(403,{'error':'Use PC controls on the Windows PC.'})
                with c.lock:
                    if c.closing or c.maintenance:raise ValueError('Wait for shutdown or the update to finish.')
                    if not c.desktop_host:raise ValueError('PC controls require the Windows app.')
                    c.desktop_host.submit(data)
                return self.reply(202,{'ok':True,'message':'PC action queued. Watch the PC controls status.'})
            if path=='/api/media/upload':
                if not self.local():return self.reply(403,{'error':'Upload thumbnails on the PC.'})
                with c.lock:
                    c.require_idle();result=c.content.add(data.get('data'))
                return self.reply(200,result)
            if path=='/api/content/preview':
                from datetime import date
                slot=next((x for x in get_schedule(c.cfg) if x['id']==data.get('slot')),None)
                if not slot:raise ValueError('Choose a saved program.')
                return self.reply(200,c.content.preview(slot,date.fromisoformat(data.get('date',''))))
            if path.startswith('/api/updates/') and path!='/api/updates/open':
                if not self.local():return self.reply(403,{'error':'Manage updates on this PC.'})
                action=path.rsplit('/',1)[1]
                if action not in ('check','install','rollback'):raise ValueError('Unknown update action.')
                getattr(c.updates,action)(data)
                return self.reply(202,{'ok':True})
            if path=='/api/updates/open':
                if not self.local():return self.reply(403,{'error':'Manage app updates on the Windows PC.'})
                if not c.open_updates:raise ValueError('Open the Windows launcher to manage updates.')
                c.open_updates()
            elif path=='/api/schedule':
                if data.get('confirmed') is not True:raise ValueError('Confirm the schedule before saving.')
                c.save_schedule(data)
            elif path=='/api/restore':
                if not self.local():return self.reply(403,{'error':'Restore settings on the Windows PC.'})
                c.restore(data)
            elif path=='/api/remote/settings':
                if not self.local():return self.reply(403,{'error':'Enroll remote access on the Windows PC.'})
                c.save_remote(data)
            elif path=='/api/runs':c.review_run(data)
            elif path=='/api/takeover':c.take_control(data)
            elif path=='/api/settings':
                if not self.local():return self.reply(403,{'error':'Change credentials on the Windows PC.'})
                c.save(data)
            elif path in ('/api/visible/save','/api/visible/browser'):
                if not self.local():return self.reply(403,{'error':'Configure browser workflows on the Windows PC.'})
                if path.endswith('/save'):c.save_visible(data)
                else:c.visible_browser(data)
            elif path=='/api/action':
                action=data.get('action')
                if action=='pause':c.pause()
                elif action in ('arm','retry'):
                    if data.get('confirmed') is not True:raise ValueError('Confirmation required.')
                    if action=='arm':c.run('arm')
                    else:c.retry(data.get('slot'))
                elif action=='check':c.run('check')
                elif action=='youtube':
                    if not self.local():return self.reply(403,{'error':'Connect YouTube on the PC.'})
                    c.run('youtube')
                else:raise ValueError('Unknown action.')
            else:return self.reply(404,{'error':'Not found.'})
            return self.reply(200,{'ok':True})
        except ValueError as exc:return self.reply(409,{'error':str(exc)})
        except Exception:return self.reply(500,{'error':'Operation failed. Check the Windows app and saved settings.'})
    def login(self,data):
        ip=self.client_address[0]; now=time.monotonic()
        with self.server.auth_lock:
            self.server.failures={k:v for k,v in self.server.failures.items() if v[1]>now}
            count,until=self.server.failures.get(ip,(0,now+300))
            if count>=8:return self.reply(429,{'error':'Too many attempts. Try again in five minutes.'})
            code=data.get('code','')
            if not self.local() and now>self.server.pair_expires:return self.reply(401,{'error':'Pairing code expired. On the PC, open Mobile access and generate a new 30-minute code.'})
            if not isinstance(code,str) or not code.isascii() or not secrets.compare_digest(code,self.server.pair_code):
                self.server.failures[ip]=(count+1,until)
                return self.reply(401,{'error':'Incorrect pairing code. Use the code shown on the Windows PC.'})
            self.server.failures.pop(ip,None)
            self.server.sessions={k:v for k,v in self.server.sessions.items() if v['expires']>now}
            if len(self.server.sessions)>=64:self.server.sessions.pop(next(iter(self.server.sessions)))
            token=secrets.token_urlsafe(32); csrf=secrets.token_urlsafe(24)
            label='PC browser' if self.local() else self.headers.get('User-Agent','Phone/browser')[:120]
            self.server.sessions[token]={'csrf':csrf,'expires':now+43200,'id':secrets.token_hex(12),
                'label':label,'role':'owner' if self.local() else self.server.pair_role,'created_at':now_ist().isoformat()}
        self.reply(200,{'ok':True},cookie=f'iskcon_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200')

def lan_addresses():
    addresses=set()
    try:
        for item in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET):
            ip=item[4][0]
            if ipaddress.ip_address(ip).is_private and not ipaddress.ip_address(ip).is_loopback:addresses.add(ip)
    except OSError:pass
    return sorted(addresses)
