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
from schedule_config import get_schedule,validate_schedule
from core import SLOTS, Journal, Scheduler, atomic_json, now_ist, slot_time

WEB = Path(__file__).parent / 'web'
SECRET_FIELDS = {'obs_password', 'facebook_page_token', 'camera_password'}

def safe_error(exc):
    from connections import SetupError
    return str(exc) if isinstance(exc, SetupError) else f'{type(exc).__name__}: operation failed. Check settings and network on the PC.'

class Controller:
    def __init__(self, base=BASE, factory=None, vault=None):
        self.base = Path(base); self.base.mkdir(parents=True, exist_ok=True)
        self.path = self.base / 'settings.json'
        self.cfg = {**DEFAULTS, **(json.loads(self.path.read_text('utf-8')) if self.path.exists() else {})}
        from connections import Services, Vault
        self.factory = factory or Services
        self.vault = vault if vault is not None else Vault()
        self.lock = threading.RLock(); self.stop = threading.Event()
        self.maintenance = False; self.open_updates = None
        self.worker = None; self.mode = ''; self.armed = False; self.closing = False
        self.logs = deque(maxlen=160); self.message = 'Ready. Check connections before enabling daily starts.'
        self.checked = None; self.error = False
        self.connections = {k: 'unchecked' for k in ('obs','youtube','facebook','camera')}
        self.mobile_urls = []; self.desktop_url = ''; self.mobile_enabled = False
        self.started_at=now_ist().isoformat();self.last_tick=None;self.last_heartbeat=0
        self.previous_heartbeat=json.loads((self.base/'heartbeat.json').read_text('utf-8')) if (self.base/'heartbeat.json').exists() else None
        self.log('Live Desk v0.5.1 opened. Saved enabled preference: '+str(bool(self.cfg.get('armed')))+'.')

    def log(self, message):
        message = str(message)
        with self.lock:
            for prefix, key in [('OBS connected.', 'obs'), ('YouTube channel verified:', 'youtube'),
                                ('Facebook Page verified:', 'facebook'), ('Camera reachable;', 'camera')]:
                if message.startswith(prefix): self.connections[key] = 'verified'
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
                              'phase': rec.get('phase','waiting') if slot['enabled'] else 'disabled', 'title': rec.get('title',''),
                              'end_at':rec.get('plan',slot)['end_at'],'end_next_day':rec.get('plan',slot)['end_next_day'],'enabled':slot['enabled'],
                              'run_start_at':rec.get('plan',slot)['at'],
                              'camera_states':rec.get('camera_states',{}),'end_state':rec.get('end_state',''),
                              'last_error':rec.get('last_error',''),'stage':rec.get('stage',''),
                              'patrol': rec.get('patrol_result',''), 'patrol_due': rec.get('patrol_due','')})
            future = [(slot_time(now.date(), s),s) for s in schedule if s['enabled'] and slot_time(now.date(),s)>now]
            active=[s for s in schedule if s['enabled']]
            due,next_slot=future[0] if future else ((slot_time(now.date()+timedelta(days=1),active[0]),active[0]) if active else (now,{'name':'No programs enabled','at':'—'}))
            issue=next((x for x in slots if x.get('last_error') and (x['phase'] in ('needs_review','missed') or x['end_state'] in ('needs_review','missed') or 'needs_review' in x['camera_states'].values())),None)
            return {'now':now.isoformat(), 'date':now.strftime('%A, %d %B %Y'),
                    'schedule':schedule,'grace_minutes':int(self.cfg.get('grace_minutes',2)),
                    'last_tick':self.last_tick,'started_at':self.started_at,'arm_requested':bool(self.cfg.get('armed')),
                    'armed':self.armed, 'busy':bool(self.maintenance or (self.worker and self.worker.is_alive())),
                    'app_version':json.loads((Path(__file__).parent/'version.json').read_text('utf-8'))['version'],
                    'mode':self.mode, 'message':issue['name']+': '+issue['last_error'] if issue else self.message, 'error':self.error or bool(issue),
                    'connections':dict(self.connections), 'checked':self.checked,
                    'slots':slots, 'next':{'name':next_slot['name'],'due':due.isoformat(),'at':next_slot['at']},
                    'logs':list(self.logs), 'local':local, 'mobile_enabled':self.mobile_enabled,
                    'mobile_urls':self.mobile_urls if local else [],
                    'settings':{k:self.cfg.get(k,v) for k,v in DEFAULTS.items() if k!='armed'} if local else None}

    def pause(self):
        # Cancellation is set before taking the state lock, including during connection checks.
        self.stop.set()
        with self.lock:
            self.stop.set()
            self.armed = False; self.cfg['armed'] = False; atomic_json(self.path, self.cfg)
            self.message = 'Paused: future starts, scheduled ends and camera actions are stopped. An operation already underway may finish.'
            self.log(self.message)

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
            for key in SECRET_FIELDS:
                value = values.get(key,'')
                if not isinstance(value,str) or len(value)>12000: raise ValueError('Invalid credential.')
            for key in SECRET_FIELDS:
                if values.get(key): self.vault.set(key, values[key].strip())
            atomic_json(self.path,cfg); self.cfg = cfg
            self.checked=None; self.connections={k:'unchecked' for k in self.connections}
            self.log('Settings saved. Blank secret fields kept their saved values.')

    def require_idle(self):
        if self.closing: raise ValueError('App is closing.')
        if self.maintenance: raise ValueError('An app update is in progress.')
        if self.worker and self.worker.is_alive(): raise ValueError('Pause automation and wait for the current operation to finish first.')

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
            journal.put(slot,now.date(),phase='new')
            self.log('Slot reset after manual review. Enable daily starts to retry within its scheduled window.')

    def save_schedule(self,data):
        with self.lock:
            self.require_idle()
            schedule=validate_schedule(data.get('schedule'))
            grace=data.get('grace_minutes',2)
            if type(grace)!=int or not 1<=grace<=15:raise ValueError('Late-start allowance must be 1–15 minutes.')
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
        for key in SECRET_FIELDS | {'youtube_oauth'}:
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
            return {'version':'0.3','exported_at_ist':now_ist().isoformat(),'system':platform.system(),
                    'app_started_at':self.started_at,'armed_now':self.armed,'enabled_preference':bool(self.cfg.get('armed')),
                    'mode':self.mode,'last_tick':self.last_tick,'previous_session_heartbeat':self.previous_heartbeat,
                    'last_full_check':self.checked,'message':clean(self.message),'schedule':get_schedule(self.cfg),
                    'grace_minutes':self.cfg.get('grace_minutes',2),'recent_runs':rows,'recent_activity':[clean(line) for line in lines],
                    'note':'No credential values, OAuth JSON or stream keys included. Missing old heartbeat does not prove the PC was off.'}

    def run(self, mode):
        if mode not in ('check','arm','youtube'):raise ValueError('Unknown action.')
        with self.lock:
            self.require_idle()
            if mode=='arm' and not any(s['enabled'] for s in get_schedule(self.cfg)):raise ValueError('Enable at least one program in Schedule.')
            self.stop.clear();self.mode=mode;self.error=False
            self.message='Checking connections…' if mode!='youtube' else 'Complete Google sign-in on the Windows PC.'
            self.connections={k:'unchecked' for k in self.connections};self.checked=None
            if mode=='arm':self.cfg['armed']=True;atomic_json(self.path,self.cfg)
            cfg=dict(self.cfg)
            def work():
                service=None
                try:
                    if mode=='youtube':
                        service=self.factory(cfg,self.vault,self.log);service.yt.connect(interactive=True)
                        channel=service.yt.owned_channel();self.log('YouTube channel verified: '+channel['snippet']['title'])
                    else:
                        while not self.stop.is_set():
                            service=self.factory(cfg,self.vault,self.log)
                            try:service.check();break
                            except Exception as exc:
                                if mode!='arm':raise
                                with self.lock:
                                    self.message='Waiting for connections; retry in 30 seconds. '+safe_error(exc)
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
                        if self.stop.is_set():self.message='Paused. Scheduled endings and camera actions are also paused; handle any live manually.'
                        elif not self.error:self.message='Connection operation finished. Automation is paused.'
                    self.heartbeat()
            self.worker=threading.Thread(target=work,daemon=True);self.worker.start()

    def shutdown(self):
        with self.lock: self.closing=True
        self.stop.set()  # Keep saved armed preference for the next Windows launch.

class DashboardServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self, address, controller, pair_code=None):
        super().__init__(address, Handler)
        self.controller=controller; self.pair_code=pair_code or secrets.token_urlsafe(12)
        self.auth_lock=threading.Lock(); self.sessions={}; self.failures={}
        self.allowed_hosts={'127.0.0.1','localhost'}
    def session(self, token):
        with self.auth_lock:
            item=self.sessions.get(token)
            if item and item['expires']>time.monotonic():return item
            self.sessions.pop(token,None)
        return None

class Handler(BaseHTTPRequestHandler):
    server_version='ISKCON-Dashboard'
    def log_message(self,*args):pass  # Never write URLs, cookies or credentials to logs.
    def setup(self):
        super().setup(); self.connection.settimeout(8)
    def local(self):return ipaddress.ip_address(self.client_address[0]).is_loopback
    def valid_host(self):
        host=self.headers.get('Host','')
        return host in {f'{h}:{self.server.server_port}' for h in self.server.allowed_hosts}
    def reply(self,status,data,ctype='application/json',cookie=None):
        raw=json.dumps(data).encode() if ctype=='application/json' else data
        self.send_response(status); self.send_header('Content-Type',ctype)
        self.send_header('Content-Length',str(len(raw))); self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
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
        if path=='/api/diagnostics':
            if not self.auth():return self.reply(401,{'error':'Pair this device to continue.'})
            if not self.local():return self.reply(403,{'error':'Export diagnostics from the PC dashboard.'})
            return self.reply(200,self.server.controller.diagnostics())
        if path=='/api/state':
            session=self.auth()
            if not session:return self.reply(401,{'error':'Pair this device to continue.'})
            try:return self.reply(200,{**self.server.controller.snapshot(self.local()),'csrf':session['csrf']})
            except Exception:return self.reply(500,{'error':'Could not read app state. Check the PC.'})
        assets={'/':('index.html','text/html; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/icon.svg':('icon.svg','image/svg+xml')}
        if path not in assets:return self.reply(404,{'error':'Not found.'})
        name,ctype=assets[path];return self.reply(200,(WEB/name).read_bytes(),ctype)
    def do_POST(self):
        if not self.valid_host():return self.reply(403,{'error':'Invalid host.'})
        # No cross-origin writes, including requests from malicious sites targeting the LAN.
        if self.headers.get('Origin')!='http://'+self.headers.get('Host',''):
            return self.reply(403,{'error':'Invalid origin.'})
        if self.headers.get('Content-Type','').split(';')[0]!='application/json':
            return self.reply(415,{'error':'JSON required.'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=65536:raise ValueError()
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
            if path=='/api/updates/open':
                if not self.local():return self.reply(403,{'error':'Manage app updates on the Windows PC.'})
                if not c.open_updates:raise ValueError('Open the Windows launcher to manage updates.')
                c.open_updates()
            elif path=='/api/schedule':
                if data.get('confirmed') is not True:raise ValueError('Confirm the schedule before saving.')
                c.save_schedule(data)
            elif path=='/api/settings':
                if not self.local():return self.reply(403,{'error':'Change credentials on the Windows PC.'})
                c.save(data)
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
            if not isinstance(code,str) or not code.isascii() or not secrets.compare_digest(code,self.server.pair_code):
                self.server.failures[ip]=(count+1,until)
                return self.reply(401,{'error':'Incorrect pairing code. Use the code shown on the Windows PC.'})
            self.server.failures.pop(ip,None)
            self.server.sessions={k:v for k,v in self.server.sessions.items() if v['expires']>now}
            if len(self.server.sessions)>=64:self.server.sessions.pop(next(iter(self.server.sessions)))
            token=secrets.token_urlsafe(32); csrf=secrets.token_urlsafe(24)
            self.server.sessions[token]={'csrf':csrf,'expires':now+43200}
        self.reply(200,{'ok':True},cookie=f'iskcon_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200')

def lan_addresses():
    addresses=set()
    try:
        for item in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET):
            ip=item[4][0]
            if ipaddress.ip_address(ip).is_private and not ipaddress.ip_address(ip).is_loopback:addresses.add(ip)
    except OSError:pass
    return sorted(addresses)
