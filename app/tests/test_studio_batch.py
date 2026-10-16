"""Batch approval and local exports; platform clients are fake."""
import copy, json, unittest, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from zipfile import ZipFile
from unittest.mock import patch
from studio import Studio
from connections import SetupError
from studio_batch import posting_modes
import test_studio
from test_social import FakePublisher


class BatchTests(unittest.TestCase):
    setUp=test_studio.ConnectionsAndPosting.setUp
    tearDown=test_studio.ConnectionsAndPosting.tearDown
    photos=test_studio.ConnectionsAndPosting.photos
    wait=test_studio.ConnectionsAndPosting.wait

    def connected(self):
        self.st.accounts={'facebook':{'status':'verified','id':'123456','name':'Page'},
            'instagram':{'status':'verified','id':'7654321','name':'Instagram'},
            'telegram':{'status':'verified','id':'-1001234567890','bot_id':'123456789','source_channel':'@test_channel','name':'Channel'}}
        self.st.data['telegram']={'channel':'@test_channel'}
        self.c.vault.set('instagram_imgbb_key','fake-hosting-key')

    def prepare(self,platforms=None):
        self.connected();media=self.photos(17)
        groups={'P1':media[:7],'P2':media[7:],'FB':media,'TG':media}
        return self.st.prepare_batch({'section':'BOTH','platforms':platforms or ['facebook','instagram','telegram','youtube'],
            'media':{p:groups for p in ['facebook','instagram','telegram','youtube']},'title':'Darshan','caption':'Hare Krishna'})

    def send(self,batch,**extra):return self.st.send_batch({'id':batch['id'],'revision':batch['revision'],'confirmed':True,**extra})

    def test_batch_builds_separate_ordered_reviews_without_platform_writes(self):
        batch=self.prepare();jobs=[self.s.job(i) for i in batch['jobs']]
        self.assertEqual([(j['platforms'][0],len(j['media'])) for j in jobs],
            [('facebook',7),('facebook',10),('instagram',7),('instagram',10),('telegram',17),('youtube',7),('youtube',10)])
        self.assertEqual(len(set(batch['jobs'])),7);self.assertTrue(all(j['status']=='draft' for j in jobs))
        self.assertEqual(FakePublisher.sent,[]);self.assertFalse(self.s.data['enabled'])
        self.assertEqual(Studio(self.c).data['batches'][0]['id'],batch['id'])
        for p in ['instagram','youtube']:self.assertEqual(posting_modes(p,'FB'),['P1','P2'])

    def test_one_confirmation_sends_api_and_browser_posts_once(self):
        batch=self.prepare()
        with self.assertRaises(ValueError):self.send(batch,confirmed=False)
        with patch('studio.Publisher',FakePublisher),patch('studio.DirectInstagram',FakePublisher),patch('studio.Telegram',FakePublisher),patch('studio.YouTubePost',FakePublisher):
            self.send(batch);self.wait()
        jobs=[self.s.job(i) for i in batch['jobs']]
        self.assertEqual([j['status'] for j in jobs],['published']*7)
        self.assertEqual(FakePublisher.sent,[j['id'] for j in jobs])
        self.assertFalse(self.s.data['enabled']);self.assertEqual(self.st.data['batches'][0]['status'],'completed')
        with self.assertRaises(ValueError):self.send(batch)

    def test_later_validation_failure_makes_no_partial_drafts(self):
        self.connected();media=self.photos(17);before=copy.deepcopy(self.s.data)
        with self.assertRaises(ValueError):self.st.prepare_batch({'section':'BOTH','platforms':['facebook','instagram'],
            'media':{'facebook':{'P1':media[:7],'P2':media[7:]},'instagram':{'P1':media[:7],'P2':media[:7]}},'caption':'Caption'})
        self.assertEqual(self.s.data,before);self.assertFalse(self.st.data.get('jobs'));self.assertFalse(self.st.data.get('batches'))

    def test_changed_target_or_started_draft_blocks_entire_batch_before_first_write(self):
        batch=self.prepare();self.st.accounts['instagram']['id']='2222222'
        with self.assertRaises(ValueError):self.send(batch)
        self.assertEqual(FakePublisher.sent,[])
        self.st.accounts['instagram']['id']='7654321';self.s.job(batch['jobs'][-1])['status']='cancelled'
        with self.assertRaises(ValueError):self.send(batch)
        self.assertEqual(FakePublisher.sent,[]);self.assertEqual(self.st.data['batches'][0]['status'],'draft')

    def test_failure_stops_remaining_posts_and_keeps_successful_receipt(self):
        batch=self.prepare(['facebook','instagram'])
        class FailSecond(FakePublisher):
            sent=[]
            def publish(self,job):
                if len(type(self).sent)==1:
                    type(self).sent.append(job['id']);raise SetupError('Fixture uncertain second write',retryable=False)
                super().publish(job)
        with patch('studio.Publisher',FailSecond),patch('studio.DirectInstagram',FailSecond):
            self.send(batch);self.wait()
        jobs=[self.s.job(i) for i in batch['jobs']]
        self.assertEqual([j['status'] for j in jobs],['published','needs_review','draft','draft'])
        self.assertEqual(len(FailSecond.sent),2);self.assertIn('facebook',jobs[0]['results'])
        self.assertEqual(self.st.data['batches'][0]['status'],'needs_review')
        with self.assertRaises(ValueError):self.send(batch)

    def test_interrupted_batch_is_not_resumed_on_restart(self):
        batch=self.prepare();self.st.data['batches'][0]['status']='publishing';self.st.persist()
        restarted=Studio(self.c);self.assertEqual(restarted.data['batches'][0]['status'],'needs_review')
        self.assertEqual(FakePublisher.sent,[])

    def test_whatsapp_handoff_survives_restart_without_becoming_an_api_receipt(self):
        self.connected();media=self.photos(17)
        batch=self.st.prepare_batch({'section':'BOTH','platforms':['facebook'],
            'media':{'facebook':{'P1':media[:7],'P2':media[7:]}},'title':'Darshan','caption':'Caption',
            'whatsapp':{'mode':'BOTH','media':media,'title':'Darshan','caption':'Exact WhatsApp caption'}})
        with patch('studio.Publisher',FakePublisher):self.send(batch);self.wait()
        restored=Studio(self.c).data['batches'][0]
        self.assertEqual(restored['status'],'manual_ready')
        self.assertEqual(restored['whatsapp'],{'mode':'BOTH','media':media,'title':'Darshan','caption':'Exact WhatsApp caption','status':'manual_ready'})
        self.assertEqual(FakePublisher.sent,batch['jobs'])
        self.assertTrue(all('whatsapp' not in self.s.job(i)['results'] for i in batch['jobs']))
        self.assertFalse(self.st.data.get('receipts'))

    def test_invalid_whatsapp_handoff_creates_no_partial_batch(self):
        self.connected();media=self.photos(17)
        for handoff in [{'mode':'P1','media':media},{'mode':'BOTH','media':media[:7]},
                        {'mode':'BOTH','media':media[:16]+media[:1]},
                        {'mode':'BOTH','media':media,'caption':'x'*5001}]:
            with self.assertRaises(ValueError):self.st.prepare_batch({'section':'BOTH','platforms':['facebook'],
                'media':{'facebook':{'P1':media[:7],'P2':media[7:]}},'whatsapp':handoff})
        self.assertEqual(self.s.data['jobs'],[]);self.assertFalse(self.st.data.get('batches'))
        self.assertEqual(FakePublisher.sent,[])

    def test_local_zip_has_separate_7_and_10_folders_caption_and_no_posting_receipt(self):
        media=self.photos(17)
        export=self.st.prepare_export({'mode':'BOTH','media':media,'title':'Darshan','caption':'Full caption'})
        with self.st.export_package(export['id']) as file,ZipFile(file) as archive:
            self.assertEqual(len([x for x in archive.namelist() if x.startswith('01_Portrait/')]),7)
            self.assertEqual(len([x for x in archive.namelist() if x.startswith('02_Landscape/')]),10)
            self.assertEqual(archive.read('caption.txt'),b'Full caption')
            manifest=json.loads(archive.read('order.json'))
            self.assertEqual(manifest['delivery'],'download');self.assertEqual(manifest['platforms'],[])
            self.assertEqual([x['sha256'] for x in manifest['photos']],media)
        self.assertEqual(self.s.data['jobs'],[]);self.assertEqual(FakePublisher.sent,[])
        self.st.exports[export['id']]['expires']=0
        with self.assertRaises(ValueError):self.st.export_package(export['id'])

    def test_download_validates_duplicates_lengths_and_media_integrity(self):
        media=self.photos(7)
        for values in [media[:6],media[:6]+media[:1]]:
            with self.assertRaises(ValueError):self.st.prepare_export({'mode':'P1','media':values})
        export=self.st.prepare_export({'mode':'P1','media':media})
        path,_=self.s.media_path(media[0]);raw=path.read_bytes();path.write_bytes(b'x'*len(raw))
        with self.assertRaises(ValueError):self.st.export_package(export['id'])

    def test_date_caption_keeps_body_tags_and_persists_selected_day(self):
        self.st.save({'caption':{'title':'Rajbhog Arati · 16 Oct 2026','body':'Unchanged description','tags':'#darshan','date':'2026-10-16'}})
        saved=Studio(self.c).state()['caption'];self.assertEqual(saved['date'],'2026-10-16');self.assertEqual(saved['body'],'Unchanged description')
