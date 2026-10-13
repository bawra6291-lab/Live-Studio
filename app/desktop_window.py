"""Optional desktop viewer. This module never owns or stops automation.

The renderer runs in a separate windowless Python process. A private inherited
pipe carries the local pairing URL (never a command-line argument or log).
"""
import importlib.util
import json
import os
from pathlib import Path
from queue import SimpleQueue
import struct
import subprocess
import sys
import threading
import time

WEBVIEW_VERSION = '6.2.1'


def runtime_path(base):
    tag = f'{sys.version_info.major}.{sys.version_info.minor}-{struct.calcsize("P") * 8}'
    return Path(base) / 'desktop-runtime' / (WEBVIEW_VERSION + '-' + tag)


def runtime_ready(base):
    folder = runtime_path(base)
    return (folder / 'ready.txt').is_file() and (folder / 'webview' / '__init__.py').is_file()


def available(base):
    return runtime_ready(base) or importlib.util.find_spec('webview') is not None


def python_executable(windowless=False):
    exe = Path(sys.executable)
    sibling = exe.with_name('pythonw.exe' if windowless else 'python.exe')
    return str(sibling if sibling.is_file() else exe)


class DesktopWindow:
    """Called only on the host UI thread; pipe readers queue status tokens."""
    def __init__(self, base, url, browser, log):
        self.base = Path(base)
        self.url = url  # Callable: pairing codes can rotate while host stays open.
        self.browser = browser
        self.log = log
        self.process = None
        self.events = SimpleQueue()
        self.ready = False
        self.closed = False
        self.started = 0
        self.stopping = False
        self.message = 'Desktop window is ready to open.'

    def _send(self, message):
        self.process.stdin.write(json.dumps(message) + '\n')
        self.process.stdin.flush()

    def _fallback(self):
        self.message = ('Desktop window unavailable. Browser dashboard opened; automation is unchanged. '
                        'Use PC controls > Set up desktop window, or install Microsoft Edge WebView2 Runtime if setup is already complete.')
        self.log(self.message)
        self.browser()

    def open(self):
        if self.stopping:
            return
        if self.process and self.process.poll() is None:
            try:
                self._send({'action': 'show', 'url': self.url()})
                return
            except (OSError, ValueError):
                self._dispose()
        elif self.process:
            self._dispose()
        if not available(self.base):
            self._fallback()
            return
        self.ready = self.closed = False
        self.events = SimpleQueue()
        self.started = time.monotonic()
        try:
            self.process = subprocess.Popen(
                # python.exe with CREATE_NO_WINDOW retains reliable stdio pipes
                # on Windows while never displaying a console.
                [python_executable(), '-E', '-s', str(Path(__file__).with_name('desktop_viewer.py'))],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding='utf-8', bufsize=1,
                cwd=str(Path(__file__).parent),
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self._send({'action': 'start', 'url': self.url(), 'base': str(self.base)})
            output, events = self.process.stdout, self.events
            def read_events():
                try:
                    for line in output:
                        if line.strip() in ('ready', 'closed'):
                            events.put(line.strip())
                except (OSError, ValueError):
                    pass
                finally:
                    output.close()
            threading.Thread(target=read_events, daemon=True).start()
            self.message = 'Opening Live Desk desktop window…'
        except (OSError, ValueError):
            self._dispose()
            self._fallback()

    def poll(self):
        if self.stopping or not self.process:
            return
        while not self.events.empty():
            event = self.events.get()
            if event == 'ready':
                self.ready = True
                self.message = 'Desktop window connected. Closing it keeps automation and phone control running.'
            elif event == 'closed':
                self.closed = True
        result = self.process.poll()
        if result is not None:
            # A successful fast close can race the pipe reader's final event.
            failed = result != 0
            self._dispose()
            if failed:
                self._fallback()
            else:
                self.message = 'Desktop window closed. Automation and phone control continue; open Live Desk to return.'
        elif not self.ready and not self.closed and time.monotonic() - self.started > 45:
            self._dispose()
            self._fallback()

    def _dispose(self):
        process, self.process = self.process, None
        if not process:
            return
        if process.poll() is None:
            # Only the dashboard viewer is terminated, never OBS or the host.
            process.terminate()
        for pipe in (process.stdin,):
            if pipe:
                try:
                    pipe.close()
                except OSError:
                    pass

    def close(self):
        self.stopping = True
        self._dispose()


def install_runtime(base):
    """Install into an isolated directory; never mutate host dependencies."""
    import shutil
    import tempfile
    target = runtime_path(base)
    if runtime_ready(base):
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.setup-', dir=target.parent))
    try:
        result = subprocess.run(
            [python_executable(), '-E', '-s', '-m', 'pip', '--isolated', 'install',
             '--disable-pip-version-check', '--no-input', '--index-url', 'https://pypi.org/simple',
             '--target', str(stage), '--ignore-installed', 'pywebview==' + WEBVIEW_VERSION],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=300, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode or not (stage / 'webview' / '__init__.py').is_file():
            raise RuntimeError('Desktop component download failed.')
        (stage / 'ready.txt').write_text(WEBVIEW_VERSION, encoding='ascii')
        if target.exists():
            shutil.rmtree(target)
        stage.rename(target)
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
