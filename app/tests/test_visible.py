import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from visible import Visible, VisibleServices, validate_recipe
from visible_browser import Browser, origin, RECORDER, target_script
from connections import SetupError


def recipe():
    return {'identity':{'locator':{'css':'#account'},'text':'Test Temple'},
            'steps':[{'kind':'fill','locator':{'css':'#title'},'variable':'title'},
                     {'kind':'click','locator':{'css':'#submit'}}]}


class VisibleTests(unittest.TestCase):
    def test_recipe_rejects_code_and_unmapped_or_secret_fields(self):
        for variable in ('','password','camera_password','facebook_page_token'):
            data=recipe();data['steps'][0]['variable']=variable
            with self.assertRaises(ValueError):validate_recipe(data)
        data=recipe();data['steps'][0]['kind']='evaluate'
        with self.assertRaises(ValueError):validate_recipe(data)
        data=recipe();data['identity']['text']=''
        with self.assertRaises(ValueError):validate_recipe(data)
        data=recipe();data['steps'][0]['locator']={'javascript':'alert(1)'}
        with self.assertRaises(ValueError):validate_recipe(data)

    def test_valid_recipe_strips_extra_data_and_never_keeps_input_values(self):
        data=recipe();data['steps'][0]['value']='DO-NOT-KEEP'
        self.assertNotIn('DO-NOT-KEEP',json.dumps(validate_recipe(data)))

    def test_origins_reject_credentials_schemes_and_match_ports(self):
        self.assertEqual(origin('https://studio.youtube.com/x'),origin('https://studio.youtube.com:443/y'))
        for url in ('file:///tmp/a','javascript:alert(1)','https://user:pass@example.com'):
            with self.assertRaises(SetupError):origin(url)

    def test_fresh_mode_is_api_and_workflows_persist_locally_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            v=Visible(tmp,threading.Event(),lambda _:None)
            self.assertEqual(v.config['mode'],'api')
            v.save({'flow':'youtube_prepare','recipe':recipe()})
            clone=Visible(tmp,threading.Event(),lambda _:None)
            self.assertIn('youtube_prepare',clone.snapshot()['configured'])
            self.assertNotIn('recipes',clone.snapshot())
            self.assertIn('recipes',clone.snapshot(True))

    def test_visible_cannot_arm_with_missing_workflows(self):
        with tempfile.TemporaryDirectory() as tmp:
            v=Visible(tmp,threading.Event(),lambda _:None)
            with self.assertRaisesRegex(ValueError,'review visible workflows'):v.ready({'schedule':[]})

    def test_url_targets_exact_event_and_rejects_injected_ids(self):
        cfg={'facebook_page_id':'113962385367196','camera_url':'http://192.168.29.10'}
        self.assertEqual(Visible.address('youtube_go',cfg,{'yt_id':'abcdefghijk'}),'https://studio.youtube.com/video/abcdefghijk/livestreaming')
        self.assertIn('video_id=12345678',Visible.address('facebook_end',cfg,{'fb_id':'12345678'}))
        self.assertEqual(Visible.address('camera_preset',cfg),'http://192.168.29.10/')
        with self.assertRaises(SetupError):Visible.address('youtube_go',cfg,{'yt_id':'../other'})
        with self.assertRaises(SetupError):Visible.address('camera_preset',{'camera_url':'http://user:secret@camera'})

    def test_failure_does_not_retry_or_fallback_and_progress_is_redacted(self):
        with tempfile.TemporaryDirectory() as tmp:
            v=Visible(tmp,threading.Event(),lambda _:None)
            v.save({'flow':'youtube_go','recipe':recipe()})
            v.browser=Mock();v.browser.run.side_effect=RuntimeError('secret-url-value')
            with self.assertRaises(SetupError):v.execute('youtube_go',{},values={'title':'Test'},record={'yt_id':'abcdefghijk'})
            self.assertEqual(v.browser.run.call_count,1)
            self.assertNotIn('secret-url-value',json.dumps(v.snapshot()))
            self.assertEqual(v.snapshot()['status']['state'],'needs_review')

    def test_cancelled_browser_never_launches(self):
        b=Browser('/unused',cancelled=lambda:True,ready=lambda:None)
        with patch('visible_browser.subprocess.Popen') as launch:
            with self.assertRaises(SetupError):b.ensure()
            launch.assert_not_called()

    def test_missing_run_variable_refuses_before_browser_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            v=Visible(tmp,threading.Event(),lambda _:None)
            v.save({'flow':'youtube_go','recipe':recipe()})
            v.browser=Mock()
            with self.assertRaisesRegex(SetupError,'unavailable'):v.execute('youtube_go',{},record={'yt_id':'abcdefghijk'})
            v.browser.run.assert_not_called()

    def test_locked_desktop_refuses_before_browser_launch(self):
        ready=Mock(side_effect=SetupError('locked'))
        b=Browser('/unused',ready=ready)
        with patch('visible_browser.subprocess.Popen') as launch:
            with self.assertRaisesRegex(SetupError,'locked'):b.ensure()
            launch.assert_not_called()

    def test_identity_mismatch_prevents_clicks(self):
        b=Browser('/unused',ready=lambda:None)
        page=Mock()
        page.evaluate.side_effect=['https://studio.youtube.com/', 'complete', 'https://studio.youtube.com/',
                                  {'ok':True,'text':'WRONG ACCOUNT','x':10,'y':10}]
        b.page=lambda _:page
        with self.assertRaisesRegex(SetupError,'identity'):b.run('youtube','https://studio.youtube.com/',recipe(),{},lambda *a:None)
        self.assertFalse(any(c.args[0].startswith('Input.') for c in page.call.call_args_list))
        page.close.assert_called_once()

    def test_api_write_gate_uses_only_ui_for_transitions(self):
        from connections import Services
        def init(instance,*args):
            instance.yt=Mock();instance.fb=Mock();instance.cfg={}
        visible=Mock()
        with patch.object(Services,'__init__',init):
            service=VisibleServices({},None,lambda _:None,visible)
        service.yt.go('abcdefghijk')
        visible.execute.assert_called_with('youtube_go',{},None,{'yt_id':'abcdefghijk'})
        with self.assertRaisesRegex(SetupError,'API write refused'):
            service.yt.api('POST','liveBroadcasts',{})
        with self.assertRaisesRegex(SetupError,'API write refused'):
            service.fb.api('POST','12345/live_videos',{})

    def test_recorder_does_not_read_value(self):
        self.assertNotIn('.value',RECORDER)
        self.assertIn('e.isTrusted',RECORDER)
        self.assertIn("n.type==='password'",RECORDER)

    def test_locator_is_serialized_as_data(self):
        script=target_script({'css':'#x";alert(1)//'},'return {ok:true};')
        self.assertIn('"#x\\";alert(1)//"',script)

    def test_empty_recording_is_error_and_clears_old_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            v=Visible(tmp,threading.Event(),lambda _:None)
            v.draft=recipe()['steps'];v.browser=Mock()
            v.browser.finish_recording.side_effect=SetupError('No actions were captured.')
            with self.assertRaisesRegex(SetupError,'No actions'):v.command({'action':'finish'}, {})
            self.assertIsNone(v.draft)
            self.assertEqual(v.status['state'],'needs_review')

    def test_capture_filters_health_messages_and_keeps_identity_assertion(self):
        b=Browser('/unused',ready=lambda:None);page=Mock()
        page.events=[{'name':'liveDeskCapture','payload':json.dumps(item)} for item in [
            {'kind':'ready','origin':'https://studio.youtube.com'},
            {'kind':'skipped','origin':'https://studio.youtube.com'},
            {'kind':'assert','origin':'https://studio.youtube.com','locator':{'css':'#channel'},'text':'Test Temple'}]]
        b.recording=(page,'script',origin('https://studio.youtube.com'))
        self.assertEqual(b.finish_recording(),[{'kind':'assert','locator':{'css':'#channel'},'text':'Test Temple'}])
        self.assertIsNone(b.recording);page.close.assert_called_once()

    def test_long_recording_is_not_silently_truncated(self):
        b=Browser('/unused',ready=lambda:None);page=Mock()
        page.events=[{'name':'liveDeskCapture','payload':json.dumps({'kind':'click','origin':'https://studio.youtube.com','locator':{'css':f'#step{i}'}})} for i in range(81)]
        b.recording=(page,'script',origin('https://studio.youtube.com'))
        with self.assertRaisesRegex(SetupError,'exceeded'):b.finish_recording()
        page.close.assert_called_once()


if __name__=='__main__':unittest.main()
