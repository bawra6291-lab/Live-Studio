import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop_host import DesktopHost


class HandoffTests(unittest.TestCase):
    def test_async_completion_holds_slot_and_dispatches_once(self):
        host=DesktopHost();host.submit({'action':'obs'})
        calls=[]
        host.drain(lambda action,ip:calls.append(action))
        host.drain(lambda action,ip:calls.append(action))
        self.assertEqual(calls,['obs'])
        with self.assertRaises(ValueError):host.submit({'action':'obs-admin'})
        host.finish('OBS visible')
        host.submit({'action':'logs'})
        host.drain(lambda *args:'Logs opened')
        self.assertFalse(host.snapshot()['busy'])

    def test_failure_releases_slot_without_exposing_exception_details(self):
        host=DesktopHost();host.submit({'action':'logs'})
        def fail(*args):raise OSError('private file or credential')
        host.drain(fail)
        self.assertFalse(host.snapshot()['busy'])
        self.assertNotIn('private',host.snapshot()['message'])
        host.update(available=False)
        with self.assertRaises(ValueError):host.submit({'action':'obs'})


@unittest.skipUnless(os.name=='nt','Windows Tk integration')
class WindowsHostTests(unittest.TestCase):
    def test_hidden_host_and_dashboard_recovery_use_same_controller(self):
        import tkinter as tk
        import launcher
        from dashboard import Controller
        from test_dashboard import Vault, Service
        with tempfile.TemporaryDirectory() as folder:
            root=tk.Tk();root.withdraw()
            controller=Controller(folder,Service,Vault())
            with patch.object(launcher,'Controller',return_value=controller),\
                 patch.object(launcher,'BASE',Path(folder)),\
                 patch.object(launcher.webbrowser,'open',return_value=True) as browser:
                host=launcher.Launcher(root)
                try:
                    root.update()
                    self.assertEqual(root.state(),'withdrawn')
                    self.assertTrue(controller.snapshot(True)['desktop_host']['available'])
                    host.open_dashboard();self.assertIn('#pair=',browser.call_args.args[0])
                    # Real Tk queue; fake OBS action so no device/platform is contacted.
                    with patch.object(host,'open_obs',side_effect=lambda:host.obs_finished('QA OBS shown')) as obs:
                        host.host.submit({'action':'obs'});host.drain_host()
                        obs.assert_called_once();self.assertFalse(host.host.snapshot()['busy'])
                    self.assertEqual(root.state(),'withdrawn')
                    host.host.submit({'action':'launcher'});host.drain_host();root.update()
                    self.assertEqual(root.state(),'normal')
                    self.assertIs(host.controller,controller)
                finally:host.close(confirmed=True)
