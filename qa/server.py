"""Disposable QA dashboard: no credentials, OBS, browser login or platform clients."""
import json
import sys
import tempfile
import threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from dashboard import Controller, DashboardServer, Handler
from desktop_host import DesktopHost
import time
from datetime import datetime
from core import IST
from unittest.mock import Mock
from studio import Telegram
import studio
QA_LIVE_EPOCH=time.time()-360

class MemoryVault:
    def __init__(self): self.values = {'facebook_page_token': 'qa-only-secret-not-a-real-token'}
    def get(self, key): return self.values.get(key, '')
    def set(self, key, value): self.values[key] = value

class ReadOnlyFakeServices:
    def __init__(self, cfg, vault, log):
        self.log = log
        if any(s.get('id')=='qa-takeover' for s in cfg.get('schedule') or []):
            self.obs=Mock();self.yt=Mock();self.fb=Mock();self.cam=Mock()
            started=datetime.fromtimestamp(QA_LIVE_EPOCH,IST).isoformat()
            self.yt.owned_channel.return_value={'id':'fixture-channel'};self.fb.identity.return_value={'id':'fixture-page'}
            self.yt.stream_for_obs.return_value={'id':'fixture-official'}
            event={'id':'abcdefghijk','snippet':{'channelId':'fixture-channel','title':'QA existing YouTube live','actualStartTime':started},'status':{'lifeCycleStatus':'live'},'contentDetails':{'boundStreamId':'fixture-official'}}
            self.yt.list.return_value=[event];self.yt.event.return_value=event
            self.fb.recent.return_value=[{'id':'123456789','status':'LIVE'}]
            self.fb.api.return_value={'id':'123456789','title':'QA existing Facebook live','status':'LIVE','secure_stream_url':'rtmps://fixture.invalid/rtmp/qa-not-a-secret','broadcast_start_time':started}
            self.obs.plugin_target.return_value=(None,None,{'service-param':{'server':'rtmps://fixture.invalid/rtmp/','key':'qa-not-a-secret'}})
            def read(kind,**kw):
                if kind=='GetOutputList':return {'outputs':[{'outputName':'multi-output-fixture','outputActive':True}]}
                if kind in ('GetStreamStatus','GetOutputStatus'):return {'outputActive':True,'outputDuration':(time.time()-QA_LIVE_EPOCH)*1000}
                raise AssertionError('QA refuses OBS writes: '+kind)
            self.obs.call.side_effect=read
            self.obs.start.side_effect=AssertionError('QA refuses any live start')
    def verify_run_outputs(self,record):return ({'outputActive':True},{'outputActive':True})
    def both_live(self,record):return True
    def takeover_live(self,record):return True
    def end(self,*args,**kw):raise AssertionError('QA refuses any live end')
    def camera_action(self,*args,**kw):raise AssertionError('QA refuses any camera movement')
    def check(self):
        self.log('OBS connected. Program scene: QA only')
        self.log('YouTube channel verified: QA only')
        self.log('Facebook Page verified: QA only')
        self.log('Camera skipped; no external devices are contacted in QA.')
    def close(self): pass

class QAController(Controller):
    def run(self, mode):
        if mode != 'check': raise ValueError('QA server refuses automation and account login.')
        return super().run(mode)

class SocialFixture:
    def __init__(self,*args):pass
    def check(self,ig):return {'facebook':{'id':'123456789','name':'Fixture Page'},'instagram':{'id':'1234567','name':'fixture_instagram'},'youtube':{'id':'UC'+'a'*22,'name':'Fixture Channel'}}
    def publish(self,job):raise AssertionError('QA never executes a platform publish')

class RemoteHandler(Handler):
    def local(self): return False

with tempfile.TemporaryDirectory(prefix='live-desk-qa-') as directory:
    controller = QAController(directory, ReadOnlyFakeServices, MemoryVault())
    controller.social.publisher_factory=SocialFixture
    # Isolated Telegram Bot API fixture; never contact a real bot or channel.
    telegram_message_id=[100]
    def fake_telegram(self,method,data=None,files=None):
        if self.vault.get('telegram_bot_token')!='123456789:'+'q'*35:raise ValueError('QA requires its fake bot token.')
        if method=='getMe':return {'id':123456789,'is_bot':True,'username':'qa_fixture_bot'}
        if method=='getChat':
            if data['chat_id']!='@qa_darshan':raise ValueError('QA requires its fake channel.')
            return {'id':-1001234567890,'type':'channel','title':'QA Telegram channel','username':'qa_darshan'}
        if method=='getChatMember':return {'status':'administrator','can_post_messages':True}
        if method=='sendMediaGroup':
            result=[]
            for item in json.loads(data['media']):
                telegram_message_id[0]+=1
                result.append({'message_id':telegram_message_id[0],'chat':{'id':-1001234567890}})
            return result
        raise AssertionError('QA refuses unsupported Telegram calls')
    Telegram.request=fake_telegram
    class StudioYouTubeFixture:
        def __init__(self,*args):pass
        def connect(self):pass
        def owned_channel(self):return {'id':'UC'+'a'*22,'snippet':{'title':'QA verified YouTube channel'}}
    studio.YouTube=StudioYouTubeFixture
    # Dashboard delivery fixture; the production adapter is separately exercised
    # through real Chromium/CDP against local pages in youtube-post.test.cjs.
    studio.chrome_ready=lambda browser:None
    youtube_post_ids=[0]
    class StudioPhotoPostFixture:
        def __init__(self,cfg,vault,manager,stop,browser):self.manager=manager
        def publish(self,job):
            if not job.get('studio_youtube_browser') or job['targets']['youtube']!='UC'+'a'*22 or len(job['media']) not in (7,10):raise AssertionError('Unexpected YouTube fixture post')
            youtube_post_ids[0]+=1
            self.manager.checkpoint(job['id'],'youtube',status='published',write_dispatched=True,stage='Fixture published receipt',url='https://www.youtube.com/post/UgQaFixture'+str(youtube_post_ids[0]))
    studio.YouTubePost=StudioPhotoPostFixture
    controller.desktop_host=DesktopHost()
    controller.desktop_host.update(addresses=['192.168.1.42'])
    def fake_host():
        while not controller.closing:
            def dispatch(action,ip):
                controller.log('QA PC action: '+action)
                if action=='mobile-on':controller.mobile_enabled=True;controller.mobile_urls=['http://'+ip+':8866']
                if action=='mobile-off':controller.mobile_enabled=False;controller.mobile_urls=[]
                return 'QA PC action finished: '+action
            controller.desktop_host.drain(dispatch)
            time.sleep(.05)
    threading.Thread(target=fake_host,daemon=True).start()
    local = DashboardServer(('127.0.0.1', 0), controller, 'qa-pairing')
    remote = DashboardServer(('127.0.0.1', 0), controller, 'qa-pairing')
    remote.RequestHandlerClass = RemoteHandler
    for server in (local, remote):
        threading.Thread(target=server.serve_forever, daemon=True).start()
    print(json.dumps({'desktop': f'http://127.0.0.1:{local.server_port}',
                      'mobile': f'http://127.0.0.1:{remote.server_port}'}), flush=True)
    try: sys.stdin.read()
    finally:
        controller.shutdown()
        if controller.worker: controller.worker.join(3)
        for server in (local, remote): server.shutdown(); server.server_close()

