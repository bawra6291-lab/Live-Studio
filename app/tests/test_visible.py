import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from visible import Visible, VisibleServices, validate_recipe
from visible_browser import Browser, BrowserCDP, origin, RECORDER, target_script
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

    def test_restarted_controller_attaches_without_launch_or_marker_deletion(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker=Path(tmp)/'visible-browser-profile'/'DevToolsActivePort'
            marker.parent.mkdir();marker.write_text('45678\n/devtools/browser/session-one\n')
            b=Browser(tmp,ready=lambda:None)
            b.endpoint=Mock(return_value={'webSocketDebuggerUrl':'ws://127.0.0.1:45678/devtools/browser/session-one'})
            with patch('visible_browser.subprocess.Popen') as launch:
                b.ensure();b.ensure()
            launch.assert_not_called()
            self.assertEqual(b.port,45678)
            self.assertIn('session-one',marker.read_text())

    def test_attach_rejects_wrong_browser_identity_or_nonlocal_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker=Path(tmp)/'DevToolsActivePort'
            marker.write_text('45678\n/devtools/browser/expected\n')
            b=Browser(tmp,ready=lambda:None);b.port=12345
            for address in ('ws://127.0.0.1:45678/devtools/browser/other',
                            'ws://example.com:45678/devtools/browser/expected',
                            'ws://127.0.0.1:45679/devtools/browser/expected'):
                b.endpoint=Mock(return_value={'webSocketDebuggerUrl':address})
                self.assertFalse(b.attach(marker));self.assertEqual(b.port,12345)

    def test_unresponsive_running_browser_does_not_launch_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            b=Browser(tmp,ready=lambda:None);b.process=Mock();b.process.poll.return_value=None
            with patch('visible_browser.subprocess.Popen') as launch:
                with self.assertRaisesRegex(SetupError,'No second browser'):b.ensure()
            launch.assert_not_called()

    def test_site_tab_is_rediscovered_after_app_restart_without_new_tab(self):
        b=Browser('/unused',ready=lambda:None);b.ensure=lambda:None
        b.sites['facebook']=origin('https://www.facebook.com/live/producer/')
        targets=[{'type':'page','id':'other','url':'https://studio.youtube.com/','webSocketDebuggerUrl':'ws://other'},
                 {'type':'service_worker','id':'worker','url':'https://www.facebook.com/','webSocketDebuggerUrl':'ws://worker'},
                 {'type':'page','id':'logged-in','url':'https://www.facebook.com/live/producer/v2/','webSocketDebuggerUrl':'ws://local'}]
        b.endpoint=Mock(return_value=targets)
        with patch('visible_browser.CDP') as cdp:b.page('facebook')
        cdp.assert_called_once_with('ws://local')
        b.endpoint.assert_called_once_with('/json/list')
        self.assertEqual(b.tabs['facebook'],'logged-in')

    def test_browser_selection_prefers_per_user_chrome_over_system_edge(self):
        with tempfile.TemporaryDirectory() as tmp:
            system=Path(tmp)/'system';local=Path(tmp)/'local'
            for exe in (system/'Microsoft/Edge/Application/msedge.exe',local/'Google/Chrome/Application/chrome.exe'):
                exe.parent.mkdir(parents=True);exe.touch()
            b=Browser(Path(tmp)/'data',ready=lambda:None)
            b.attach=Mock(side_effect=[False,True])
            with patch.dict('os.environ',{'PROGRAMFILES':str(system),'LOCALAPPDATA':str(local)},clear=True),patch('visible_browser.subprocess.Popen') as launch:
                b.ensure()
            self.assertEqual(launch.call_args.args[0][0],str(local/'Google/Chrome/Application/chrome.exe'))

    def test_normal_chrome_selection_persists_but_connection_is_local_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            v=Visible(tmp,threading.Event(),lambda _:None)
            v.save({'browser_source':'running_chrome'})
            clone=Visible(tmp,threading.Event(),lambda _:None)
            self.assertEqual(clone.browser.source,'running_chrome')
            self.assertFalse(clone.snapshot(True)['chrome_connected'])
            self.assertNotIn('browser_source',clone.snapshot())
            with self.assertRaises(ValueError):v.save({'browser_source':'http://attacker'})

    def test_normal_chrome_never_launches_when_not_connected_or_disconnected(self):
        b=Browser('/unused',ready=lambda:None);b.select('running_chrome')
        with patch('visible_browser.subprocess.Popen') as launch:
            with self.assertRaisesRegex(SetupError,'Connect my Chrome'):b.ensure()
            b.chrome=Mock();b.chrome.closed=True
            with self.assertRaisesRegex(SetupError,'Connect my Chrome'):b.page('facebook')
        launch.assert_not_called()

    def test_normal_chrome_connect_uses_only_valid_marker_and_one_browser_socket(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker=Path(tmp)/'Google/Chrome/User Data/DevToolsActivePort'
            marker.parent.mkdir(parents=True);marker.write_text('9222\n/devtools/browser/user-browser\n')
            b=Browser('/unused',ready=lambda:None);b.select('running_chrome')
            with patch.dict('os.environ',{'LOCALAPPDATA':tmp}),patch('visible_browser.BrowserCDP') as connect,patch('visible_browser.subprocess.Popen') as launch:
                root=connect.return_value;root.closed=False;root.call.return_value={'product':'Chrome/154.0'}
                b.connect_chrome();b.connect_chrome();b.ensure()
            connect.assert_called_once_with('ws://127.0.0.1:9222/devtools/browser/user-browser')
            launch.assert_not_called();self.assertIs(b.chrome,root)

    def test_normal_chrome_bad_marker_or_denied_permission_never_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker=Path(tmp)/'Google/Chrome/User Data/DevToolsActivePort'
            marker.parent.mkdir(parents=True)
            b=Browser('/unused',ready=lambda:None);b.select('running_chrome')
            with patch.dict('os.environ',{'LOCALAPPDATA':tmp}),patch('visible_browser.BrowserCDP') as connect,patch('visible_browser.subprocess.Popen') as launch:
                for value in ('9222\nws://attacker/\n','9222\n/devtools/browser/user?secret=value\n','0\n/devtools/browser/abc\n','9222\n/devtools/browser/abc\nextra'):
                    marker.write_text(value)
                    with self.assertRaisesRegex(SetupError,'Cannot find'):b.connect_chrome()
                connect.assert_not_called()
                marker.write_text('9222\n/devtools/browser/abc\n')
                connect.side_effect=RuntimeError('private-browser-value')
                with self.assertRaisesRegex(SetupError,'not allowed') as exc:b.connect_chrome()
                self.assertNotIn('private-browser-value',str(exc.exception))
            launch.assert_not_called();self.assertIsNone(b.chrome)

    def test_normal_chrome_uses_managed_tabs_and_browser_transport_without_http(self):
        b=Browser('/unused',ready=lambda:None);b.select('running_chrome')
        root=Mock();root.closed=False;b.chrome=root
        existing=[{'type':'page','targetId':'personal','url':'https://www.facebook.com/'}]
        root.call.side_effect=[{'product':'Chrome/154'},{'targetInfos':existing},{'targetId':'managed'},{},
                               {'product':'Chrome/154'},{'targetInfos':existing+[{'type':'page','targetId':'managed'}]},{}]
        b.endpoint=Mock(side_effect=AssertionError('No HTTP discovery'))
        b.page('facebook');b.page('facebook')
        self.assertEqual(b.tabs['facebook'],'managed')
        creates=[c for c in root.call.call_args_list if c.args[0]=='Target.createTarget']
        self.assertEqual(len(creates),1);self.assertFalse(creates[0].kwargs['newWindow'])
        root.page.assert_called_with('managed');b.endpoint.assert_not_called()
        b.disconnect();root.close.assert_called_once()
        self.assertFalse(any(c.args[0] in ('Target.closeTarget','Browser.close') for c in root.call.call_args_list))

    def test_browser_socket_filters_recorder_events_by_page_session(self):
        import queue
        import websocket
        messages=queue.Queue()
        ws=Mock()
        def receive():
            try:return messages.get(timeout=.05)
            except queue.Empty:raise websocket.WebSocketTimeoutException()
        ws.recv.side_effect=receive
        def send(raw):
            packet=json.loads(raw)
            result={'sessionId':'s1'} if packet['method']=='Target.attachToTarget' else {}
            if packet['method']=='Runtime.evaluate':
                for session in ('unrelated','s1'):
                    messages.put(json.dumps({'sessionId':session,'method':'Runtime.bindingCalled',
                        'params':{'name':'liveDeskCapture','payload':'{"kind":"click"}'}}))
            messages.put(json.dumps({'id':packet['id'],'result':result}))
        ws.send.side_effect=send
        with patch('websocket.create_connection',return_value=ws) as connect:
            root=BrowserCDP('ws://127.0.0.1:9222/devtools/browser/fixture')
            try:
                page=root.page('target-one');page.call('Runtime.evaluate',expression='1')
                self.assertEqual(len(page.events),1)
                sent=json.loads(ws.send.call_args.args[0]);self.assertEqual(sent['sessionId'],'s1')
                page.close();self.assertFalse(root.closed)
                self.assertNotIn('s1',root.sessions)
                self.assertEqual(connect.call_count,1)
            finally:root.close()

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

    def test_opaque_frame_health_events_do_not_discard_valid_recording(self):
        b=Browser('/unused',ready=lambda:None);page=Mock()
        items=[
            {'kind':'ready','origin':'null'},
            {'kind':'skipped','origin':'null'},
            {'kind':'ready'},
            {'kind':'ready','origin':'about:blank'},
            {'kind':'click','origin':'https://other.example','locator':{'css':'#foreign'}},
            {'kind':'assert','origin':'https://www.facebook.com','locator':{'css':'#account'},'text':'Test Temple'},
            {'kind':'fill','origin':'https://www.facebook.com','locator':{'css':'#title'}},
            {'kind':'click','origin':'https://www.facebook.com','locator':{'css':'#prepare'}}]
        page.events=[{'name':'liveDeskCapture','payload':json.dumps(item)} for item in items]
        b.recording=(page,'script',origin('https://www.facebook.com/live/producer/'))
        self.assertEqual(b.finish_recording(),[
            {'kind':'assert','locator':{'css':'#account'},'text':'Test Temple'},
            {'kind':'fill','locator':{'css':'#title'},'variable':''},
            {'kind':'click','locator':{'css':'#prepare'}}])
        self.assertIsNone(b.recording);page.close.assert_called_once()

    def test_opaque_frame_health_only_is_still_empty_recording(self):
        b=Browser('/unused',ready=lambda:None);page=Mock()
        page.events=[{'name':'liveDeskCapture','payload':json.dumps({'kind':'ready','origin':'null'})}]
        b.recording=(page,'script',origin('https://www.facebook.com'))
        with self.assertRaisesRegex(SetupError,'No actions were captured'):
            b.finish_recording()
        self.assertIsNone(b.recording);page.close.assert_called_once()

    def test_opaque_origin_action_still_refuses_recording(self):
        b=Browser('/unused',ready=lambda:None);page=Mock()
        page.events=[{'name':'liveDeskCapture','payload':json.dumps(item)} for item in [
            {'kind':'click','origin':'https://www.facebook.com','locator':{'css':'#valid'}},
            {'kind':'click','origin':'null','locator':{'css':'#unsupported'}}]]
        b.recording=(page,'script',origin('https://www.facebook.com'))
        with self.assertRaisesRegex(SetupError,'HTTP'):
            b.finish_recording()
        self.assertIsNone(b.recording);page.close.assert_called_once()


if __name__=='__main__':unittest.main()
