"""Exact PPT ordering, atomic batch creation, and manual handoff isolation."""
import hashlib, json, struct, sys, zlib, unittest
from pathlib import Path
from datetime import timedelta
from zipfile import ZipFile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_social
FakePublisher=test_social.FakePublisher
from social import Social
from social_structure import PORTRAIT, LANDSCAPE, FACEBOOK_ORDER
from core import now_ist


def image_bytes(i, portrait):
    # Controller tests exercise the same dimension/sniffing boundary as imports.
    # Real decoded crops are exercised by the browser canvas test.
    width,height=(300,400) if portrait else (400,300)
    if not portrait:
        return b'\xff\xd8\xff\xc0\x00\x0b\x08'+height.to_bytes(2,'big')+width.to_bytes(2,'big')+b'\x01\x01\x11\x00'+b'\xff\xfe\x00\x03'+bytes([i])+b'\xff\xd9'
    def chunk(kind,data):return len(data).to_bytes(4,'big')+kind+data+zlib.crc32(kind+data).to_bytes(4,'big')
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\x00'+bytes([i,50,100])*width)*height))+chunk(b'IEND',b'')


class StructureTests(unittest.TestCase):
    setUp=test_social.SocialTests.setUp
    tearDown=test_social.SocialTests.tearDown
    upload=test_social.SocialTests.upload
    draft=test_social.SocialTests.draft
    approve=test_social.SocialTests.approve
    enable=test_social.SocialTests.enable
    def fixture(self):
        ids=[]
        for i,(_,name) in enumerate(PORTRAIT+LANDSCAPE):
            ids.append(self.upload(image_bytes(i,i<7),name+('.png' if i<7 else '.jpg'))['id'])
        return ids
    def save(self,ids,**extra):
        when=(now_ist()+timedelta(minutes=20)).isoformat()
        return self.s.batch({'action':'save','revision':self.s.batch_plan()['revision'],
            'slots':ids,'title':'Morning darshan','caption':'Shared caption',
            'times':dict.fromkeys(('portrait','landscape','facebook'),when),**extra})
    def build(self,plan):return self.s.batch({'action':'build','revision':plan['revision']})
    def test_exact_five_posts_cover_and_facebook_order(self):
        ids=self.fixture();plan=self.save(ids);created=self.build(plan)
        jobs=[self.s.job(i) for i in created['jobs']]
        self.assertEqual([j['platforms'] for j in jobs],[['instagram'],['instagram'],['youtube'],['youtube'],['facebook']])
        self.assertEqual([j['delivery'] for j in jobs],['manual','api','manual','manual','api'])
        self.assertEqual([len(j['media']) for j in jobs],[7,10,7,10,17])
        self.assertEqual(jobs[0]['media'],ids[:7]);self.assertEqual(jobs[1]['media'],ids[7:])
        self.assertEqual(jobs[4]['media'],[ids[i] for i in FACEBOOK_ORDER])
        self.assertEqual(jobs[4]['media'][0],ids[7]);self.assertEqual({j['caption'] for j in jobs},{'Shared caption'})
        self.assertTrue(all(j['status']=='draft' and not j['approved_at'] for j in jobs))
        again=self.build(plan);self.assertTrue(again['already_built']);self.assertEqual(again['jobs'],created['jobs']);self.assertEqual(len(self.s.data['jobs']),5)
        self.enable();self.s.tick(now_ist()+timedelta(minutes=21));self.assertEqual(FakePublisher.sent,[])
        restarted=Social(self.c,FakePublisher);self.assertEqual(restarted.batch_plan()['slots'],ids);self.assertEqual(restarted.batch_plan()['jobs'],created['jobs']);restarted.close()
    def test_missing_duplicate_wrong_crop_and_stale_mapping_fail(self):
        ids=self.fixture();plan=self.save(ids[:-1]+[''])
        with self.assertRaises(ValueError):self.build(plan)
        plan=self.save(ids[:-1]+[ids[0]])
        with self.assertRaises(ValueError):self.build(plan)
        plan=self.save(ids)
        with self.assertRaises(ValueError):self.s.batch({'action':'build','revision':plan['revision']-1})
        self.s.data['assets'][ids[0]]['width']=350
        with self.assertRaisesRegex(ValueError,'3:4'):self.build(plan)
        self.assertEqual(self.s.data['jobs'],[])
    def test_failed_last_post_leaves_no_partial_batch_on_disk(self):
        ids=self.fixture();when=(now_ist()+timedelta(minutes=20)).isoformat()
        plan=self.save(ids,times={'portrait':when,'landscape':when,'facebook':'invalid'})
        with self.assertRaises(ValueError):self.build(plan)
        self.assertEqual(self.s.data['jobs'],[]);self.assertEqual(json.loads(self.s.path.read_text())['jobs'],[])
    def test_manual_ready_never_calls_api_even_after_enable_restart(self):
        plan=self.save(self.fixture());job=self.s.job(self.build(plan)['jobs'][2]);self.approve(job)
        self.assertEqual(job['status'],'manual_ready');self.enable();self.s.tick(now_ist()+timedelta(minutes=21));self.assertEqual(FakePublisher.sent,[])
        with self.assertRaises(ValueError):self.s.command({'action':'manual_done','id':job['id'],'revision':job['revision']})
        self.s.command({'action':'manual_done','id':job['id'],'revision':job['revision'],'confirmed':True})
        self.assertEqual(job['status'],'manual_done');self.assertEqual(job['results'],{})
        restarted=Social(self.c,FakePublisher);restarted.tick(now_ist()+timedelta(minutes=21));self.assertEqual(FakePublisher.sent,[]);restarted.close()
        with self.assertRaises(ValueError):self.s.asset_update({'id':job['media'][0],'action':'remove'})
    def test_export_is_ordered_and_preserves_hash_caption_without_posting(self):
        ids=self.fixture();plan=self.save(ids);job=self.s.job(self.build(plan)['jobs'][4])
        with self.s.export_post(job['id']) as file,ZipFile(file) as archive:
            manifest=json.loads(archive.read('order.json'));self.assertEqual(manifest['cover'],1)
            self.assertEqual([r['sha256'] for r in manifest['photos']],job['media'])
            for row in manifest['photos']:self.assertEqual(hashlib.sha256(archive.read(row['file'])).hexdigest(),row['sha256'])
            self.assertTrue(manifest['photos'][0]['file'].startswith('01_DSC03654'))
            self.assertEqual(archive.read('caption.txt').decode(),'Shared caption')
        self.assertEqual(FakePublisher.sent,[]);self.assertEqual(job['status'],'draft')
        (self.s.folder/ids[7]).write_bytes(b'x'*self.s.data['assets'][ids[7]]['size'])
        with self.assertRaisesRegex(ValueError,'damaged'):self.s.export_post(job['id'])
    def test_seventeen_photos_only_for_facebook_and_batch_references_protect_assets(self):
        ids=self.fixture();self.draft(media=ids)
        with self.assertRaises(ValueError):self.draft(media=ids,platforms=['instagram'])
        with self.assertRaises(ValueError):self.draft(media=ids,platforms=['facebook','instagram'])
        plan=self.save(ids)
        with self.assertRaises(ValueError):self.s.asset_update({'id':ids[0],'action':'remove'})
        self.assertEqual(self.s.batch({**plan,'action':'save'})['revision'],plan['revision'])
