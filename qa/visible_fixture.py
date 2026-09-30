"""Real CDP input regression against a localhost-only fixture, never a platform."""
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from visible_browser import Browser

port,url=sys.argv[1:]
assert url.startswith('http://127.0.0.1:')
browser=Browser('/unused',ready=lambda:None)
browser.port=int(port)
browser.ensure=lambda:None
browser.begin_recording('fixture',url)
page=browser.page('fixture')
deadline=time.monotonic()+10
while time.monotonic()<deadline:
    if page.evaluate('Boolean(document.querySelector("#title") && window.__liveDeskRecorder)'):break
    time.sleep(.1)
else:raise AssertionError('Recorder did not load')

def click(selector):
    p=page.evaluate('(() => {const r=document.querySelector('+json.dumps(selector)+').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()')
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
# Pause before execution and wrong account both prevent a second write.
browser.cancelled=lambda:True
try:browser.run('fixture',url,recipe,{'title':'WRONG'},lambda *args:None)
except Exception:pass
else:raise AssertionError('Cancellation was ignored')
assert page.evaluate('window.savedTitle')=='Scheduled Title'
page.close()
print('PASS real Chromium recording, secret exclusion, trusted click, typing, verification and cancellation')
