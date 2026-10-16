"""Posting boundary tests. All platform calls are mocked; no real posts/messages."""
import copy, json, tempfile, threading, unittest, sys
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from studio import Studio, DirectInstagram, public_link
from social import Social
from connections import SetupError
import test_social
from test_social import FakePublisher
import test_dashboard
from dashboard import Handler

class ConnectionsAndPosting(unittest.TestCase):
    def setUp(self):
        test_social.SocialTests.setUp(self);self.c.social=self.s;self.st=Studio(self.c)
    tearDown=test_social.SocialTests.tearDown
    upload=test_social.SocialTests.upload
    wait=test_social.SocialTests.wait
    def photos(self,count):
        # JPEG dimensions are verified by the existing media importer in its own tests.
        result=[]
        for i in range(count):
            import hashlib
            raw=('fixture-photo-'+str(i)).encode();ident=hashlib.sha256(raw).hexdigest()
            (self.s.folder/ident).write_bytes(raw)
            self.s.data['assets'][ident]={'id':ident,'name':str(i)+'.jpg','type':'image/jpeg','size':len(raw),'width':960,'height':1200}
            result.append(ident)
        return result
    def ready(self,platform='facebook',mode='FB'):
        self.st.accounts[platform]={'status':'verified','id':'123456' if platform=='facebook' else self.c.cfg['youtube_channel_id'] if platform=='youtube' else '7654321','name':'Fixture'}
        return self.st.prepare({'platform':platform,'mode':mode,'media':self.photos(17 if mode=='FB' else 7),'title':'Darshan','caption':'Hare Krishna'})
    def send(self,j):return self.st.send({'id':j['id'],'revision':j['revision'],'confirmed':True})
    def test_one_post_sent_once_without_enabling_or_resuming_old_queue(self):
        old=self.s.draft({'title':'Old','caption':'Old','platforms':['facebook'],'media':[], 'publish_at':(__import__('core').now_ist()+__import__('datetime').timedelta(minutes=10)).isoformat()})
        self.s.command({'action':'approve','id':old['id'],'revision':old['revision'],'confirmed':True})
        j=self.ready()
        with patch('studio.Publisher',FakePublisher):self.send(j);self.wait()
        self.assertEqual(FakePublisher.sent,[j['id']]);self.assertFalse(self.s.data['enabled'])
        with self.assertRaises(ValueError):self.send(j)
        self.assertEqual(self.s.job(old['id'])['status'],'queued')
    def test_direct_instagram_has_own_account_and_preserves_legacy_linked_account(self):
        self.s.data['instagram_id']='999999';self.c.vault.set('instagram_imgbb_key','fake-hosting')
        j=self.ready('instagram','P1')
        self.assertEqual(self.s.data['instagram_id'],'999999')
        with patch('studio.DirectInstagram',FakePublisher):self.send(j);self.wait()
        self.assertEqual(self.s.job(j['id'])['targets'],{'instagram':'7654321'})
        self.assertEqual(self.s.data['instagram_id'],'999999')
        self.assertFalse(self.s.data['enabled'])
    def test_account_change_busy_and_live_protect_preview(self):
        j=self.ready();self.c.cfg['facebook_page_id']='222222'
        with self.assertRaises(ValueError):self.send(j)
        self.c.cfg['facebook_page_id']='123456';self.c.monitor.snapshot=lambda:{'obs':{'active':True}}
        with self.assertRaises(ValueError):self.send(j)
        self.assertEqual(self.s.job(j['id'])['status'],'draft')
    def test_uncertain_write_is_retained_and_not_retried(self):
        j=self.ready();FakePublisher.fail=True
        with patch('studio.Publisher',FakePublisher):self.send(j);self.wait()
        self.assertEqual(self.s.job(j['id'])['status'],'needs_review')
        restarted=Social(self.c,FakePublisher);self.assertEqual(restarted.job(j['id'])['status'],'needs_review');restarted.close()
        with self.assertRaises(ValueError):self.send(j)
        self.assertEqual(FakePublisher.sent,[j['id']])
    def test_youtube_handoff_is_never_claimed_published_and_requires_link(self):
        j=self.ready('youtube','P1');self.st.accounts['youtube']={}
        self.send(j);self.assertEqual(self.s.job(j['id'])['status'],'manual_ready');self.assertEqual(FakePublisher.sent,[])
        with self.assertRaises(ValueError):self.st.receipt({'kind':'youtube','id':j['id'],'confirmed':True,'url':'https://evil.example/post'})
        self.st.receipt({'kind':'youtube','id':j['id'],'confirmed':True,'url':'https://www.youtube.com/post/fixture'})
        self.assertEqual(self.s.job(j['id'])['status'],'manual_done')

    def test_verified_youtube_without_configured_id_can_send_the_unchanged_preview(self):
        self.c.cfg['youtube_channel_id']='';channel='UC'+'b'*22
        self.st.accounts['youtube']={'status':'verified','id':channel,'name':'Verified channel'}
        # The user may already have this preview from before the fix.
        j=self.st.prepare({'platform':'youtube','mode':'P1','media':self.photos(7),'title':'Darshan','caption':'Caption'})
        self.assertEqual(j['studio_target'],channel)
        self.assertEqual(self.st.state()['saved']['youtube'],channel)
        self.send(j)
        self.assertEqual(self.s.job(j['id'])['targets'],{'youtube':channel})
        self.assertEqual(self.s.job(j['id'])['status'],'manual_ready')
        self.assertEqual(self.c.cfg['youtube_channel_id'],'');self.assertEqual(FakePublisher.sent,[])

    def test_youtube_verification_remembers_channel_and_keeps_existing_preview_after_restart(self):
        self.c.cfg['youtube_channel_id']='';channel='UC'+'b'*22
        with patch('studio.YouTube') as yt:
            yt.return_value.owned_channel.return_value={'id':channel,'snippet':{'title':'Verified channel'}}
            self.st.check({'platform':'youtube'});self.wait()
        j=self.st.prepare({'platform':'youtube','mode':'P1','media':self.photos(7),'title':'Darshan'})
        self.assertEqual(self.s.data['youtube_id'],channel)
        self.st=Studio(self.c)
        self.assertEqual(self.st.state()['saved']['youtube'],channel)
        self.send(j);self.assertEqual(self.s.job(j['id'])['targets'],{'youtube':channel})
        self.assertEqual(self.c.cfg['youtube_channel_id'],'');self.assertEqual(FakePublisher.sent,[])

    def test_real_youtube_channel_change_still_blocks_single_and_batch_sends(self):
        self.c.cfg['youtube_channel_id']='';channel='UC'+'b'*22
        self.st.accounts['youtube']={'status':'verified','id':channel}
        media=self.photos(7)
        batch=self.st.prepare_batch({'section':'P1','platforms':['youtube'],'media':{'youtube':{'P1':media}},'title':'Darshan'})
        j=self.s.job(batch['jobs'][0]);self.st.accounts['youtube']['id']='UC'+'c'*22
        with self.assertRaisesRegex(ValueError,'destination changed'):self.send(j)
        with self.assertRaisesRegex(ValueError,'destination changed'):self.st.send_batch({'id':batch['id'],'revision':1,'confirmed':True})
        self.assertEqual(j['status'],'draft');self.assertEqual(FakePublisher.sent,[])

    def test_verified_youtube_conflict_is_rejected_before_creating_a_draft(self):
        self.st.accounts['youtube']={'status':'verified','id':'UC'+'b'*22}
        with self.assertRaisesRegex(ValueError,'differs from Connections'):
            self.st.prepare({'platform':'youtube','mode':'P1','media':self.photos(7),'title':'Darshan'})
        self.assertFalse(self.st.data.get('jobs'));self.assertEqual(FakePublisher.sent,[])
    def test_tokens_are_in_vault_only_blank_preserves_and_direct_check_uses_ig(self):
        self.st.save_instagram({'instagram_login_token':'private-ig-token','instagram_imgbb_key':'private-host-key'})
        self.st.save_instagram({'instagram_login_token':''})
        self.assertEqual(self.c.vault.get('instagram_login_token'),'private-ig-token')
        raw=json.dumps(self.st.state())
        self.assertNotIn('private-ig-token',raw);self.assertNotIn('private-host-key',raw)
        with patch('studio.DirectInstagram.identity',return_value={'id':'777777','name':'test_ig'}):self.st.check({'platform':'instagram'});self.wait()
        self.assertEqual(self.st.accounts['instagram']['status'],'verified');self.assertEqual(self.s.data['studio_instagram_id'],'777777')
    def test_share_receipts_only_after_manual_confirmation_and_edit_resets_them(self):
        share={'date':'2026-10-15','programs':[{'name':'Mangal Arati','youtube':'https://youtube.com/live/abcdefghijk','facebook':''}], 'targets':[{'name':'Community '+str(i),'url':''} for i in range(9)]}
        self.st.save({'share':share});self.assertEqual(self.st.data['receipts'],{})
        with self.assertRaises(ValueError):self.st.receipt({'index':0})
        self.st.receipt({'index':0,'confirmed':True});self.assertIn('0',self.st.data['receipts'])
        self.st.save({'share':share});self.assertIn('0',self.st.data['receipts'])
        self.st.receipt({'index':0,'confirmed':True,'undo':True});self.assertEqual(self.st.data['receipts'],{})
        self.st.receipt({'index':8,'confirmed':True});share['date']='2026-10-16';self.st.save({'share':share});self.assertEqual(self.st.data['receipts'],{})
        self.assertEqual(Studio(self.c).data['share'],share)
    def test_destination_links_reject_arbitrary_sites_and_credentials(self):
        for value in ['javascript:alert(1)','https://facebook.com.evil.test/x','https://secret@facebook.com/post','https://facebook.com:444/post']:
            with self.assertRaises(ValueError):public_link(value,'facebook')
        self.assertEqual(public_link('https://www.whatsapp.com/channel/abc','whatsapp'),'https://www.whatsapp.com/channel/abc')
    def test_corrupt_settings_not_overwritten(self):
        self.st.path.write_text('{broken');st=Studio(self.c)
        with self.assertRaises(ValueError):st.save({'caption':{}})
        self.assertEqual(st.path.read_text(),'{broken')
    def test_direct_graph_uses_instagram_host_bearer_and_redacts_error(self):
        self.c.vault.set('instagram_login_token','private-ig-token')
        adapter=DirectInstagram({**self.c.cfg,'graph_version':'v23.0'},self.c.vault,self.s,self.s.stop)
        response=Mock(ok=True);response.json.return_value={'user_id':'777777','username':'darshan'}
        req=Mock(return_value=response)
        with patch.dict(sys.modules,{'requests':Mock(request=req)}):
            self.assertEqual(adapter.identity()['id'],'777777')
            self.assertEqual(req.call_args.args[1],'https://graph.instagram.com/v23.0/me')
            self.assertEqual(req.call_args.kwargs['headers']['Authorization'],'Bearer private-ig-token')
            self.assertNotIn('access_token',req.call_args.kwargs['params'])
        response.ok=False;response.json.return_value={'error':{'code':190,'message':'private-ig-token'}}
        with patch.dict(sys.modules,{'requests':Mock(request=Mock(return_value=response))}):
            with self.assertRaises(SetupError) as exc:adapter.identity()
            self.assertNotIn('private-ig-token',str(exc.exception))

class StudioHTTP(unittest.TestCase):
    setUp=test_dashboard.Tests.setUp;tearDown=test_dashboard.Tests.tearDown;request=test_dashboard.Tests.request;login=test_dashboard.Tests.login
    def test_auth_csrf_viewer_and_local_credentials(self):
        self.assertEqual(self.request('/api/studio/state')[0],401);self.login()
        self.assertEqual(self.request('/api/studio/save',{'caption':{}},**{'X-CSRF-Token':'bad'})[0],403)
        with patch.object(Handler,'local',return_value=False):
            self.assertEqual(self.request('/api/studio/instagram',{'instagram_login_token':'secret'})[0],403)
            self.assertEqual(self.request('/api/studio/check',{'platform':'facebook'})[0],403)
        self.assertEqual(self.request('/api/studio/instagram',{'instagram_login_token':'secret-value'})[0],200)
        self.assertNotIn('secret-value',json.dumps(self.request('/api/studio/state')[1]))
        with self.server.auth_lock:self.server.sessions[self.cookie.split('=',1)[1]]['role']='viewer'
        self.assertEqual(self.request('/api/studio/state')[0],403)
        self.assertEqual(self.request('/api/studio/send',{'id':'anything'})[0],403)
