"""Daily workflow invariants, no real accounts or external posting."""
import copy, sys, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import now_ist
from studio import Studio
from studio_workflow import fingerprint
import test_studio
from test_social import FakePublisher

class WorkflowTests(unittest.TestCase):
    setUp=test_studio.ConnectionsAndPosting.setUp
    tearDown=test_studio.ConnectionsAndPosting.tearDown
    photos=test_studio.ConnectionsAndPosting.photos
    ready=test_studio.ConnectionsAndPosting.ready
    wait=test_studio.ConnectionsAndPosting.wait

    def test_saved_templates_and_audio_reference_are_real_and_survive_restart(self):
        values={'templates':{'facebook':'{{event_title}} {{date_short}}','youtube_P1':'7 photos'},'telegram_order':'mixed','instagram_audio':{'required':True,'reference':'My saved track'}}
        self.st.save({'workflow':values})
        self.assertEqual(Studio(self.c).state()['workflow'],values)
        for invalid in [{'templates':{'unknown':'text'}},{'templates':{'facebook':2}},{'instagram_audio':{'required':True}},{'telegram_order':'random'}]:
            before=copy.deepcopy(self.st.data)
            with self.assertRaises(ValueError):self.st.save({'workflow':invalid})
            self.assertEqual(self.st.data,before)

    def test_pretest_checks_exact_media_and_target_without_calls_or_state_writes(self):
        j=self.ready();before=copy.deepcopy(self.s.data);settings=copy.deepcopy(self.st.data)
        with patch('studio.Publisher') as pub:
            report=self.st.pretest({'jobs':[j['id']]});pub.assert_not_called()
        self.assertTrue(report['ready']);self.assertEqual(len(report['fingerprint']),64)
        self.assertEqual(self.s.data,before);self.assertEqual(self.st.data,settings)
        self.c.cfg['facebook_page_id']='different'
        self.assertFalse(self.st.pretest({'jobs':[j['id']]})['ready'])
        self.c.cfg['facebook_page_id']='123456';path,_=self.s.media_path(j['media'][0]);path.write_bytes(b'corrupt')
        self.assertFalse(self.st.pretest({'jobs':[j['id']]})['ready'])

    def test_pretest_does_not_navigate_or_connect_chrome(self):
        j=self.ready('youtube','P1');self.st.pretest({'jobs':[j['id']]})
        self.c.visible.browser.ensure.assert_not_called()
        self.assertFalse(self.st.pretest({'jobs':[]})['ready'])

    def test_audio_required_draft_cannot_send_or_silently_drop_track(self):
        self.st.save({'workflow':{'templates':{},'instagram_audio':{'required':True,'reference':'Saved kirtan'}}})
        j=self.ready('instagram','P1');self.c.vault.set('instagram_imgbb_key','fake')
        with patch('studio.DirectInstagram',FakePublisher):
            with self.assertRaisesRegex(ValueError,'Needs audio action'):self.st.send({'id':j['id'],'revision':j['revision'],'confirmed':True})
        self.assertEqual(FakePublisher.sent,[]);self.assertEqual(self.s.job(j['id'])['status'],'draft')
        self.st.save({'workflow':{'templates':{}}})
        with self.assertRaisesRegex(ValueError,'Needs audio action'):self.st.validate_send(self.s.job(j['id']))

    def test_service_date_frozen_and_invalid_day_creates_no_orphan(self):
        self.ready();media=self.photos(7);before=copy.deepcopy(self.s.data)
        with self.assertRaises(ValueError):self.st.prepare({'platform':'youtube','mode':'P1','media':media,'service_date':'bad'})
        self.assertEqual(before,self.s.data)
        j=self.st.prepare({'platform':'youtube','mode':'P1','media':media,'service_date':'2000-01-01'})
        with self.assertRaisesRegex(ValueError,'service date'):self.st.validate_send(self.s.job(j['id']))

    def test_platform_captions_frozen_independently_and_template_changes_do_not_edit_jobs(self):
        self.ready();media=self.photos(17)
        batch=self.st.prepare_batch({'section':'BOTH','platforms':['facebook','youtube'],'media':{p:{'P1':media[:7],'P2':media[7:]} for p in ['facebook','youtube']},'caption':'fallback','captions':{'facebook_P1':'FB portrait','youtube_P2':'YT landscape'},'service_date':now_ist().date().isoformat()})
        self.assertEqual([self.s.job(i)['caption'] for i in batch['jobs']],['FB portrait','fallback','fallback','YT landscape'])
        old=copy.deepcopy([self.s.job(i) for i in batch['jobs']]);self.st.save({'workflow':{'templates':{'facebook':'Changed'}}})
        self.assertEqual(old,[self.s.job(i) for i in batch['jobs']])

    def share(self):
        media=self.photos(2);return {'date':now_ist().date().isoformat(),'programs':[{'name':'Darshan','youtube':'https://www.youtube.com/watch?v=abcdefghijk','facebook':''}],'targets':[{'name':str(i),'url':''} for i in range(9)],'sequence':'rgm_jbs','photos':dict(zip(['L1','L5'],media))}

    def receipt(self,index,step,**extra):return self.st.receipt({'kind':'whatsapp','index':index,'step':step,'fingerprint':fingerprint(self.st.data['share']),'confirmed':True,**extra})

    def test_pair_receipts_enforce_order_per_target_and_survive_restart(self):
        self.st.save({'share':self.share()})
        with self.assertRaises(ValueError):self.receipt(0,'jbs')
        self.receipt(0,'rgm');self.receipt(0,'jbs')
        with self.assertRaises(ValueError):self.receipt(1,'jbs')
        self.assertEqual(len(Studio(self.c).data['receipts']),2)
        self.receipt(0,'rgm',undo=True);self.assertEqual(self.st.data['receipts'],{})
        self.assertEqual(FakePublisher.sent,[])

    def test_pair_photo_and_link_changes_invalidate_receipts_and_stale_fingerprints(self):
        share=self.share();self.st.save({'share':share});self.receipt(0,'rgm');old=fingerprint(self.st.data['share'])
        share['photos']={'L1':share['photos']['L5'],'L5':share['photos']['L1']};self.st.save({'share':share})
        self.assertEqual(self.st.data['receipts'],{})
        with self.assertRaises(ValueError):self.receipt(0,'rgm',fingerprint=old)
        with self.assertRaises(ValueError):self.receipt(0,None)
