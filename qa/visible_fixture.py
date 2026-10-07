"""Real CDP input regression against a localhost-only fixture, never a platform."""
import json
import os
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from visible_browser import Browser

port,url,base=sys.argv[1:]
assert url.startswith('http://127.0.0.1:')
browser=Browser(base,ready=lambda:None)
browser.ensure()
assert browser.port==int(port)
browser.begin_recording('fixture',url)
page=browser.page('fixture')
deadline=time.monotonic()+10
while time.monotonic()<deadline:
    if page.evaluate('Boolean(document.querySelector("#title") && window.__liveDeskRecorder)'):break
    time.sleep(.1)
else:raise AssertionError('Recorder did not load')

def click(selector, shadow=False):
    root='document.querySelector("studio-fixture").shadowRoot' if shadow else 'document'
    p=page.evaluate('(() => {const r='+root+'.querySelector('+json.dumps(selector)+').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()')
    for event in ('mousePressed','mouseReleased'):
        page.call('Input.dispatchMouseEvent',type=event,button='left',clickCount=1,**p)

click('#title');page.call('Input.insertText',text='manual-title-not-saved')
click('#password');page.call('Input.insertText',text='test-secret-not-saved')
click('#save')
steps=browser.finish_recording()
assert any(s['kind']=='fill' and s['locator'].get('css')=='#title' for s in steps),steps
assert not any(s['locator'].get('css')=='#password' for s in steps),steps
assert 'manual-title-not-saved' not in json.dumps(steps)
assert 'test-secret-not-saved' not in json.dumps(steps)
browser.begin_recording('fixture',url)
deadline=time.monotonic()+10
while time.monotonic()<deadline:
    if page.evaluate('Boolean(document.querySelector("studio-fixture")?.shadowRoot && window.__liveDeskRecorder)'):break
    time.sleep(.1)
time.sleep(.4) # Allow the recorder to discover dynamically inserted open shadow roots.
click('#channel-name',True)
click('#shadow-title',True);page.call('Input.insertText',text='shadow-title-not-saved')
click('#editable-title',True);page.call('Input.insertText',text='editable-text-not-saved')
click('#shadow-password',True);page.call('Input.insertText',text='shadow-secret-not-saved')
click('#shadow-save span',True)
assert 'captured on this page' in page.evaluate('document.querySelector("[data-live-desk-recorder]").textContent')
steps=browser.finish_recording()
assert page.evaluate('document.querySelector("[data-live-desk-recorder]")===null')
assert any(s['kind']=='fill' and s['locator'].get('css')=='#shadow-title' for s in steps),steps
assert any(s['kind']=='fill' and s['locator'].get('css')=='#editable-title' for s in steps),steps
assert any(s['locator'].get('css')=='#channel-name' for s in steps),steps
assert any(s['kind']=='click' and s['locator'].get('css')=='#shadow-save' for s in steps),steps
assert not any(s['locator'].get('css')=='#shadow-password' for s in steps),steps
for secret in ('shadow-title-not-saved','editable-text-not-saved','shadow-secret-not-saved'):assert secret not in json.dumps(steps)
shadow_recipe={'identity':{'locator':{'css':'#channel-name'},'text':'Test Temple'},'steps':[
    {'kind':'fill','locator':{'css':'#shadow-title'},'variable':'title'},
    {'kind':'click','locator':{'css':'#shadow-save'}},
    {'kind':'assert','locator':{'css':'#shadow-result'},'text':'Shadow saved'}]}
browser.run('fixture',url,shadow_recipe,{'title':'Shadow scheduled title'},lambda *args:None)
assert page.evaluate('window.shadowSaved')=='Shadow scheduled title'
assert page.evaluate('window.shadowTrusted') is True
browser.begin_recording('fixture',url)
try:browser.finish_recording()
except Exception as exc:assert 'No actions were captured' in str(exc),str(exc)
else:raise AssertionError('Empty recording reported success')
recipe={'identity':{'locator':{'css':'#account'},'text':'Test Temple'},'steps':[
    {'kind':'fill','locator':{'css':'#title'},'variable':'title'},
    {'kind':'click','locator':{'css':'#save'}},
    {'kind':'assert','locator':{'css':'#result'},'text':'Saved via real click'}]}
