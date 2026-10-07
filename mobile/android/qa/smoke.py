"""Exercise the installed APK against the disposable real mobile dashboard."""
import json
import re
import subprocess
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

OUT = Path('mobile/android/build')
OUT.mkdir(parents=True, exist_ok=True)
REPORT = {'tests': []}

def adb(*args, binary=False):
    return subprocess.check_output(['adb', *args], text=not binary, timeout=20)

def nodes():
    adb('shell', 'uiautomator', 'dump', '/sdcard/window.xml')
    return list(ET.fromstring(adb('shell', 'cat', '/sdcard/window.xml')).iter('node'))

def find(label=None, klass=None, contains=False, enabled=True, timeout=35):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        for node in nodes():
            values = [node.get('text', ''), node.get('content-desc', ''), node.get('resource-id', '')]
            matched = not label or any(label in val if contains else label == val for val in values)
            if matched and (not klass or node.get('class') == klass) and (not enabled or node.get('enabled') == 'true'):
                return node
        time.sleep(.4)
    raise AssertionError('UI element missing: ' + str(label or klass))

def tap(node):
    a,b,c,d = map(int,re.findall(r'\d+', node.get('bounds')))
    adb('shell','input','tap',str((a+c)//2),str((b+d)//2))

def click(label, contains=False): tap(find(label, contains=contains))

def type_into(node, text, clear=False):
    tap(node)
    time.sleep(.5)
    if clear:
        adb('shell','input','keyevent','123')
        adb('shell','input','keyevent', *(['67'] * 64))
    adb('shell','input','text',text)
    adb('shell','input','keyevent','4') # Android Back dismisses the IME
    time.sleep(.5)

def state():
    return json.load(urllib.request.urlopen('http://127.0.0.1:8866/qa/state', timeout=3))

def assert_state(armed, events):
    until=time.monotonic()+20
    while time.monotonic()<until:
        s=state()
        if s['armed']==armed and s['events']==events:return
        time.sleep(.5)
    raise AssertionError(state())

def shot(name): (OUT / name).write_bytes(adb('exec-out','screencap','-p',binary=True))

def passed(label):
    REPORT['tests'].append(label)
    print('PASS ' + label, flush=True)

try:
    adb('install','-r',str(OUT / 'Live-Desk-Mobile-0.1.0.apk'))
    adb('shell','am','start','-n','org.livedesk.mobile/.MainActivity')
    find('Connect to PC'); shot('android-connect.png')
    type_into(find('PC mobile address', klass='android.widget.EditText'), 'http://10.0.2.2:8866')
    click('Connect to PC')
    find('Connect this device', contains=True)
    type_into(find(klass='android.widget.EditText'), 'wrong')
    click('Connect this device',contains=True)
    find('Incorrect pairing code',contains=True,enabled=False)
    passed('Installed APK loads pairing; incorrect code rejected')
    type_into(find(klass='android.widget.EditText'),'qa-pairing',clear=True)
    click('Connect this device',contains=True)
    find('Live overview',contains=True);shot('android-overview.png')
    assert_state(False,[])
    passed('Correct pairing opens real remote dashboard without enabling automation')
    # The hero controls may lie below the fold on a small phone.
    adb('shell','input','swipe','500','1450','500','680','500')
    click('Enable automation',contains=True)
    find('Enable your saved automation plan?',contains=True)
    click('Cancel');assert_state(False,[])
    click('Enable automation',contains=True)
    click('Confirm')
    assert_state(True,['arm'])
    shot('android-enabled.png')
    click('Pause automation',contains=True)
    assert_state(False,['arm','pause'])
    passed('Enable confirmation, cancel and Pause reach only the fake PC controller')
    adb('shell','input','keyevent','3') # normal background flush before process restart
    time.sleep(1)
    adb('shell','am','force-stop','org.livedesk.mobile')
    adb('shell','am','start','-n','org.livedesk.mobile/.MainActivity')
    find('Live overview',contains=True)
    assert state()['sessions']==1
    passed('Saved address and pairing survive app restart')
    (OUT / 'offline.flag').touch()
    find('Connection to the PC is lost',contains=True,enabled=False)
    arm=find('Enable automation',contains=True,enabled=False)
    assert arm.get('enabled')=='false',arm.attrib
    shot('android-offline.png')
    (OUT / 'offline.flag').unlink()
    # Reconnect automatically through the dashboard's polling.
    find('PC connected',contains=True)
    passed('Connection loss disables controls and automatically recovers')
    click('PC')
    click('android:id/button1') # native positive button is uppercase on Material theme
    find('Connect to PC')
    click('Connect to PC')
    find('Connect this device',contains=True)
    assert_state(False,['arm','pause'])
    passed('Changing PC clears pairing without pausing or starting the PC')
    REPORT['status']='passed'
except Exception as exception:
    REPORT['status']='failed';REPORT['error']=repr(exception)
    try: shot('android-failure.png');(OUT/'android-window.xml').write_text(adb('shell','cat','/sdcard/window.xml'))
    except Exception:pass
    raise
finally:
    (OUT/'android-report.json').write_text(json.dumps(REPORT,indent=2))
