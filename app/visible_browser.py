"""Headful browser actions; no cookies, screenshots or input values exported."""
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from connections import SetupError


def origin(url):
    u = urlsplit(url)
    if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password:
        raise SetupError('Visible browser address must be an HTTP(S) address without credentials.')
    return (u.scheme, u.hostname.lower(), u.port or (443 if u.scheme == 'https' else 80))


def desktop_ready():
    if os.name != 'nt':
        raise SetupError('Visible mode needs the logged-in Windows livestream desktop.')
    import ctypes
    from ctypes import wintypes
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    user.OpenInputDesktop.restype = wintypes.HANDLE
    user.SwitchDesktop.argtypes = [wintypes.HANDLE]
    user.CloseDesktop.argtypes = [wintypes.HANDLE]
    handle = user.OpenInputDesktop(0, False, 0x0100)
    if not handle:
        raise SetupError('Unlock the Windows desktop and finish any UAC prompt. Visible actions are stopped.')
    try:
        if not user.SwitchDesktop(handle):
            raise SetupError('The interactive Windows desktop is unavailable. Visible actions are stopped.')
    finally:
        user.CloseDesktop(handle)


class CDP:
    def __init__(self, address):
        import websocket
        self.ws = websocket.create_connection(address, timeout=4, suppress_origin=True)
        self.sequence = 0
        self.events = []

    def call(self, method, **params):
        self.sequence += 1
        ident = self.sequence
        self.ws.send(json.dumps({'id': ident, 'method': method, 'params': params}))
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            reply = json.loads(self.ws.recv())
            if reply.get('method') == 'Runtime.bindingCalled':
                if len(self.events)<500 and len(reply.get('params',{}).get('payload',''))<2000:
                    self.events.append(reply['params'])
            if reply.get('id') == ident:
                if 'error' in reply:
                    raise SetupError('The visible page changed or refused the requested browser action. Review it on the PC.')
                return reply.get('result', {})
        raise SetupError('Visible browser did not respond. Inspect the PC; no automatic replay was sent.')

    def evaluate(self, expression):
        result = self.call('Runtime.evaluate', expression=expression, returnByValue=True)
        if result.get('exceptionDetails'):
            raise SetupError('This page cannot be inspected by the visible adapter. Use a supported page, not an embedded/legacy plugin.')
        return result.get('result', {}).get('value')

    def close(self):
        self.ws.close()


class BrowserCDP:
    """One consented browser socket, with isolated flattened page sessions.

    Chrome's inspect server need not offer /json HTTP discovery. Reading only
    DevToolsActivePort supplies its loopback socket; Chrome handles permission.
    Keep that socket until explicit disconnect/app exit, not one per UI click.
    """
    def __init__(self, address):
        import websocket
        self.ws = websocket.create_connection(address, timeout=60, suppress_origin=True,
                                              http_no_proxy=['127.0.0.1', 'localhost'])
        self.ws.settimeout(1)
        self.sequence = 0
        self.lock = threading.RLock()
        self.call_lock = threading.Lock()
        self.pending = {}
        self.sessions = {}
        self.closed = False
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        import websocket
        try:
            while not self.closed:
                try: raw = self.ws.recv()
                except websocket.WebSocketTimeoutException: continue
                if not raw: break
                if len(raw) > 2_000_000: break
                reply = json.loads(raw)
                with self.lock:
                    if 'id' in reply and reply['id'] in self.pending:
                        item = self.pending[reply['id']]
                        item['reply'] = reply; item['ready'].set()
                    elif reply.get('method') == 'Runtime.bindingCalled':
                        page = self.sessions.get(reply.get('sessionId'))
                        data = reply.get('params', {})
                        if page is not None and len(page.events) < 500 and len(data.get('payload', '')) < 2000:
                            page.events.append(data)
        except Exception:
            pass
        finally:
            self.close()

    def call(self, method, **params):
        return self._call(method, params)

    def _call(self, method, params, session=None):
        with self.call_lock:
            with self.lock:
                if self.closed: raise SetupError('Chrome disconnected. Connect my Chrome locally before retrying; no browser was launched.')
                self.sequence += 1
                ident = self.sequence
                item = {'ready': threading.Event()}
                self.pending[ident] = item
            try:
                packet = {'id': ident, 'method': method, 'params': params}
                if session: packet['sessionId'] = session
                self.ws.send(json.dumps(packet))
                if not item['ready'].wait(15) or 'reply' not in item:
                    self.close()
                    raise SetupError('Chrome connection interrupted. Inspect the page and reconnect locally; no automatic replay was sent.')
                reply = item['reply']
                if 'error' in reply:
                    raise SetupError('Chrome refused this browser action. Inspect the selected tab before retrying.')
                return reply.get('result', {})
            except SetupError:
                raise
            except Exception:
                self.close()
                raise SetupError('Chrome connection interrupted. Reconnect locally; no automatic replay was sent.') from None
            finally:
                with self.lock: self.pending.pop(ident, None)

    def page(self, target):
        session = self.call('Target.attachToTarget', targetId=target, flatten=True)['sessionId']
        page = ChromePage(self, session)
        with self.lock: self.sessions[session] = page
        return page

    def close(self):
        with self.lock:
            if self.closed: return
            self.closed = True
            for item in self.pending.values(): item['ready'].set()
        try: self.ws.close()
        except Exception: pass


