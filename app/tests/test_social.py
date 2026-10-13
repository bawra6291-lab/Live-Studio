"""Posting approval/recovery and adapter tests; no external account is contacted."""
import base64, copy, json, sys, tempfile, threading, unittest
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import now_ist
from social import Social, https_media
from social_publish import Publisher
from connections import SetupError
from test_dashboard import Vault

PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAIAAAABCAIAAAB7QOjdAAAAD0lEQVR4nGN4sKBAxtYIAAsnAnyYPiW8AAAAAElFTkSuQmCC')
MP4=b'\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isommp42'+b'\x00\x00\x00\x08mdat'

class FakePublisher:
    sent=[];fail=False
    def __init__(self,*args):self.manager=args[2]
    def check(self,ig):return {'facebook':{'id':'123456','name':'Fixture'},'youtube':{'id':'UC'+'a'*22,'name':'Fixture'}}
    def publish(self,job):
        type(self).sent.append(job['id']);self.manager.checkpoint(job['id'],'facebook',status='sending')
        if type(self).fail:raise SetupError('Uncertain write',retryable=False)
        for p in job['platforms']:self.manager.checkpoint(job['id'],p,status='published',id='123456_789012',url='https://www.facebook.com/123456_789012')
    def review_existing(self,job,platform,ident):return {'id':ident,'url':'https://www.facebook.com/'+ident}

class SocialTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.c=SimpleNamespace(base=Path(self.tmp.name),lock=threading.RLock(),closing=False,maintenance=False,armed=False,mode='',worker=None,cfg={'facebook_page_id':'123456','youtube_channel_id':'UC'+'a'*22},vault=Vault(),log=Mock(),monitor=SimpleNamespace(snapshot=lambda:{'obs':{'active':False}}))
        self.s=Social(self.c,FakePublisher);FakePublisher.sent=[];FakePublisher.fail=False
    def tearDown(self):
        self.s.close()
        if self.s.worker:self.s.worker.join(3)
        self.tmp.cleanup()
    def draft(self,**extra):
        return self.s.draft({'title':'Darshan','caption':'Hare Krishna','platforms':['facebook'],'media':[],'publish_at':(now_ist()+timedelta(minutes=10)).isoformat(),**extra})
    def approve(self,j):self.s.command({'action':'approve','id':j['id'],'revision':j['revision'],'confirmed':True})
    def enable(self):self.s.command({'action':'enable','confirmed':True})
    def wait(self):
        if self.s.worker:self.s.worker.join(3)
    def test_draft_and_enable_never_publish_unapproved_content(self):
        self.draft();self.enable();self.s.tick(now_ist()+timedelta(minutes=11));self.assertEqual(FakePublisher.sent,[])
        with self.assertRaises(ValueError):self.s.command({'action':'enable'})
    def test_confirmed_future_approved_revision_sends_once_after_due(self):
        j=self.draft();self.approve(j);self.enable();self.s.tick();self.assertEqual(FakePublisher.sent,[])
        self.s.tick(now_ist()+timedelta(minutes=11));self.wait();self.s.tick(now_ist()+timedelta(minutes=12));self.wait()
        self.assertEqual(FakePublisher.sent,[j['id']]);self.assertEqual(self.s.job(j['id'])['status'],'published')
    def test_edit_revokes_approval_and_stale_preview_is_rejected(self):
        j=self.draft();self.approve(j)
        with self.assertRaises(ValueError):self.draft(id=j['id'],revision=j['revision'])
        self.s.command({'action':'cancel','id':j['id'],'revision':j['revision']})
        changed=self.draft(id=j['id'],revision=j['revision'],caption='Changed')
        self.assertEqual(changed['status'],'draft');self.assertFalse(changed['targets']);self.assertIsNone(changed['approved_at'])
        with self.assertRaises(ValueError):self.approve(j)
        with self.assertRaises(ValueError):self.draft(id=j['id'],revision=j['revision'])
    def test_destination_change_and_missed_window_do_not_publish(self):
        j=self.draft();self.approve(j);self.enable();self.c.cfg['facebook_page_id']='654321';self.s.tick(now_ist()+timedelta(minutes=11));self.assertEqual(FakePublisher.sent,[]);self.assertEqual(self.s.job(j['id'])['status'],'needs_review')
        self.c.cfg['facebook_page_id']='123456';j=self.draft();self.approve(j);self.s.tick(now_ist()+timedelta(minutes=30));self.assertEqual(FakePublisher.sent,[])
    def test_uncertain_write_pauses_queue_and_restart_never_repeats(self):
        j=self.draft();self.approve(j);self.enable();FakePublisher.fail=True;self.s.tick(now_ist()+timedelta(minutes=11));self.wait()
        self.assertEqual(self.s.job(j['id'])['status'],'needs_review');self.assertFalse(self.s.data['enabled'])
        restarted=Social(self.c,FakePublisher);restarted.data['enabled']=True;restarted.tick(now_ist()+timedelta(minutes=12));self.assertEqual(FakePublisher.sent,[j['id']]);restarted.close()
        self.s.job(j['id'])['status']='publishing';self.s.persist();restarted=Social(self.c,FakePublisher);self.assertEqual(restarted.job(j['id'])['status'],'needs_review');restarted.close()
    def test_partial_success_receipt_is_retained(self):
        j=self.draft(platforms=['facebook','youtube'],media=[self.upload(MP4,'test.mp4')['id']]);self.approve(j)
        self.s.job(j['id'])['status']='publishing';self.s.checkpoint(j['id'],'facebook',status='published',id='123456_789012');self.s.persist()
        restarted=Social(self.c,FakePublisher);self.assertEqual(restarted.job(j['id'])['results']['facebook']['id'],'123456_789012');self.assertEqual(restarted.job(j['id'])['status'],'needs_review');restarted.close()
    def test_live_update_shutdown_blocks_posting(self):
        j=self.draft();self.approve(j);self.enable()
        self.c.monitor.snapshot=lambda:{'obs':{'active':True}};self.s.tick(now_ist()+timedelta(minutes=11));self.assertEqual(FakePublisher.sent,[])
        self.c.monitor.snapshot=lambda:{'obs':{'active':False}};self.c.maintenance=True;self.s.tick(now_ist()+timedelta(minutes=11));self.assertEqual(FakePublisher.sent,[])
        self.c.maintenance=False;self.c.closing=True;self.s.tick(now_ist()+timedelta(minutes=11));self.assertEqual(FakePublisher.sent,[])
    def upload(self,raw,name='test.png'):
        upload=self.s.begin_upload({'name':name,'size':len(raw)})
        self.s.upload_chunk({'upload':upload['upload'],'offset':0,'data':base64.b64encode(raw).decode()})
        return self.s.finish_upload({'upload':upload['upload']})
    def test_import_deduplicates_and_rejects_fake_images_offsets_paths(self):
        a=self.upload(PNG,'../darshan.png');self.assertEqual(a['name'],'darshan.png');self.assertEqual(a['id'],self.upload(PNG)['id']);self.assertEqual(len(self.s.data['assets']),1)
        begin=self.s.begin_upload({'name':'test.jpg','size':3})
        with self.assertRaises(ValueError):self.s.upload_chunk({'upload':begin['upload'],'offset':1,'data':'YWJj'})
        self.s.upload_chunk({'upload':begin['upload'],'offset':0,'data':'YWJj'})
        with self.assertRaises(ValueError):self.s.finish_upload({'upload':begin['upload']})
        with self.assertRaises(ValueError):self.s.media_path('../settings.json')
    def test_approved_media_cannot_be_replaced_or_removed(self):
        a=self.upload(PNG);j=self.draft(media=[a['id']]);self.approve(j)
        with self.assertRaises(ValueError):self.s.asset_update({'id':a['id'],'public_url':'https://example.com/other.png'})
        with self.assertRaises(ValueError):self.s.asset_update({'id':a['id'],'action':'remove'})
    def test_platform_media_constraints(self):
        a=self.upload(PNG)
        with self.assertRaises(ValueError):self.draft(platforms=['youtube'],media=[a['id']])
        with self.assertRaises(ValueError):self.draft(platforms=['instagram'],media=[])
        self.s.data['instagram_id']='1234567';j=self.draft(platforms=['instagram'],media=[a['id']])
        with self.assertRaises(ValueError):self.approve(j)
        for url in ('http://example.com/a.mp4','https://127.0.0.1/a','https://localhost/a','https://user:password@example.com/a'):
            with self.assertRaises(ValueError):https_media(url)
    def test_read_only_reconcile_does_not_send_another_post(self):
        j=self.draft();self.approve(j);self.s.job(j['id'])['status']='needs_review';self.s.persist()
        self.s.reconcile({'id':j['id'],'revision':j['revision'],'platform':'facebook','post_id':'123456_789012','confirmed':True});self.wait()
        self.assertEqual(FakePublisher.sent,[]);self.assertEqual(self.s.job(j['id'])['status'],'published')
    def test_corrupt_storage_retained_and_posting_disabled(self):
        self.s.path.write_text('broken json');again=Social(self.c,FakePublisher);self.assertTrue(again.error);self.assertEqual(self.s.path.read_text(),'broken json')
        with self.assertRaises(ValueError):again.draft({})
        again.close()

