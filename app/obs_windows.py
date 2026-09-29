"""Visible, same-session OBS launch. Elevated task launches OBS only, never Python."""
import ntpath
import os
import subprocess
import threading
import time
from pathlib import Path

_LOCK = threading.Lock()
TASK_PREFIX = 'ISKCON-OBS-Admin-'

class OBSLaunchError(RuntimeError):
    pass

def _same_user(account, sid):
    """Task Scheduler may return an account name even when registered with a SID."""
    if account == sid:
        return True
    if not account or str(account).upper().startswith('S-1-'):
        return False
    try:
        import win32security
        resolved, _, kind = win32security.LookupAccountName(None, str(account))
        return (kind == win32security.SidTypeUser
                and win32security.ConvertSidToStringSid(resolved) == sid)
    except Exception:
        # Unresolvable identities must never authorize an elevated launch.
        return False

def validate_task(task, exe, sid):
    """Reject background/different-user tasks or actions with streaming arguments."""
    d = task.Definition
    p = d.Principal
    if not _same_user(p.UserId, sid):
        raise OBSLaunchError('OBS administrator task user does not resolve to this Windows login. Run SETUP-OBS-ADMIN.cmd from this account.')
    if (p.LogonType != 3 or p.RunLevel != 1
            or d.Actions.Count != 1 or not task.Enabled):
        raise OBSLaunchError('OBS administrator task requires an enabled, interactive, highest-privilege task with one OBS action. Run SETUP-OBS-ADMIN.cmd again.')
    a = d.Actions.Item(1)
    norm = lambda s: ntpath.normcase(ntpath.normpath(str(s)))
    if (a.Type != 0 or norm(a.Path) != norm(exe) or (a.Arguments or '').strip()
            or norm(a.WorkingDirectory) != norm(ntpath.dirname(str(exe)))):
        raise OBSLaunchError('OBS administrator task path differs from Connections. Use the installed Program Files OBS and rerun SETUP-OBS-ADMIN.cmd.')
    # Never let Task Scheduler time out or replace an active broadcast.
    s = d.Settings
    if (s.MultipleInstances != 2 or s.ExecutionTimeLimit != 'PT0S'
            or s.StopIfGoingOnBatteries or not s.AllowDemandStart):
        raise OBSLaunchError('OBS administrator task settings changed. Run SETUP-OBS-ADMIN.cmd again.')

def _sid():
    import win32api, win32con, win32security
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        return win32security.ConvertSidToStringSid(win32security.GetTokenInformation(token, win32security.TokenUser)[0])
    finally:
        token.Close()

def _task(exe):
    import win32com.client
    sid = _sid()
    scheduler = win32com.client.Dispatch('Schedule.Service')
    scheduler.Connect()
    for task in scheduler.GetFolder('\\').GetTasks(0):
        if task.Name == TASK_PREFIX + sid:
            validate_task(task, exe, sid)
            return task
    return None

def _processes():
    import win32com.client, win32ts
    session = win32ts.ProcessIdToSessionId(os.getpid())
    wmi = win32com.client.GetObject('winmgmts:root/cimv2')
    return {int(p.ProcessId) for p in wmi.ExecQuery(
        "SELECT ProcessId, SessionId FROM Win32_Process WHERE Name='obs64.exe' OR Name='obs32.exe'")
        if int(p.SessionId) == session}

def _show(pids):
    import win32gui, win32process, win32con
    windows = []
    def collect(hwnd, _):
        if (win32process.GetWindowThreadProcessId(hwnd)[1] in pids
                and win32gui.GetWindowText(hwnd).startswith('OBS ')):
            windows.append(hwnd)
    win32gui.EnumWindows(collect, None)
    if not windows:
        return False
    for hwnd in windows:
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
            if not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
                win32gui.PostMessage(hwnd, win32con.WM_SYSCOMMAND, win32con.SC_RESTORE, 0)
        except Exception:
            pass  # Higher integrity or a busy OBS can refuse window operations.
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass  # Windows may keep focus on the operator's current window.
    return any(win32gui.IsWindowVisible(h) and not win32gui.IsIconic(h) for h in windows)

def _launch(exe):
    task = _task(exe)
    if task is not None:
        if task.State in (2, 4):  # Already queued/running; do not submit another launch.
            return 'Administrator OBS launch already requested.'
        task.Run('')
        return 'OBS launched as administrator for this Windows login.'
    try:
        subprocess.Popen([str(exe)], cwd=str(exe.parent))
    except OSError as exc:
        if getattr(exc, 'winerror', None) == 740:
            raise OBSLaunchError('OBS requires administrator access. On this PC run SETUP-OBS-ADMIN.cmd once, approve Windows UAC, then retry.') from None
        raise
    return 'OBS opened. For administrator mode run SETUP-OBS-ADMIN.cmd once.'

def open_obs(exe, require_window=True):
    """Does not start/stop outputs, kill processes or change OBS configuration."""
    if os.name != 'nt':
        raise OBSLaunchError('Open OBS on the Windows livestream PC.')
    import pythoncom
    pythoncom.CoInitialize()
    try:
        with _LOCK:
            exe = Path(exe)
            if not exe.is_file():
                raise OBSLaunchError('OBS executable path is incorrect. Check Connections.')
            pids = _processes()
            message = ('Existing OBS reused; its administrator mode is unchanged.'
                       if pids else _launch(exe))
            for _ in range(25):
                if _show(_processes()):
                    return message + ' Window restored; use the OBS taskbar icon if it is behind another window.'
                time.sleep(1)
            if not require_window:
                # A visible-window failure must not stop a healthy WebSocket connection.
                return message + ' Check the OBS taskbar/tray icon to show its window.'
            raise OBSLaunchError('OBS window is not available yet. Check the OBS taskbar/tray icon or startup dialog. No existing OBS was closed or restarted.')
    except OBSLaunchError:
        raise
    except Exception as exc:
        raise OBSLaunchError(f'Could not open/show OBS ({type(exc).__name__}). Check Task Scheduler and the OBS taskbar/tray icon on this PC.') from None
    finally:
        pythoncom.CoUninitialize()