progress=[]
browser.run('fixture',url,recipe,{'title':'Scheduled Title'},lambda *args:progress.append(args))
assert page.evaluate('document.querySelector("#title").value')=='Scheduled Title'
assert page.evaluate('window.trustedClick') is True
assert page.evaluate('window.savedTitle')=='Scheduled Title'
assert len(progress)==3
# Replacing the controller (app restart) must attach to the same browser/profile
# and rediscover its site tab instead of opening another login window or tab.
page.evaluate("document.cookie='liveDeskSession=retained;path=/';localStorage.setItem('liveDeskLogin','retained')")
tab=browser.tabs['fixture'];count=len(browser.endpoint('/json/list'))
restarted=Browser(base,ready=lambda:None)
restarted.navigate('fixture',url)
assert restarted.port==int(port) and restarted.process is None
assert restarted.tabs['fixture']==tab
assert len(restarted.endpoint('/json/list'))==count
reused=restarted.page('fixture')
deadline=time.monotonic()+10
while time.monotonic()<deadline:
    if reused.evaluate('location.href')==url and reused.evaluate('document.readyState')=='complete':break
    time.sleep(.1)
assert 'liveDeskSession=retained' in reused.evaluate('document.cookie')
assert reused.evaluate("localStorage.getItem('liveDeskLogin')")=='retained'
restarted.begin_recording('fixture',url)
assert restarted.tabs['fixture']==tab
assert len(restarted.endpoint('/json/list'))==count
click('#account')
assert restarted.finish_recording()
reused.close()
# Pause before execution and wrong account both prevent a second write.
browser.cancelled=lambda:True
try:browser.run('fixture',url,recipe,{'title':'WRONG'},lambda *args:None)
except Exception:pass
else:raise AssertionError('Cancellation was ignored')
assert 'liveDeskSession=retained' in page.evaluate('document.cookie')
page.close()
print('PASS real Chromium recording/replay, cancellation, controller reattachment, same site tab and retained local login session')

# Simulate Chrome's regular User Data marker using this localhost fixture's
# already running browser. Real Windows permission UI is an operator gate;
# this fixture proves the WebSocket-only transport without any HTTP discovery,
# cookie migration, replacement launch or reuse/navigation of unrelated tabs.
local=Path(base)/'normal-chrome-fixture'
marker=local/'Google/Chrome/User Data/DevToolsActivePort'
marker.parent.mkdir(parents=True)
marker.write_text((Path(base)/'visible-browser-profile/DevToolsActivePort').read_text())
os.environ['LOCALAPPDATA']=str(local)
normal=Browser(base,ready=lambda:None);normal.select('running_chrome')
normal.endpoint=lambda *a:(_ for _ in ()).throw(AssertionError('Normal Chrome must not use HTTP discovery'))
normal.connect_chrome();root=normal.chrome
before=root.call('Target.getTargets')['targetInfos']
normal.navigate('fixture',url)
managed=normal.page('fixture')
deadline=time.monotonic()+10
while time.monotonic()<deadline:
    if managed.evaluate('location.href')==url and managed.evaluate('document.readyState')=='complete':break
    time.sleep(.1)
assert 'liveDeskSession=retained' in managed.evaluate('document.cookie')
assert managed.evaluate("localStorage.getItem('liveDeskLogin')")=='retained'
assert normal.process is None and normal.chrome is root
normal_tab=normal.tabs['fixture']
after=root.call('Target.getTargets')['targetInfos']
assert len([t for t in after if t['type']=='page'])==len([t for t in before if t['type']=='page'])+1
assert all(any(t['targetId']==old['targetId'] and t['url']==old['url'] for t in after) for old in before if old['type']=='page')
normal.begin_recording('fixture',url)
page=managed
deadline=time.monotonic()+10
while time.monotonic()<deadline:
    if page.evaluate('Boolean(document.querySelector("#account") && window.__liveDeskRecorder)'):break
    time.sleep(.1)
click('#account');click('#title');page.call('Input.insertText',text='normal-chrome-private-value');click('#save')
captured=normal.finish_recording()
assert any(s['kind']=='fill' for s in captured)
assert 'normal-chrome-private-value' not in json.dumps(captured)
normal.run('fixture',url,recipe,{'title':'Existing browser scheduled title'},lambda *a:None)
assert managed.evaluate('window.savedTitle')=='Existing browser scheduled title'
assert managed.evaluate('window.trustedClick') is True
assert normal.chrome is root and normal.tabs['fixture']==normal_tab
assert len([t for t in root.call('Target.getTargets')['targetInfos'] if t['type']=='page'])==len([t for t in after if t['type']=='page'])
managed.close();normal.disconnect()
assert root.closed and normal.process is None
try:normal.navigate('fixture',url)
except Exception as exc:assert 'Connect my Chrome' in str(exc)
else:raise AssertionError('Disconnected Chrome silently reconnected/launched')
# Existing browser is still alive and retains every original page after detach.
check=Browser(base,ready=lambda:None);check.select('running_chrome');check.connect_chrome()
remaining=check.chrome.call('Target.getTargets')['targetInfos']
assert all(any(t['targetId']==old['targetId'] for t in remaining) for old in before if old['type']=='page')
check.disconnect()
print('PASS existing browser WebSocket-only managed tabs, retained sign-in, recording/replay, persistent socket, disconnect without closing tabs or launching Chrome')
