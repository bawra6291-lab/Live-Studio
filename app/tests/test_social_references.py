"""Private reference templates remain local and cannot become posting assets."""
import base64,copy,unittest
from unittest.mock import patch
import test_social
from social import Social

class ReferenceTests(unittest.TestCase):
    setUp=test_social.SocialTests.setUp
    tearDown=test_social.SocialTests.tearDown
    def fixture(self):
        images=[]
        for i in range(17):
            w,h=(48,64) if i<7 else (64,48)
            raw=b'\xff\xd8\xff\xc0\x00\x0b\x08'+h.to_bytes(2,'big')+w.to_bytes(2,'big')+b'\x01\x01\x11\x00\xff\xd9'
            images.append('data:image/jpeg;base64,'+base64.b64encode(raw).decode())
        return {'format':'live-desk-darshan-reference-v1','images':images}
    def test_template_persists_without_importing_or_posting_it(self):
        d=self.fixture();self.s.references(d);self.assertEqual(self.s.references()['images'],d['images'])
        snapshot=self.s.snapshot();self.assertTrue(snapshot['reference_ready']);self.assertNotIn('images',snapshot);self.assertEqual(snapshot['assets'],[]);self.assertEqual(snapshot['jobs'],[]);self.assertFalse(snapshot['enabled'])
        s=Social(self.c);self.assertEqual(s.references()['images'],d['images']);s.close()
    def test_bad_template_is_rejected_and_failed_write_restores_state(self):
        before=copy.deepcopy(self.s.data)
        for data in ({}, {'format':'wrong','images':[]}, {**self.fixture(),'images':['https://example.com/photo.jpg']*17}, {**self.fixture(),'images':self.fixture()['images'][::-1]}):
            with self.assertRaises(ValueError):self.s.references(data)
            self.assertEqual(self.s.data,before)
        with patch.object(self.s,'persist',side_effect=OSError('fixture')):
            with self.assertRaises(OSError):self.s.references(self.fixture())
        self.assertEqual(self.s.data,before)