class ChromePage(CDP):
    def __init__(self, browser, session):
        self.browser, self.session = browser, session
        self.events = []
        self.closed = False

    def call(self, method, **params):
        if self.closed: raise SetupError('This Chrome page session is closed. Inspect the tab before retrying.')
        return self.browser._call(method, params, self.session)

    def close(self):
        if self.closed: return
        self.closed = True
        with self.browser.lock: self.browser.sessions.pop(self.session, None)
        if not self.browser.closed:
            try: self.browser.call('Target.detachFromTarget', sessionId=self.session)
            except SetupError: pass


# Input values are deliberately never read. Passwords and authentication controls
# must be handled by the operator before recording. Targets use unique semantic
# labels or IDs, not absolute screen coordinates saved from another machine.
RECORDER = r'''(() => {
if(window.__liveDeskRecorder) return;
window.__liveDeskRecorder=true;
const forbidden=/password|passcode|secret|token|stream.?key|verification|one.?time|otp|email|sign.?in|log.?in/i;
const controls='button,input,textarea,select,a,[role="button"],[role="tab"],[contenteditable="true"],ytcp-button,tp-yt-paper-button';
const roots=new Set(),seen=new WeakSet();
let count=0,ignored=0,badge=null;
function editable(n){return n.isContentEditable || ['INPUT','TEXTAREA','SELECT'].includes(n.tagName);}
function label(n){return (n.getAttribute('aria-label')||n.labels?.[0]?.innerText||n.getAttribute('placeholder')||(editable(n)?'':n.innerText)||'').trim();}
function emit(item){window.liveDeskCapture(JSON.stringify({...item,origin:location.origin}));}
function show(){
 if(!document.body)return;
 if(!badge||!badge.isConnected){
  badge=document.createElement('aside');badge.setAttribute('data-live-desk-recorder','true');
  Object.assign(badge.style,{position:'fixed',top:'8px',left:'8px',zIndex:'2147483647',padding:'8px 12px',background:'#153e32',color:'#fff',font:'14px sans-serif',border:'2px solid #f8b36b',borderRadius:'6px',pointerEvents:'none'});
  document.body.append(badge);
 }
 badge.textContent='LIVE DESK RECORDING • '+count+' captured on this page'+(ignored?' • '+ignored+' unsupported':'');
}
function target(event){
 const path=event.composedPath().filter(n=>n instanceof Element);
 // Use the actual inner control, not the retargeted shadow host.
 let n=path.find(n=>n.matches(controls));
 const passive=!n;
 if(!n && event.type==='click')n=path.find(n=>n.matches('span,div,yt-formatted-string')&&n.children.length===0);
 if(!n || n.closest('[data-live-desk-recorder]'))return null;
 if(n.type==='password'||forbidden.test(label(n)+' '+n.id+' '+n.name+' '+n.type))return null;
 if(passive && (!label(n)||label(n).length>160||/EAA[A-Za-z0-9]{20}|ya29\.|[A-Za-z0-9_-]{50}/.test(label(n))))return null;
 if(n.tagName==='SELECT'||n.type==='file')return null;
 const text=label(n).slice(0,160);
 let loc=null;
 if(n.id && !/[0-9]{5}/.test(n.id))loc={css:'#'+CSS.escape(n.id),label:text};
 else if(text && ['button','input','textarea','a','div','span','ytcp-button','tp-yt-paper-button','yt-formatted-string'].includes(n.tagName.toLowerCase()))loc={tag:n.tagName.toLowerCase(),text};
 return loc?{locator:loc,passive,text}:null;
}
function capture(e){
 if(!window.__liveDeskRecorder||!e.isTrusted||seen.has(e))return;
 seen.add(e);
 const actual=e.composedPath()[0];
 if(e.type==='focusout' && !actual?.isContentEditable)return;
 const found=target(e);
 if(!found){ignored++;emit({kind:'skipped'});show();return;}
 const kind=found.passive?'assert':e.type==='click'?'click':'fill';
 emit({kind,locator:found.locator,...(kind==='assert'?{text:found.text}:{})});count++;show();
}
function scan(){
 const pending=[document];
 for(let i=0;i<pending.length;i++){
  const root=pending[i];
  if(!roots.has(root)){
   roots.add(root);
   for(const type of ['click','change','focusout'])root.addEventListener(type,capture,true);
  }
  for(const n of root.querySelectorAll('*'))if(n.shadowRoot)pending.push(n.shadowRoot);
 }
 show();
}
window.__liveDeskStopRecorder=()=>{
 window.__liveDeskRecorder=false;clearInterval(timer);
 for(const root of roots)for(const type of ['click','change','focusout'])root.removeEventListener(type,capture,true);
 badge?.remove();
};
const timer=setInterval(scan,200);scan();emit({kind:'ready'});
})();''' 


