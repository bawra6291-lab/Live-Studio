"""Reviewed bulk cleanup: exact selection, protected receipts and crash recovery."""
import copy, unittest
from pathlib import Path
from unittest.mock import patch
import test_social_structure
from social import Social


class BulkTests(unittest.TestCase):
    setUp=test_social_structure.StructureTests.setUp
    tearDown=test_social_structure.StructureTests.tearDown
    upload=test_social_structure.StructureTests.upload
    fixture=test_social_structure.StructureTests.fixture
    save=test_social_structure.StructureTests.save
    build=test_social_structure.StructureTests.build
    approve=test_social_structure.StructureTests.approve
    def preview(self,ids,cleanup=False):return self.s.assets_bulk({'action':'preview','ids':ids,'cleanup_drafts':cleanup})
    def remove(self,plan):return self.s.assets_bulk({'action':'remove','ids':[r['id'] for r in plan['files']],
        'cleanup_drafts':plan['cleanup_drafts'],'fingerprint':plan['fingerprint'],'confirmed':True})
    def test_delete_all_unused_photos_only_after_exact_confirmation(self):
        ids=self.fixture();original=self.c.base/'original.jpg';original.write_bytes(b'original outside library')
        plan=self.preview(ids);self.assertEqual(len(plan['files']),17);self.assertEqual(len(self.s.data['assets']),17)
        with self.assertRaises(ValueError):self.s.assets_bulk({'action':'remove','ids':ids,'fingerprint':plan['fingerprint']})
        with self.assertRaises(ValueError):self.s.assets_bulk({'action':'remove','ids':ids,'fingerprint':'stale','confirmed':True})
        result=self.remove(plan);self.assertEqual(result['removed'],ids);self.assertEqual(result['retained'],[])
        self.assertEqual(self.s.data['assets'],{});self.assertTrue(all(not (self.s.folder/id).exists() for id in ids));self.assertEqual(original.read_bytes(),b'original outside library')
        self.assertFalse(list(self.s.folder.glob('.delete-*')))
    def test_opt_in_cleanup_clears_slots_and_unused_drafts_in_one_operation(self):
        ids=self.fixture();batch=self.save(ids);self.build(batch)
        no_cleanup=self.preview(ids);self.assertTrue(all(r['reason'] for r in no_cleanup['files']))
        plan=self.preview(ids,True);self.assertEqual(len(plan['drafts']),5);self.assertEqual(plan['batch_slots'],list(range(17)))
        result=self.remove(plan);self.assertEqual(len(result['removed']),17);self.assertEqual(result['drafts_removed'],5);self.assertEqual(result['batch_slots_cleared'],17)
        self.assertEqual(self.s.data['jobs'],[]);self.assertEqual(self.s.batch_plan()['slots'],['']*17);self.assertEqual(self.s.batch_plan()['caption'],batch['caption']);self.assertEqual(self.s.batch_plan()['revision'],batch['revision']+1)
    def test_approved_posting_review_and_completed_items_protect_media(self):
        ids=self.fixture();batch=self.save(ids);jobs=self.build(batch)['jobs'];j=self.s.job(jobs[-1]);self.approve(j)
        for status in ('queued','publishing','published','needs_review','manual_ready','manual_done'):
            j['status']=status;plan=self.preview(ids,True);self.assertTrue(all(r['reason'] for r in plan['files']));result=self.remove(plan)
            self.assertEqual(result['removed'],[]);self.assertEqual(len(self.s.data['assets']),17);self.assertEqual(len(self.s.data['jobs']),5)
    def test_new_approval_after_preview_invalidates_deletion(self):
        ids=self.fixture();jobs=self.build(self.save(ids))['jobs'];plan=self.preview(ids,True);self.approve(self.s.job(jobs[-1]))
        with self.assertRaisesRegex(ValueError,'changed'):self.remove(plan)
        self.assertEqual(len(self.s.data['assets']),17);self.assertTrue(all((self.s.folder/id).exists() for id in ids))
    def test_failed_metadata_commit_restores_files_and_restart_recovers_interrupted_moves(self):
        ids=self.fixture();before=copy.deepcopy(self.s.data);plan=self.preview(ids)
        with patch.object(self.s,'persist',side_effect=OSError('fixture storage failure')):
            with self.assertRaises(OSError):self.remove(plan)
        self.assertEqual(self.s.data,before);self.assertTrue(all((self.s.folder/id).exists() for id in ids))
        trash=self.s.folder/'.delete-fixture';trash.mkdir();(self.s.folder/ids[0]).replace(trash/ids[0])
        again=Social(self.c);self.assertTrue((self.s.folder/ids[0]).exists());self.assertFalse(trash.exists());again.close()
        trash.mkdir();(self.s.folder/ids[0]).replace(trash/ids[0]);self.s.data['assets'].pop(ids[0]);self.s.persist()
        again=Social(self.c);self.assertFalse((self.s.folder/ids[0]).exists());self.assertFalse(trash.exists());again.close()
    def test_busy_file_is_retained_while_other_selected_files_are_removed(self):
        ids=self.fixture();plan=self.preview(ids);original=Path.replace
        def move(path,target):
            if path.name==ids[0]:raise PermissionError('fixture open file')
            return original(path,target)
        with patch.object(Path,'replace',move):result=self.remove(plan)
        self.assertEqual(result['removed'],ids[1:]);self.assertEqual(result['retained'][0]['id'],ids[0]);self.assertIn(ids[0],self.s.data['assets']);self.assertTrue((self.s.folder/ids[0]).exists())
