"""Real Windows WebView2 lifecycle, against fake services only.

Never contacts OBS, YouTube, Facebook, a camera, or Windows Credential Manager.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time

assert os.name == 'nt', 'Run on Windows with WebView2 Runtime installed.'
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'app'), str(ROOT/'app'/'tests')]
from core import atomic_json
from dashboard import Controller, DashboardServer
from desktop_window import DesktopWindow
from test_dashboard import Service, Vault
import win32con
import win32gui
import win32process


def wait_for(test, viewer, timeout=50):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        viewer.poll()
        if test():
            return
        time.sleep(0.1)
    raise AssertionError('Desktop lifecycle check timed out: ' + viewer.message)


def hwnd_for(pid):
    matches = []
    def visit(hwnd, _):
        if win32process.GetWindowThreadProcessId(hwnd)[1] == pid and win32gui.GetWindowText(hwnd) == 'Live Desk':
            matches.append(hwnd)
    win32gui.EnumWindows(visit, None)
    return matches[0] if matches else None


with tempfile.TemporaryDirectory() as folder:
    base = Path(folder)
    atomic_json(base/'settings.json', {})
    controller = Controller(base, Service, Vault())
    server = DashboardServer(('127.0.0.1', 8865), controller, 'fixture-pair-code')
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    fallbacks, logs = [], []
    viewer = DesktopWindow(base, lambda:'http://127.0.0.1:8865/#pair='+server.pair_code,
                           lambda:fallbacks.append(True), logs.append)
    def authenticated():
        with server.auth_lock:
            return bool(server.sessions)
    try:
        viewer.open()
        wait_for(lambda: viewer.ready and authenticated(), viewer)
        assert not fallbacks, logs
        first_pid = viewer.process.pid
        hwnd = hwnd_for(first_pid)
        assert hwnd, 'No named native Live Desk window found.'
        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
        wait_for(lambda: bool(win32gui.IsIconic(hwnd)), viewer)
        # Allow the renderer to observe the minimize event.
        time.sleep(0.3)
        viewer.open()
        wait_for(lambda: not win32gui.IsIconic(hwnd), viewer)
        assert viewer.process.pid == first_pid, 'Reopen created a duplicate viewer.'
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        wait_for(lambda: viewer.process is None, viewer)
        assert not controller.stop.is_set(), 'Closing viewer stopped host.'
        assert server_thread.is_alive(), 'Closing viewer stopped dashboard/mobile host.'
        assert not fallbacks, 'Normal close incorrectly reopened a browser.'
        # Reopen with a newly rotated pairing code and a new private session.
        with server.auth_lock:
            server.pair_code = 'rotated-fixture-code'
            server.sessions.clear()
        viewer.open()
        wait_for(lambda: viewer.ready and authenticated(), viewer)
        assert not fallbacks, logs
        assert viewer.process.pid != first_pid
        process = viewer.process
        viewer.close()
        process.wait(timeout=10)
        assert not controller.stop.is_set()
        print(json.dumps({'native_window':'passed','pairing':'passed',
              'reopen_same_process':'passed','minimize_restore':'passed',
              'close_keeps_host_running':'passed','rotated_pairing':'passed',
              'shutdown_closes_viewer':'passed','real_live_services_contacted':False}))
    finally:
        if viewer.process:
            process = viewer.process
            viewer.close()
            process.wait(timeout=10)
        controller.shutdown()
        server.shutdown()
        server.server_close()
        server_thread.join(5)