class AdapterTests(unittest.TestCase):
    setUp=SocialTests.setUp
    tearDown=SocialTests.tearDown
    draft=SocialTests.draft
    upload=SocialTests.upload
    def publisher(self):return Publisher({**self.c.cfg,'graph_version':'v23.0'},self.c.vault,self.s,self.s.stop)
    def test_facebook_streamed_multipart_preserves_media_and_receipt(self):
        a=self.upload(PNG)
        j=self.draft(media=[a['id']]);p=self.publisher()
        response=Mock(ok=True);response.json.return_value={'post_id':'123456_789012'}
        with patch('requests.request',return_value=response) as request:
            p.post_facebook(j);kwargs=request.call_args.kwargs;body=kwargs['data'];self.assertEqual(len(body),int(kwargs['headers']['Content-Length']));data=b''.join(body);self.assertIn(PNG,data)
            import requests
            prepared=requests.Request('POST','https://graph.facebook.com/v23.0/123456/photos',data=body,headers=kwargs['headers']).prepare()
            self.assertNotIn('Transfer-Encoding',prepared.headers)
        self.assertEqual(self.s.job(j['id'])['results']['facebook']['status'],'published')
    def test_facebook_album_uploads_unpublished_then_sends_one_feed_post(self):
        import zlib
        text=b'Comment\0fixture';chunk=len(text).to_bytes(4,'big')+b'tEXt'+text+zlib.crc32(b'tEXt'+text).to_bytes(4,'big')
        a=self.upload(PNG);b=self.upload(PNG[:-12]+chunk+PNG[-12:]);j=self.draft(media=[a['id'],b['id']]);p=self.publisher();p.graph=Mock(side_effect=[{'id':'photo1'},{'id':'photo2'},{'id':'123456_789012'}]);p.post_facebook(j)
        self.assertEqual(p.graph.call_count,3);self.assertEqual(p.graph.call_args_list[0].args[2],{'published':'false'})
        self.assertEqual(json.loads(p.graph.call_args_list[2].args[2]['attached_media']),[{'media_fbid':'photo1'},{'media_fbid':'photo2'}])
        self.assertEqual(self.s.job(j['id'])['results']['facebook']['status'],'published')
    def test_video_upload_stays_in_approved_channel_and_detects_forced_private(self):
        a=self.upload(MP4,'test.mp4');j=self.draft(platforms=['youtube'],media=[a['id']],privacy='public');p=self.publisher();p.yt.session=Mock()
        start=Mock(status_code=200,headers={'Location':'https://www.googleapis.com/upload/youtube/v3/videos?upload_id=fixture'})
        finish=Mock(status_code=201);finish.json.return_value={'id':'abcdefghijk','status':{'privacyStatus':'private'}};p.yt.session.post.return_value=start;p.yt.session.put.return_value=finish
        with self.assertRaises(SetupError):p.post_youtube(j)
        result=self.s.job(j['id'])['results']['youtube'];self.assertEqual(result['id'],'abcdefghijk');self.assertEqual(result['status'],'uploaded');self.assertEqual(result['visibility'],'private')
        self.assertEqual(p.yt.session.post.call_count,1)
    def test_upload_session_foreign_host_never_receives_video_or_credentials(self):
        a=self.upload(MP4,'test.mp4');j=self.draft(platforms=['youtube'],media=[a['id']]);p=self.publisher();p.yt.session=Mock();p.yt.session.post.return_value=Mock(status_code=200,headers={'Location':'https://evil.example/upload'})
        with self.assertRaises(SetupError):p.post_youtube(j)
        p.yt.session.put.assert_not_called()
    def test_instagram_success_persisted_even_if_permalink_read_fails(self):
        a=self.upload(PNG);j=self.draft(platforms=['instagram'],media=[a['id']]);j['targets']={'instagram':'1234567'};p=self.publisher();p.instagram_source=Mock(return_value='https://cdn.example.com/same.jpg');p.wait_container=Mock()
        p.graph=Mock(side_effect=[{'id':'container123'},{'id':'media12345'},SetupError('Read failed')]);p.post_instagram(j)
        result=self.s.job(j['id'])['results']['instagram'];self.assertEqual(result['status'],'published');self.assertEqual(result['id'],'media12345');self.assertEqual(p.graph.call_args_list[1].args[1],'1234567/media_publish')