def target_script(locator, body):
    # locator is data, never JavaScript or an arbitrary expression from a client.
    return r'''(() => {
const loc=LOCATOR;
const roots=[document];for(let i=0;i<roots.length;i++)for(const n of roots[i].querySelectorAll('*'))if(n.shadowRoot)roots.push(n.shadowRoot);
let found=[];for(const root of roots){
 for(const n of root.querySelectorAll(loc.css||loc.tag)){
 const label=(n.getAttribute('aria-label')||n.labels?.[0]?.innerText||n.getAttribute('placeholder')||n.innerText||'').trim();
 if((loc.css||label===loc.text)&&n.getClientRects().length)found.push(n);
 }}
if(found.length!==1)return {ok:false,reason:found.length?'ambiguous':'missing'};
const n=found[0];if(n.disabled||n.getAttribute('aria-disabled')==='true')return {ok:false,reason:'disabled'};
BODY
})();'''.replace('LOCATOR', json.dumps(locator)).replace('BODY', body)


class Browser:
    def __init__(self, base, cancelled=lambda: False, ready=desktop_ready):
        self.base = Path(base)
        self.cancelled, self.ready = cancelled, ready
        self.lock = threading.RLock()
        self.process = None
        self.port = None
        self.tabs = {}
        self.sites = {}
        self.recording = None
        self.source = 'dedicated'
        self.chrome = None

    def select(self, source):
        if source not in ('dedicated', 'running_chrome'):
            raise ValueError('Choose the Live Desk browser or your running Chrome.')
        if self.recording: raise ValueError('Finish recording before changing the browser.')
        with self.lock:
            if source != self.source:
                self.disconnect()
                self.source = source

    def disconnect(self):
        if self.recording: raise ValueError('Finish recording before disconnecting Chrome.')
        with self.lock:
            if self.chrome: self.chrome.close()
            self.chrome = None
            self.tabs = {}; self.sites = {}

    def connect_chrome(self):
        with self.lock:
            self.guard()
            if self.source != 'running_chrome':
                raise SetupError('Save browser choice as My running Chrome before connecting.')
            if self.chrome and not self.chrome.closed:
                self.ensure(); return
            # Read the debug marker only. Never copy/read cookies, Local State,
            # Preferences or website data from the ordinary Chrome profile.
            root = os.environ.get('LOCALAPPDATA')
            marker = Path(root)/'Google/Chrome/User Data/DevToolsActivePort' if root else None
            try:
                lines = [line.strip() for line in marker.read_text().splitlines() if line.strip()] if marker else []
                if len(lines) != 2 or not lines[0].isdigit(): raise ValueError()
                port = int(lines[0])
                if not 1 <= port <= 65535 or not re.fullmatch(r'/devtools/browser/[A-Za-z0-9-]+', lines[1]): raise ValueError()
            except (OSError, ValueError):
                raise SetupError('Cannot find the running Chrome debug connection. In normal Chrome enable chrome://inspect/#remote-debugging, then Connect my Chrome again. No separate browser was opened.') from None
            connection = None
            try:
                connection = BrowserCDP(f'ws://127.0.0.1:{port}'+lines[1])
                info = connection.call('Browser.getVersion')
                if not re.match(r'^(HeadlessChrome|Chrome)/[0-9]+', info.get('product', '')):
                    raise ValueError()
                self.chrome = connection
                self.tabs = {}; self.sites = {}
            except Exception:
                if connection: connection.close()
                raise SetupError('Chrome connection was not allowed or did not respond. Check the permission prompt in your normal Chrome and connect again locally. No separate browser was opened.') from None

    def guard(self):
        if self.cancelled():
            raise SetupError('Visible operation paused. Inspect the page before resuming; no automatic replay was sent.')
        self.ready()

    def attach(self, marker):
        """Reconnect only to the browser identified by our persistent profile."""
        previous = self.port
        attached = False
        try:
            lines = marker.read_text().splitlines()
            if len(lines) != 2 or not lines[0].isdigit():return False
            port = int(lines[0])
            if not 1 <= port <= 65535 or not re.fullmatch(r'/devtools/browser/[A-Za-z0-9-]+', lines[1]):return False
            self.port = port
            info = self.endpoint('/json/version')
            address = urlsplit(info.get('webSocketDebuggerUrl', ''))
            if (address.scheme != 'ws' or address.hostname not in ('127.0.0.1', 'localhost')
                    or address.port != port or address.path != lines[1]
                    or address.username or address.password or address.query or address.fragment):return False
            if previous != port:self.tabs = {}
            attached = True
            return True
        except (OSError, ValueError, TypeError, KeyError):
            return False
        except Exception:
            # A stale profile marker or closed endpoint is not an attached browser.
            return False
        finally:
            # Keep a port only after its browser identity has been verified.
            if not attached:self.port = previous

    def ensure(self):
        self.guard()
        if self.source == 'running_chrome':
            if not self.chrome or self.chrome.closed:
                raise SetupError('Use Connect my Chrome on this PC first. Keep normal Chrome open and allow its connection prompt. No separate browser was opened.')
            try: self.chrome.call('Browser.getVersion')
            except Exception:
                self.chrome.close(); self.chrome = None; self.tabs = {}
                raise SetupError('Normal Chrome disconnected. Inspect the page, then Connect my Chrome locally. No automatic replay or separate browser launch was sent.') from None
            return
        profile = self.base/'visible-browser-profile'
        profile.mkdir(parents=True, exist_ok=True)
        marker = profile/'DevToolsActivePort'
        # Chrome's launcher may exit while the real browser stays open. Reattach
        # before spawning, including after Live Desk itself has restarted.
        if self.attach(marker):return
        if self.process and self.process.poll() is None:
            raise SetupError('The existing Live Desk browser is not responding. Keep its profile; close only that browser window normally, then retry. No second browser was opened.')
        roots = []
        for name in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
            root = os.environ.get(name)
            if root:roots.append(Path(root))
        # Prefer Chrome even when it is installed per-user and Edge is system-wide.
        candidates = [root/relative for relative in ('Google/Chrome/Application/chrome.exe',
            'Microsoft/Edge/Application/msedge.exe') for root in roots]
        exe = next((p for p in candidates if p.is_file()), None)
        if exe is None:
            raise SetupError('Install Chrome or Microsoft Edge on this Windows PC for visible mode.')
        marker.unlink(missing_ok=True)
        self.process = subprocess.Popen([str(exe), '--remote-debugging-address=127.0.0.1',
            '--remote-debugging-port=0', '--user-data-dir='+str(profile.resolve()),
            '--no-first-run', '--no-default-browser-check', '--new-window', 'about:blank'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(60):
            self.guard()
            if self.attach(marker):return
            if self.process.poll() is not None:
                break
            time.sleep(.2)
        raise SetupError('Could not open the dedicated visible browser. Close only the old Live Desk browser window and retry.')

    def endpoint(self, path, method='GET'):
        import requests
        with requests.Session() as session:
            session.trust_env = False
            response = session.request(method, f'http://127.0.0.1:{self.port}'+path, timeout=5, allow_redirects=False)
            response.raise_for_status()
            if response.status_code != 200:raise SetupError('The local browser endpoint did not return a valid response.')
            return response.json()

    def page(self, service):
        self.ensure()
        if self.source == 'running_chrome':
            targets = self.chrome.call('Target.getTargets')['targetInfos']
            target = next((t for t in targets if t.get('type') == 'page' and t.get('targetId') == self.tabs.get(service)), None)
            # Leave the operator's existing tabs alone. Create one managed tab
            # per service in the already running browser's regular context.
            if target is None:
                ident = self.chrome.call('Target.createTarget', url='about:blank', newWindow=False)['targetId']
            else: ident = target['targetId']
            self.tabs[service] = ident
            self.chrome.call('Target.activateTarget', targetId=ident)
            return self.chrome.page(ident)
        targets = self.endpoint('/json/list')
        target = next((t for t in targets if t.get('type') == 'page' and t.get('id') == self.tabs.get(service)), None)
        if target is None and service in self.sites:
            for candidate in targets:
                try:matches = origin(candidate.get('url', '')) == self.sites[service]
                except SetupError:matches = False
                if candidate.get('type') == 'page' and matches:
                    target = candidate;break
        if target is None:
            target = self.endpoint('/json/new?about:blank', 'PUT')
        self.tabs[service] = target['id']
        return CDP(target['webSocketDebuggerUrl'])

    def navigate(self, service, url):
        origin(url)
        with self.lock:
            self.sites[service] = origin(url)
            page = self.page(service)
            try:
                self.guard();page.call('Page.enable');page.call('Page.bringToFront')
                page.call('Page.navigate', url=url)
            finally:
                page.close()

    def begin_recording(self, service, url):
        with self.lock:
            if self.recording:
                raise SetupError('Finish or discard the current recording first.')
            self.sites[service] = origin(url)
            page = self.page(service)
            script = None
            try:
                page.call('Runtime.enable');page.call('Page.enable')
                page.call('Runtime.addBinding', name='liveDeskCapture')
                script = page.call('Page.addScriptToEvaluateOnNewDocument', source=RECORDER)['identifier']
                self.guard();page.call('Page.bringToFront');page.call('Page.navigate', url=url)
                deadline=time.monotonic()+25
                while time.monotonic()<deadline:
                    self.guard()
                    state=page.evaluate("({url:location.href,ready:document.readyState,recorder:window.__liveDeskRecorder===true})")
                    if state and state.get('url','').startswith(('http://','https://')) and origin(state['url'])==origin(url) and state['ready'] in ('interactive','complete'):
                        if not state['recorder']:page.evaluate(RECORDER)
                        if page.evaluate('window.__liveDeskRecorder===true'):break
                    time.sleep(.2)
                else:raise SetupError('Recorder did not become ready on the selected site. Sign in first; no recording was started.')
                self.recording = (page, script, origin(url))
            except Exception:
                try:
                    page.evaluate('window.__liveDeskStopRecorder?.()')
                    if script:page.call('Page.removeScriptToEvaluateOnNewDocument',identifier=script)
                except Exception:pass
                page.close();raise

    def finish_recording(self):
        with self.lock:
            if not self.recording:
                raise SetupError('No recording is active.')
            page, script, allowed = self.recording
            self.recording = None
            try:
                page.evaluate('window.__liveDeskStopRecorder?.(); window.__liveDeskRecorder=false')
                page.call('Page.removeScriptToEvaluateOnNewDocument', identifier=script)
                steps = []
                for event in page.events:
                    if event.get('name') != 'liveDeskCapture':continue
                    item = json.loads(event['payload'])
                    # The startup script also runs in blank/opaque frames.
                    # Their ready/skipped messages are bookkeeping, not actions:
                    # filter them before validating a replayable site's origin.
                    if item.get('kind') not in ('click','fill','assert'):continue
                    if origin(item.get('origin', '')) != allowed:continue
                    step = {k:item[k] for k in ('kind','locator')}
                    if step['kind'] == 'fill':step['variable'] = ''
                    if step['kind'] == 'assert':step['text']=item['text']
                    if not steps or step != steps[-1]:steps.append(step)
                if not steps:
                    raise SetupError('No actions were captured. The workflow was not saved. Check for the LIVE DESK RECORDING badge in the recording tab; use a harmless click test before recording another schedule.')
                if len(steps)>80 or len(page.events)>=500:
                    raise SetupError('Recording exceeded its limit and was not saved. Record a shorter workflow; do not replay a partial recording.')
                return steps
            finally:
                page.close()

    def run(self, service, url, recipe, values, progress):
        """Never retries a dispatched write; caller verifies the external result."""
        with self.lock:
            if self.recording:raise SetupError('Finish recording before running visible automation.')
            self.sites[service] = origin(url)
            page = self.page(service)
            try:
                self.guard();page.call('Page.enable');page.call('Page.bringToFront')
                page.call('Page.navigate', url=url)
                expected = origin(url)
                def check_origin():
                    self.guard()
                    if origin(page.evaluate('location.href')) != expected:
                        raise SetupError('Visible page left the configured site. Complete login manually, then review this run.')
                # Navigation is asynchronous; never reject the initial about:blank
                # or the previous event before Chrome has committed the new URL.
                deadline=time.monotonic()+25
                while time.monotonic()<deadline:
                    self.guard()
                    address=page.evaluate('location.href')
                    if address and address!='about:blank' and origin(address)==expected:
                        actual=urlsplit(address);requested=urlsplit(url)
                        if actual.path.rstrip('/')==requested.path.rstrip('/') and page.evaluate('document.readyState') in ('interactive','complete'):
                            # A navigation to another event is not an acceptable fallback.
                            from urllib.parse import parse_qs
                            q=parse_qs(actual.query)
                            if all(q.get(k)==v for k,v in parse_qs(requested.query).items()):break
                    time.sleep(.2)
                else:raise SetupError('The selected site did not open. Complete browser login manually before enabling visible mode.')
                def locate(locator):
                    check_origin()
                    return page.evaluate(target_script(locator, r'''
n.scrollIntoView({block:'center',inline:'center'});
const r=n.getBoundingClientRect(),x=r.x+r.width/2,y=r.y+r.height/2;
const root=n.getRootNode(),top=root.elementFromPoint(x,y);
if(!top||!(top===n||n.contains(top)))return {ok:false,reason:'covered'};
return {ok:true,x,y,text:(n.getAttribute('aria-label')||n.labels?.[0]?.innerText||n.innerText||n.textContent||'').trim(),
 editable:n.isContentEditable||['INPUT','TEXTAREA'].includes(n.tagName),type:n.type||''};'''))
                def wait_target(locator, timeout=25):
                    deadline = time.monotonic()+timeout
                    while time.monotonic()<deadline:
                        result = locate(locator)
                        if result and result.get('ok'):return result
                        time.sleep(.25)
                    raise SetupError('Visible target is missing, covered, ambiguous or disabled. Inspect the page; no guessed click was sent.')
                guard = wait_target(recipe['identity']['locator'])
                if guard['text'] != recipe['identity']['text']:
                    raise SetupError('The visible account/Page identity does not match the recorded workflow. Select the correct account first.')
                for index, step in enumerate(recipe['steps']):
                    progress(index+1, len(recipe['steps']), step['kind'])
                    loc = dict(step['locator'])
                    if 'text' in loc:
                        for key,value in values.items():loc['text']=loc['text'].replace('{'+key+'}', str(value))
                    if 'css' in loc and '{number}' in loc['css']:
                        number=str(values.get('number',''))
                        if not number.isdigit():raise SetupError('Missing camera number for the visible target.')
                        loc['css']=loc['css'].replace('{number}',number)
                    point = wait_target(loc)
                    self.guard();page.call('Page.bringToFront')
                    if step['kind'] == 'assert':
                        expected_text=step['text']
                        for key,value in values.items():expected_text=expected_text.replace('{'+key+'}',str(value))
                        if point['text'] != expected_text:raise SetupError('Visible page result did not match the configured check.')
                        continue
                    if step['kind']=='fill' and (not point['editable'] or point['type']=='password'):
                        raise SetupError('Visible fill supports ordinary text fields only. Enter login/passwords manually.')
                    # Real input events; do not call element.click() or simulate success.
                    check_origin()
                    page.call('Input.dispatchMouseEvent', type='mouseMoved', x=point['x'], y=point['y'])
                    page.call('Input.dispatchMouseEvent', type='mousePressed', x=point['x'], y=point['y'], button='left', clickCount=1)
                    page.call('Input.dispatchMouseEvent', type='mouseReleased', x=point['x'], y=point['y'], button='left', clickCount=1)
                    if step['kind']=='fill':
                        check_origin()
                        focused=page.evaluate(target_script(loc,"return {ok:n===n.getRootNode().activeElement && n.type!=='password'};"))
                        if not focused or not focused.get('ok'):
                            raise SetupError('The selected input lost focus. No text was sent to another field.')
                        page.call('Input.dispatchKeyEvent', type='keyDown', key='a', code='KeyA', windowsVirtualKeyCode=65, modifiers=2)
                        page.call('Input.dispatchKeyEvent', type='keyUp', key='a', code='KeyA', windowsVirtualKeyCode=65, modifiers=2)
                        page.call('Input.insertText', text=str(values[step['variable']]))
                    time.sleep(.6)
                check_origin()
            finally:
                page.close()
