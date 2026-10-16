"""Independent 7/10/17 ordering, migration and asset lifetime protection."""
import copy,json,unittest
from unittest.mock import patch
import test_social_structure as fixtures
image_bytes=fixtures.image_bytes
from social import Social

class ColumnsTests(unittest.TestCase):
    setUp=fixtures.StructureTests.setUp
    tearDown=fixtures.StructureTests.tearDown
    upload=fixtures.StructureTests.upload
    fixture=fixtures.StructureTests.fixture
    save=fixtures.StructureTests.save
    build=fixtures.StructureTests.build
    def columns(self):
        ids=self.fixture()
        fb=[self.upload(image_bytes(40+i,i%2==0),f'facebook-{i}.jpg')['id'] for i in range(17)]
        return {'portrait':ids[:7][::-1],'landscape':ids[7:][::-1],'facebook':fb[::-1]}
    def save_columns(self,groups):
        return self.save(groups['portrait']+groups['landscape'],mode='columns',groups=groups)
    def test_independent_groups_keep_exact_order_cover_and_restart(self):
        groups=self.columns();plan=self.save_columns(groups);result=self.build(plan)
        jobs=[self.s.job(i) for i in result['jobs']]
        self.assertEqual([j['media'] for j in jobs],[groups['portrait'],groups['landscape'],groups['portrait'],groups['landscape'],groups['facebook']])
        self.assertTrue(all(j['status']=='draft' for j in jobs))
        self.assertTrue(self.build(plan)['already_built'])
        reloaded=Social(self.c);self.assertEqual(reloaded.batch_plan()['groups'],groups);reloaded.close()
        reordered=copy.deepcopy(groups);reordered['facebook'].reverse();self.save_columns(reordered)
        self.assertEqual([j['media'] for j in jobs],[groups['portrait'],groups['landscape'],groups['portrait'],groups['landscape'],groups['facebook']])
    def test_missing_and_duplicate_facebook_positions_never_build(self):
        groups=self.columns()
        for bad in [groups['facebook'][:-1]+[''],groups['facebook'][:-1]+[groups['facebook'][0]]]:
            plan=self.save_columns({**groups,'facebook':bad})
            with self.assertRaises(ValueError):self.build(plan)
        self.assertEqual(self.s.data['jobs'],[])
    def test_legacy_migration_retains_built_jobs_and_rejects_old_client_overwrite(self):
        plan=self.save(self.fixture());result=self.build(plan)
        self.s.data['batch'].pop('groups',None);self.s.data['batch'].pop('mode',None);self.s.persist()
        legacy=self.s.batch_plan();updated=self.s.batch({**legacy,'action':'save','mode':'columns'})
        self.assertEqual(updated['revision'],legacy['revision']);self.assertEqual(self.build(updated)['jobs'],result['jobs'])
        with self.assertRaisesRegex(ValueError,'Reload'):self.s.batch({**updated,'action':'save','mode':'legacy'})
    def test_facebook_only_assignment_protected_and_cleanup_clears_it(self):
        groups=self.columns();self.save_columns(groups);ident=groups['facebook'][0]
        with self.assertRaises(ValueError):self.s.asset_update({'id':ident,'action':'remove'})
        preview=self.s.assets_bulk({'action':'preview','ids':[ident],'cleanup_drafts':False});self.assertTrue(preview['files'][0]['reason'])
        preview=self.s.assets_bulk({'action':'preview','ids':[ident],'cleanup_drafts':True});self.assertEqual(preview['batch_slots'],[17])
        self.s.assets_bulk({'action':'remove','ids':[ident],'cleanup_drafts':True,'fingerprint':preview['fingerprint'],'confirmed':True})
        self.assertEqual(self.s.batch_plan()['groups']['facebook'][0],'');self.assertEqual(self.s.batch_plan()['groups']['portrait'],groups['portrait'])
    def test_failed_save_restores_all_columns(self):
        groups=self.columns();self.save_columns(groups);before=copy.deepcopy(self.s.data);groups['facebook'].reverse()
        with patch.object(self.s,'persist',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.save_columns(groups)
        self.assertEqual(self.s.data,before)