class HttpTests(unittest.TestCase):
    from test_dashboard import Tests as DashboardTests
    setUp=DashboardTests.setUp
    tearDown=DashboardTests.tearDown
    request=DashboardTests.request
    login=DashboardTests.login
    def test_social_state_and_imports_require_session_role_and_csrf(self):
        from dashboard import Handler
        self.assertEqual(self.request('/api/social/state')[0],401)
        self.assertEqual(self.request('/api/social/export/unknown')[0],401)
        self.login()
        body={'name':'darshan.png','size':len(PNG)}
        self.assertEqual(self.request('/api/social/upload/begin',body,**{'X-CSRF-Token':'wrong'})[0],403)
        self.assertEqual(self.request('/api/social/assets/bulk',{'action':'preview','ids':[]},**{'X-CSRF-Token':'wrong'})[0],403)
        with self.server.auth_lock:self.server.sessions[self.cookie.split('=',1)[1]]['role']='viewer'
        self.assertEqual(self.request('/api/social/upload/begin',body)[0],403)
        self.assertEqual(self.request('/api/social/assets/bulk',{'action':'preview','ids':[]})[0],403)
        with self.server.auth_lock:self.server.sessions[self.cookie.split('=',1)[1]]['role']='owner'
        with patch.object(Handler,'local',return_value=False):self.assertEqual(self.request('/api/social/account',{'instagram_id':'1234567'})[0],403)
        status,start,_=self.request('/api/social/upload/begin',body);self.assertEqual(status,200)
        self.assertEqual(self.request('/api/social/upload/chunk',{'upload':start['upload'],'offset':0,'data':base64.b64encode(PNG).decode()})[0],200)
        status,asset,_=self.request('/api/social/upload/finish',{'upload':start['upload']});self.assertEqual(status,200)
        status,raw,_=self.request('/api/social/media/'+asset['id'],**{'Range':'bytes=0-7'});self.assertEqual(status,206);self.assertEqual(raw,PNG[:8])
        self.assertEqual(self.request('/api/social/media/../settings.json')[0],404)
        snapshot=self.request('/api/social/state')[1];self.assertNotIn('sensitive-page-token',json.dumps(snapshot));self.assertFalse(snapshot['enabled'])
        _,job,_=self.request('/api/social/draft',{'title':'Private draft name','caption':'Unpublished private caption','media':[asset['id']],'platforms':['facebook'],'publish_at':(now_ist()+timedelta(minutes=10)).isoformat()})
        status,raw,_=self.request('/api/social/export/'+job['id']);self.assertEqual(status,200);self.assertTrue(raw.startswith(b'PK'))
        self.assertEqual(self.request('/api/social/batch',{'action':'save','revision':0,'slots':[asset['id']]+['']*16,'title':'Private batch','caption':'Private batch caption','times':dict.fromkeys(('portrait','landscape','facebook'),'')},**{'X-CSRF-Token':'wrong'})[0],403)
        self.assertEqual(self.request('/api/social/batch',{'action':'save','revision':0,'slots':[asset['id']]+['']*16,'title':'Private batch','caption':'Private batch caption','times':dict.fromkeys(('portrait','landscape','facebook'),'')})[0],200)
        with self.server.auth_lock:self.server.sessions[self.cookie.split('=',1)[1]]['role']='viewer'
        self.assertEqual(self.request('/api/social/media/'+asset['id'])[0],403)
        self.assertEqual(self.request('/api/social/export/'+job['id'])[0],403)
        self.assertEqual(self.request('/api/social/batch',{'action':'build','revision':1})[0],403)
        restricted=self.request('/api/social/state')[1];self.assertEqual(restricted['assets'],[]);self.assertEqual(restricted['batch'],{});self.assertNotIn('Private batch',json.dumps(restricted));self.assertNotIn('Unpublished private caption',json.dumps(restricted));self.assertNotIn('Private draft name',json.dumps(restricted))
    def test_unconfirmed_approval_and_enable_rejected_at_http_boundary(self):
        self.login();payload={'title':'Darshan','caption':'Caption','media':[],'platforms':['facebook'],'publish_at':(now_ist()+timedelta(minutes=10)).isoformat()}
        status,j,_=self.request('/api/social/draft',payload);self.assertEqual(status,200)
        self.assertEqual(self.request('/api/social/action',{'action':'approve','id':j['id'],'revision':j['revision']})[0],409)
        self.assertEqual(self.request('/api/social/action',{'action':'enable'})[0],409)
        self.assertEqual(self.request('/api/social/action',{'action':'approve','id':j['id'],'revision':j['revision'],'confirmed':True})[0],200)
        self.assertEqual(self.c.social.job(j['id'])['status'],'queued');self.assertFalse(self.c.social.data['enabled'])
