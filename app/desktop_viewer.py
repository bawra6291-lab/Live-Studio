"""Windows WebView2 window only. No controller, scheduler, vault or OBS imports."""
import json
import os
from pathlib import Path
import sys
import threading
from urllib.parse import urlsplit


def local_url(value):
    if not isinstance(value, str) or len(value) > 512:
        raise ValueError('Invalid dashboard address.')
    parsed = urlsplit(value)
    if (parsed.scheme != 'http' or parsed.netloc != '127.0.0.1:8865'
            or parsed.path != '/' or parsed.query or not parsed.fragment.startswith('pair=')):
        raise ValueError('Only the local Live Desk dashboard is allowed.')
    return value


def pipe_messages(stream, stopped):
    """Poll the inherited Windows pipe so closing a window can join the reader.

    A blocking readline inside pywebview.start's non-daemon worker would keep
    the process alive after the native window is destroyed.
    """
    import ctypes
    from ctypes import wintypes
    import msvcrt
    fd = stream.fileno()
    handle = msvcrt.get_osfhandle(fd)
    peek = ctypes.windll.kernel32.PeekNamedPipe
    peek.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                     ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    peek.restype = wintypes.BOOL
    pending = b''
    while not stopped.wait(0.05):
        available = wintypes.DWORD()
        if not peek(handle, None, 0, None, ctypes.byref(available), None):
            return  # Parent closed the pipe or exited.
        if not available.value:
            continue
        data = os.read(fd, min(4096, available.value))
        if not data:
            return
        pending += data
        if len(pending) > 8192:
            raise ValueError('Invalid local window command.')
        while b'\n' in pending:
            line, pending = pending.split(b'\n', 1)
            yield line.decode('utf-8')


def run(config, commands, report, webview, closed=None):
    url = local_url(config.get('url'))
    base = Path(config['base'])
    webview.settings['ALLOW_DOWNLOADS'] = True  # Diagnostics and settings exports.
    webview.settings['ALLOW_FILE_URLS'] = False
    webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER'] = True
    webview.settings['REMOTE_DEBUGGING_PORT'] = None
    window = webview.create_window('Live Desk', url, width=1200, height=780,
        min_size=(780, 560), background_color='#f5f4ef', text_select=True,
        zoomable=True, confirm_close=False)
    # No Python API bridge is exposed. All actions retain existing HTTP auth/CSRF.
    closed = closed or threading.Event()
    minimized = threading.Event()
    def on_loaded():
        report('ready')
    def on_closed():
        closed.set()
        report('closed')
    window.events.loaded += on_loaded
    window.events.closed += on_closed
    window.events.minimized += minimized.set
    window.events.restored += minimized.clear
    def on_before_show():
        from windows_identity import brand_window
        brand_window(window.native.Handle.ToInt64())
    window.events.before_show += on_before_show

    def listen():
        try:
            for line in commands:
                if closed.is_set():
                    return
                command = json.loads(line)
                if command.get('action') != 'show':
                    continue
                next_url = local_url(command.get('url'))
                window.show()
                if minimized.is_set():
                    window.restore()
                # Preserve the current view/unsaved form unless pairing expired.
                if window.evaluate_js('!!document.getElementById("login") && !document.getElementById("login").hidden'):
                    window.load_url(next_url)
        except (OSError, ValueError, KeyError):
            pass
        finally:
            # Parent exit closes only this viewer. Viewer exit never stops parent.
            if not closed.is_set():
                window.destroy()

    webview.start(listen, gui='edgechromium', debug=False, private_mode=True,
        storage_path=str(base / 'desktop-webview'),
        icon=str(Path(__file__).parent / 'web' / 'icon.ico'))


def main():
    if os.name != 'nt':
        return 1
    output, errors = sys.stdout, sys.stderr
    stopped = threading.Event()
    commands = pipe_messages(sys.stdin, stopped)
    report_lock = threading.Lock()
    def report(message):
        try:
            with report_lock:
                output.write(message + '\n')
                output.flush()
        except OSError:
            pass
    # Renderer diagnostics cannot leak the pairing URL to stdout or a log file.
    with open(os.devnull, 'w') as quiet:
        sys.stdout = sys.stderr = quiet
        try:
            config = json.loads(next(commands))
            if config.get('action') != 'start':
                return 1
            local_url(config.get('url'))
            from windows_identity import set_process_identity
            set_process_identity()
            from desktop_window import runtime_path, runtime_ready
            if runtime_ready(config['base']):
                import site
                sys.path.insert(0, str(runtime_path(config['base'])))
                site.addsitedir(str(runtime_path(config['base'])))
            import webview
            run(config, commands, report, webview, stopped)
            return 0
        except Exception:
            return 1
        finally:
            stopped.set()
            sys.stdout = output
            sys.stderr = errors


if __name__ == '__main__':
    raise SystemExit(main())
