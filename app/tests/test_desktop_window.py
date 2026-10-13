"""Renderer lifecycle failures must never control the automation host."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop_window import DesktopWindow, install_runtime, runtime_path
from desktop_viewer import local_url, run

URL = 'http://127.0.0.1:8865/#pair=test-code'


class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.browser, self.log = Mock(), Mock()
        self.viewer = DesktopWindow('.', lambda: URL, self.browser, self.log)

    def process(self, code=None):
        process = Mock()
        process.poll.return_value = code
        process.stdin = io.StringIO()
        process.stdout = io.StringIO()
        return process

    def test_close_viewer_does_not_invoke_browser_or_restart_host(self):
        self.viewer.process = self.process(0)
        self.viewer.ready = True
        self.viewer.poll()
        self.assertIsNone(self.viewer.process)
        self.browser.assert_not_called()
        self.assertIn('Automation and phone control continue', self.viewer.message)

    def test_missing_renderer_and_failed_spawn_open_browser(self):
        with patch('desktop_window.available', return_value=False):
            self.viewer.open()
        self.browser.assert_called_once()
        self.browser.reset_mock()
        with patch('desktop_window.available', return_value=True), \
             patch('desktop_window.subprocess.Popen', side_effect=OSError):
            self.viewer.open()
        self.browser.assert_called_once()

    def test_reopen_uses_same_process_and_private_pipe(self):
        process = self.process()
        self.viewer.process = process
        with patch('desktop_window.subprocess.Popen') as spawn:
            self.viewer.open()
            self.viewer.open()
        spawn.assert_not_called()
        commands = [json.loads(x) for x in process.stdin.getvalue().splitlines()]
        self.assertEqual(commands, [{'action': 'show', 'url': URL}] * 2)
        self.browser.assert_not_called()

    def test_start_pairing_not_exposed_in_process_arguments(self):
        process = self.process()
        with patch('desktop_window.available', return_value=True), \
             patch('desktop_window.subprocess.Popen', return_value=process) as spawn:
            self.viewer.open()
        self.assertNotIn('test-code', repr(spawn.call_args))
        self.assertEqual(json.loads(process.stdin.getvalue())['url'], URL)
        self.assertIsNotNone(self.viewer.process)

    def test_renderer_hang_and_crash_fallback_only_once(self):
        self.viewer.process = self.process()
        self.viewer.started = 0
        with patch('desktop_window.time.monotonic', return_value=46):
            self.viewer.poll()
            self.viewer.poll()
        self.browser.assert_called_once()
        self.browser.reset_mock()
        self.viewer.process = self.process(1)
        self.viewer.ready = True
        self.viewer.poll()
        self.browser.assert_called_once()

    def test_parent_shutdown_disposes_viewer_without_fallback(self):
        process = self.process()
        self.viewer.process = process
        self.viewer.close()
        self.viewer.poll()
        self.viewer.open()
        process.terminate.assert_called_once()
        self.browser.assert_not_called()

    def test_close_before_ready_is_not_a_crash(self):
        self.viewer.process = self.process(0)
        self.viewer.poll()
        self.browser.assert_not_called()


class Installation(unittest.TestCase):
    def test_failed_install_does_not_touch_core_or_publish_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch('desktop_window.subprocess.run', return_value=Mock(returncode=1)) as pip:
                with self.assertRaises(RuntimeError):
                    install_runtime(folder)
            self.assertFalse(runtime_path(folder).exists())
            command = pip.call_args.args[0]
            self.assertIn('--target', command)
            self.assertIn('--isolated', command)
            self.assertEqual(list(runtime_path(folder).parent.iterdir()), [])

    def test_install_is_reused_and_staged_atomically(self):
        with tempfile.TemporaryDirectory() as folder:
            def download(command, **kwargs):
                stage = Path(command[command.index('--target')+1])
                (stage/'webview').mkdir()
                (stage/'webview'/'__init__.py').write_text('# fixture')
                return Mock(returncode=0)
            with patch('desktop_window.subprocess.run', side_effect=download) as pip:
                install_runtime(folder)
                install_runtime(folder)
            pip.assert_called_once()
            self.assertTrue((runtime_path(folder)/'ready.txt').exists())


class Event:
    def __init__(self):
        self.callbacks = []
    def __iadd__(self, callback):
        self.callbacks.append(callback)
        return self


class ViewerContract(unittest.TestCase):
    def test_only_fixed_local_dashboard_can_load(self):
        self.assertEqual(local_url(URL), URL)
        for address in ('https://example.com/', 'http://127.0.0.1:8866/#pair=x',
                        'file:///c:/settings.json', 'http://127.0.0.1:8865.evil/#pair=x',
                        'http://127.0.0.1:8865/api/state#pair=x', None):
            with self.subTest(address=address), self.assertRaises(ValueError):
                local_url(address)

    def test_force_modern_engine_and_no_python_bridge(self):
        webview = Mock(settings={})
        window = webview.create_window.return_value
        for event in ('loaded', 'closed', 'minimized', 'restored'):
            setattr(window.events, event, Event())
        run({'url': URL, 'base': '.'}, io.StringIO(), Mock(), webview)
        self.assertEqual(webview.start.call_args.kwargs['gui'], 'edgechromium')
        self.assertTrue(webview.start.call_args.kwargs['private_mode'])
        self.assertNotIn('js_api', webview.create_window.call_args.kwargs)
        self.assertFalse(webview.settings['ALLOW_FILE_URLS'])
        self.assertTrue(webview.settings['ALLOW_DOWNLOADS'])
        self.assertTrue(webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER'])
