"""Mock Telegram only: no bots, channels or messages are contacted."""
import json, sys, unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from connections import SetupError
from studio import Studio
from telegram_publish import Telegram, bot_token, channel_id
import test_studio, test_dashboard
from dashboard import Handler

TOKEN='123456789:'+'x'*35
CHANNEL='-1001234567890'


class TelegramTests(unittest.TestCase):
    setUp=test_studio.ConnectionsAndPosting.setUp
    tearDown=test_studio.ConnectionsAndPosting.tearDown
    photos=test_studio.ConnectionsAndPosting.photos
    wait=test_studio.ConnectionsAndPosting.wait

    def connect(self):
        self.st.save_telegram({'token':TOKEN,'channel':'@darshan_test'})
        with patch('studio.Telegram.identity',return_value={'id':CHANNEL,'name':'Darshan fixture','bot_id':'123456789','bot_name':'fixture_bot'}):
            self.st.check({'platform':'telegram'});self.wait()
        self.assertEqual(self.st.accounts['telegram']['status'],'verified')

    def draft(self,count=17):
        self.connect()
        return self.st.prepare({'platform':'telegram','mode':{7:'P1',10:'P2',17:'TG'}[count],
            'media':self.photos(count),'title':'Daily darshan','caption':'Hare Krishna 🌻'})

    def send(self,job):return self.st.send({'id':job['id'],'revision':job['revision'],'confirmed':True})

    def responder(self,calls,*,fail_second=False,stop_after_first=False):
        def respond(method,data=None,files=None):
            if method=='getMe':return {'id':123456789,'is_bot':True,'username':'fixture_bot'}
            if method=='getChat':return {'id':int(CHANNEL),'type':'channel','title':'Fixture','username':'darshan_test'}
            if method=='getChatMember':return {'status':'administrator','can_post_messages':True}
            self.assertEqual(method,'sendMediaGroup')
            # Receipt stage is persisted BEFORE each network write.
            saved=json.loads(self.s.path.read_text())['jobs'][-1]
            self.assertEqual(saved['results']['telegram']['status'],'sending')
            if calls:self.assertEqual(len(saved['results']['telegram']['albums']),1)
            media=json.loads(data['media'])
            calls.append({'media':media,'bytes':[files['photo'+str(i)][1].read() for i in range(len(files))]})
            if fail_second and len(calls)==2:raise SetupError('Uncertain Telegram write',retryable=False)
            if stop_after_first:self.s.stop.set()
            return [{'message_id':100*len(calls)+i,'chat':{'id':int(CHANNEL)}} for i in range(len(media))]
        return respond

    def test_credentials_survive_restart_blank_preserves_and_never_leave_vault(self):
        self.connect();self.st.save_telegram({'token':'','channel':'@darshan_test'})
        self.assertEqual(self.c.vault.get('telegram_bot_token'),TOKEN)
        self.assertNotIn(TOKEN,self.st.path.read_text());self.assertNotIn(TOKEN,json.dumps(self.st.state()))
        self.assertEqual(Studio(self.c).state()['saved']['telegram'],'@darshan_test')
        for token,channel in [('bad','@darshan_test'),(TOKEN,'https://t.me/darshan_test'),(TOKEN,'https://evil.test')]:
            with self.assertRaises(ValueError):self.st.save_telegram({'token':token,'channel':channel})
        self.assertEqual(self.st.data['telegram']['channel'],'@darshan_test')

    def test_check_is_read_only_and_requires_channel_post_permission(self):
        self.st.save_telegram({'token':TOKEN,'channel':'@darshan_test'})
        calls=[];respond=self.responder(calls)
        with patch('studio.Telegram.request',side_effect=respond) as req:
            self.st.check({'platform':'telegram'});self.wait()
        self.assertEqual([x.args[0] for x in req.call_args_list],['getMe','getChat','getChatMember'])
        self.assertEqual(calls,[])
        for chat_type,status,can_post in [('supergroup','administrator',True),('channel','member',False),('channel','administrator',False)]:
            adapter=Telegram({'telegram_channel':'@darshan_test'},self.c.vault,self.s,self.s.stop)
            adapter.request=Mock(side_effect=[{'id':123456789,'is_bot':True},{'id':int(CHANNEL),'type':chat_type},{'status':status,'can_post_messages':can_post}])
            with self.assertRaises(SetupError):adapter.identity()

    def test_two_albums_keep_7_then_10_exact_photo_order_and_caption(self):
        job=self.draft();calls=[]
        with patch('studio.Telegram.request',side_effect=self.responder(calls)):
            self.send(job);self.wait()
        self.assertEqual([len(c['media']) for c in calls],[7,10])
        self.assertEqual(sum((c['bytes'] for c in calls),[]),[('fixture-photo-'+str(i)).encode() for i in range(17)])
        for call in calls:
            self.assertEqual(call['media'][0]['caption'],job['caption'])
            self.assertTrue(all('caption' not in x for x in call['media'][1:]))
        posted=self.s.job(job['id']);self.assertEqual(posted['status'],'published')
        self.assertEqual(posted['targets'],{'telegram':CHANNEL});self.assertFalse(self.s.data['enabled'])
        self.assertEqual(posted['results']['telegram']['urls'],['https://t.me/darshan_test/100','https://t.me/darshan_test/200'])
        with self.assertRaises(ValueError):self.send(job)

    def test_single_seven_and_ten_photo_albums(self):
        for count in (7,10):
            job=self.draft(count);calls=[]
            with patch('studio.Telegram.request',side_effect=self.responder(calls)):
                self.send(job);self.wait()
            self.assertEqual([len(c['media']) for c in calls],[count])
            self.assertEqual(self.s.job(job['id'])['status'],'published')

    def test_second_album_failure_keeps_first_receipt_and_never_retries(self):
        job=self.draft();calls=[]
        with patch('studio.Telegram.request',side_effect=self.responder(calls,fail_second=True)):
            self.send(job);self.wait()
        saved=self.s.job(job['id']);self.assertEqual(saved['status'],'needs_review')
        self.assertEqual(saved['results']['telegram']['albums'][0]['count'],7)
        self.assertEqual(len(saved['results']['telegram']['albums']),1)
        self.assertEqual(len(calls),2)
        with self.assertRaises(ValueError):self.send(job)
        from social import Social
        restarted=Social(self.c);self.assertEqual(restarted.job(job['id'])['status'],'needs_review');restarted.close()

    def test_shutdown_between_albums_retains_first_album(self):
        job=self.draft();calls=[]
        with patch('studio.Telegram.request',side_effect=self.responder(calls,stop_after_first=True)):
            self.send(job);self.wait()
        self.assertEqual(len(calls),1);self.assertEqual(self.s.job(job['id'])['status'],'needs_review')
        self.assertEqual(self.s.job(job['id'])['results']['telegram']['albums'][0]['count'],7)

    def test_changed_channel_bot_or_live_blocks_delivery(self):
        job=self.draft(7)
        self.st.accounts['telegram']['bot_id']='987654321'
        with self.assertRaises(ValueError):self.send(job)
        self.st.accounts['telegram']['bot_id']='123456789';self.st.data['telegram']['channel']='@another_channel'
        with self.assertRaises(ValueError):self.send(job)
        self.st.data['telegram']['channel']='@darshan_test';self.c.monitor.snapshot=lambda:{'obs':{'active':True}}
        with self.assertRaises(ValueError):self.send(job)
        self.assertEqual(self.s.job(job['id'])['status'],'draft')

    def test_live_account_identity_is_rechecked_before_first_album(self):
        job=self.draft(7);calls=[]
        with patch('studio.Telegram.identity',return_value={'id':CHANNEL,'bot_id':'99999999'}),patch('studio.Telegram.request') as req:
            self.send(job);self.wait();req.assert_not_called()
        self.assertEqual(self.s.job(job['id'])['status'],'needs_review')

    def test_validation_blocks_long_captions_missing_photos_and_legacy_approval(self):
        self.connect();media=self.photos(7)
        for caption in ('x'*1025,'🌻'*513):
            with self.assertRaises(ValueError):self.st.prepare({'platform':'telegram','mode':'P1','media':media,'title':'Test','caption':caption})
        with self.assertRaises(ValueError):self.st.prepare({'platform':'telegram','mode':'TG','media':media,'title':'Test','caption':'Hi'})
        with self.assertRaises(ValueError):self.s.draft({'platforms':['telegram'],'title':'Test','caption':'Hi','media':media})
        job=self.draft(7)
        with self.assertRaises(ValueError):self.s.command({'action':'approve','id':job['id'],'revision':job['revision'],'confirmed':True})
        self.assertEqual(self.s.job(job['id'])['status'],'draft')

    def test_api_failure_and_timeout_never_expose_bot_token(self):
        self.connect();adapter=Telegram({'telegram_channel':'@darshan_test'},self.c.vault,self.s,self.s.stop)
        response=Mock(ok=False);response.json.return_value={'ok':False,'error_code':401,'description':TOKEN}
        for request in (Mock(return_value=response),Mock(side_effect=RuntimeError('https://api.telegram.org/bot'+TOKEN))):
            with patch.dict(sys.modules,{'requests':Mock(post=request)}):
                with self.assertRaises(SetupError) as exc:adapter.request('getMe')
            self.assertNotIn(TOKEN,str(exc.exception));self.assertEqual(request.call_count,1)


class TelegramHTTP(unittest.TestCase):
    setUp=test_dashboard.Tests.setUp;tearDown=test_dashboard.Tests.tearDown;request=test_dashboard.Tests.request;login=test_dashboard.Tests.login
    def test_only_local_operator_can_save_token_and_diagnostics_redact_it(self):
        body={'token':TOKEN,'channel':'@darshan_test'}
        self.assertEqual(self.request('/api/studio/telegram',body)[0],401);self.login()
        self.assertEqual(self.request('/api/studio/telegram',body,**{'X-CSRF-Token':'bad'})[0],403)
        with patch.object(Handler,'local',return_value=False):self.assertEqual(self.request('/api/studio/telegram',body)[0],403)
        self.assertEqual(self.request('/api/studio/telegram',body)[0],200)
        self.assertNotIn(TOKEN,json.dumps(self.request('/api/studio/state')[1]))
        self.c.log('old error included '+TOKEN);self.assertNotIn(TOKEN,json.dumps(self.c.diagnostics()))
        with self.server.auth_lock:self.server.sessions[self.cookie.split('=',1)[1]]['role']='viewer'
        self.assertEqual(self.request('/api/studio/telegram',body)[0],403)
