import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import obs_windows as ow

EXE = r'C:\Program Files\obs-studio\bin\64bit\obs64.exe'
SID = 'S-1-5-21-123'

def task():
    action = NS(Type=0, Path=EXE, Arguments='', WorkingDirectory=ow.ntpath.dirname(EXE))
    return NS(Enabled=True, State=3, Run=Mock(), Definition=NS(
        Principal=NS(UserId=SID, LogonType=3, RunLevel=1),
        Actions=NS(Count=1, Item=lambda _: action),
        Settings=NS(MultipleInstances=2, ExecutionTimeLimit='PT0S',
                    StopIfGoingOnBatteries=False, AllowDemandStart=True)))

class AdminTaskTests(unittest.TestCase):
    def test_account_name_resolves_to_same_sid(self):
        security=Mock(SidTypeUser=1)
        security.LookupAccountName.return_value=('native-sid', 'PC', 1)
        security.ConvertSidToStringSid.return_value=SID
        for name in ('kolka', r'PC\kolka'):
            with self.subTest(name=name), patch.dict(sys.modules, {'win32security':security}):
                t=task();t.Definition.Principal.UserId=name
                ow.validate_task(t, EXE, SID)
                security.LookupAccountName.assert_called_with(None, name)
    def test_account_name_for_other_user_is_rejected(self):
        security=Mock(SidTypeUser=1)
        security.LookupAccountName.return_value=('native-sid', 'PC', 1)
        security.ConvertSidToStringSid.return_value='S-1-5-21-456'
        with patch.dict(sys.modules, {'win32security':security}):
            t=task();t.Definition.Principal.UserId='other'
            with self.assertRaises(ow.OBSLaunchError):ow.validate_task(t, EXE, SID)
    def test_unresolved_account_and_group_are_rejected(self):
        security=Mock(SidTypeUser=1)
        with patch.dict(sys.modules, {'win32security':security}):
            t=task();t.Definition.Principal.UserId='unknown'
            security.LookupAccountName.side_effect=OSError('Unknown account')
            with self.assertRaises(ow.OBSLaunchError):ow.validate_task(t, EXE, SID)
            security.LookupAccountName.side_effect=None
            security.LookupAccountName.return_value=('native-sid', 'PC', 2)
            security.ConvertSidToStringSid.return_value=SID
            with self.assertRaises(ow.OBSLaunchError):ow.validate_task(t, EXE, SID)
    def test_direct_sid_match_needs_no_name_lookup(self):
        with patch.dict(sys.modules, {'win32security':Mock()}) as modules:
            self.assertTrue(ow._same_user(SID, SID))
            self.assertFalse(ow._same_user('S-1-5-21-456', SID))
            self.assertFalse(ow._same_user('', SID))
            modules['win32security'].LookupAccountName.assert_not_called()
    def test_accepts_same_user_interactive_obs_only(self):
        ow.validate_task(task(), EXE, SID)
    def test_rejects_other_account_background_and_limited_task(self):
        for field, value in [('UserId','SYSTEM'),('LogonType',5),('RunLevel',0)]:
            with self.subTest(field=field):
                t=task();setattr(t.Definition.Principal,field,value)
                with self.assertRaises(ow.OBSLaunchError):ow.validate_task(t,EXE,SID)
    def test_rejects_changed_path_or_streaming_arguments(self):
        for field,value in [('Path',r'C:\other.exe'),('Arguments','--startstreaming'),
                            ('WorkingDirectory',r'C:\other')]:
            with self.subTest(field=field):
                t=task();setattr(t.Definition.Actions.Item(1),field,value)
                with self.assertRaises(ow.OBSLaunchError):ow.validate_task(t,EXE,SID)
    def test_rejects_settings_that_can_stop_broadcast(self):
        for field,value in [('MultipleInstances',3),('ExecutionTimeLimit','PT72H'),
                            ('StopIfGoingOnBatteries',True)]:
            with self.subTest(field=field):
                t=task();setattr(t.Definition.Settings,field,value)
                with self.assertRaises(ow.OBSLaunchError):ow.validate_task(t,EXE,SID)
    def test_admin_task_run_has_no_parameters_and_no_popen(self):
        t=task()
        with patch.object(ow,'_task',return_value=t), patch.object(ow.subprocess,'Popen') as popen:
            self.assertIn('administrator',ow._launch(Path(EXE)))
        t.Run.assert_called_once_with('');popen.assert_not_called()
    def test_running_or_queued_task_is_not_started_again(self):
        for state in (2,4):
            t=task();t.State=state
            with patch.object(ow,'_task',return_value=t):ow._launch(Path(EXE))
            t.Run.assert_not_called()
    def test_plain_launch_has_no_tray_or_stream_flags(self):
        exe=Path('/example/obs64.exe')
        with patch.object(ow,'_task',return_value=None), patch.object(ow.subprocess,'Popen') as popen:
            ow._launch(exe)
        popen.assert_called_once_with([str(exe)],cwd=str(exe.parent))
    def test_elevation_required_points_to_setup_without_retry(self):
        error=OSError('elevation');error.winerror=740
        with patch.object(ow,'_task',return_value=None), patch.object(ow.subprocess,'Popen',side_effect=error) as popen:
            with self.assertRaisesRegex(ow.OBSLaunchError,'SETUP-OBS-ADMIN.cmd'):
                ow._launch(Path(EXE))
        self.assertEqual(popen.call_count,1)

class VisibleLaunchTests(unittest.TestCase):
    def test_existing_obs_only_shown_without_new_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe=Path(tmp)/'obs64.exe';exe.touch()
            com=Mock()
            with patch.dict(sys.modules,{'pythoncom':com}), patch.object(ow,'os',NS(name='nt')), \
                 patch.object(ow,'_processes',return_value={123}), patch.object(ow,'_show',return_value=True) as show, \
                 patch.object(ow,'_launch') as launch:
                message=ow.open_obs(exe)
            launch.assert_not_called();show.assert_called_once_with({123})
            self.assertIn('Existing OBS reused',message);com.CoUninitialize.assert_called_once()
    def test_missing_window_does_not_spawn_duplicate_or_kill(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe=Path(tmp)/'obs64.exe';exe.touch()
            with patch.dict(sys.modules,{'pythoncom':Mock()}), patch.object(ow,'os',NS(name='nt')), \
                 patch.object(ow,'_processes',return_value={123}), patch.object(ow,'_show',return_value=False), \
                 patch.object(ow,'_launch') as launch, patch.object(ow.time,'sleep'):
                with self.assertRaisesRegex(ow.OBSLaunchError,'No existing OBS was closed'):
                    ow.open_obs(exe)
            launch.assert_not_called()
    def test_new_obs_launched_once_then_shown(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe=Path(tmp)/'obs64.exe';exe.touch()
            with patch.dict(sys.modules,{'pythoncom':Mock()}), patch.object(ow,'os',NS(name='nt')), \
                 patch.object(ow,'_processes',side_effect=[set(),{123}]), patch.object(ow,'_show',return_value=True), \
                 patch.object(ow,'_launch',return_value='Opened.') as launch:
                ow.open_obs(exe)
            launch.assert_called_once_with(exe)

if __name__=='__main__':unittest.main()
