"""Windows runner smoke check. Does not start OBS, change tasks or access stored secrets."""
import json
import os
import sys
from pathlib import Path
assert os.name == 'nt', 'Run this smoke check on Windows.'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import keyring
import pythoncom
import win32api
import win32con
import win32security
import win32ts
import tkinter
import obs_windows

root = tkinter.Tk()
root.withdraw()
root.update_idletasks()
root.destroy()
pythoncom.CoInitialize()
try:
    sid = obs_windows._sid()
    assert sid.startswith('S-1-'), 'Cannot identify the current Windows user.'
    assert obs_windows._same_user(win32api.GetUserName(), sid), 'Task account name did not resolve to current SID.'
    session = win32ts.ProcessIdToSessionId(os.getpid())
    assert isinstance(session, int)
finally:
    pythoncom.CoUninitialize()
backend = type(keyring.get_keyring()).__module__
assert 'Windows' in backend, 'Windows Credential Manager backend unavailable.'
print(json.dumps({'tkinter': 'passed', 'windows_user_identity': 'passed',
                  'task_account_name_resolution': 'passed',
                  'session_lookup': 'passed', 'credential_backend': backend,
                  'note': 'No OBS, UAC, scheduled task, credentials or live-platform operations tested.'}))
