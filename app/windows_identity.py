"""Windows shell branding shared by the host and its desktop viewer.

Pinned windows relaunch desktop_start.py, never the private stdin-only viewer.
No pairing URL, credential or runtime-specific version enters shell properties.
"""
import ctypes
import os
from pathlib import Path
import subprocess
import sys

APP_ID = 'ISKCON.LiveDesk.Desktop'
DISPLAY_NAME = 'Live Desk - ISKCON Kolkata'
ICON = Path(__file__).resolve().parent / 'web' / 'icon.ico'


def set_process_identity():
    if os.name != 'nt':
        return False
    setter = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
    setter.argtypes = [ctypes.c_wchar_p]
    setter.restype = ctypes.c_long
    return setter(APP_ID) == 0


def relaunch_command():
    executable = Path(sys.executable)
    gui = executable.with_name('pythonw.exe')
    return subprocess.list2cmdline([
        str(gui if gui.exists() else executable), '-E', '-s',
        str(Path(__file__).resolve().with_name('desktop_start.py'))])


def brand_window(hwnd):
    """Apply pinning identity before showing a native window (Windows only)."""
    import pythoncom
    from win32com.propsys import propsys
    pythoncom.CoInitialize()
    try:
        store = propsys.SHGetPropertyStoreForWindow(int(hwnd))
        # ID goes last: changing it tells Explorer to refresh these properties.
        properties = (
            ('System.AppUserModel.RelaunchCommand', relaunch_command()),
            ('System.AppUserModel.RelaunchDisplayNameResource', DISPLAY_NAME),
            ('System.AppUserModel.RelaunchIconResource', str(ICON) + ',0'),
            ('System.AppUserModel.ID', APP_ID),
        )
        for name, value in properties:
            store.SetValue(propsys.PSGetPropertyKeyFromName(name),
                           propsys.PROPVARIANTType(value))
        store.Commit()
    finally:
        pythoncom.CoUninitialize()
