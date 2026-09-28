"""Disposable QA dashboard: no credentials, OBS, browser login or platform clients."""
import json
import sys
import tempfile
import threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from dashboard import Controller, DashboardServer, Handler

class MemoryVault:
    def __init__(self): self.values = {'facebook_page_token': 'qa-only-secret-not-a-real-token'}
    def get(self, key): return self.values.get(key, '')
    def set(self, key, value): self.values[key] = value

class ReadOnlyFakeServices:
    def __init__(self, cfg, vault, log): self.log = log
    def check(self):
        self.log('OBS connected. Program scene: QA only')
        self.log('YouTube channel verified: QA only')
        self.log('Facebook Page verified: QA only')
        self.log('Camera skipped; no external devices are contacted in QA.')
    def close(self): pass

class QAController(Controller):
    def run(self, mode):
        if mode != 'check': raise ValueError('QA server refuses automation and account login.')
        return super().run(mode)

class RemoteHandler(Handler):
    def local(self): return False

with tempfile.TemporaryDirectory(prefix='live-desk-qa-') as directory:
    controller = QAController(directory, ReadOnlyFakeServices, MemoryVault())
    local = DashboardServer(('127.0.0.1', 0), controller, 'qa-pairing')
    remote = DashboardServer(('127.0.0.1', 0), controller, 'qa-pairing')
    remote.RequestHandlerClass = RemoteHandler
    for server in (local, remote):
        threading.Thread(target=server.serve_forever, daemon=True).start()
    print(json.dumps({'desktop': f'http://127.0.0.1:{local.server_port}',
                      'mobile': f'http://127.0.0.1:{remote.server_port}'}), flush=True)
    try: sys.stdin.read()
    finally:
        controller.shutdown()
        if controller.worker: controller.worker.join(3)
        for server in (local, remote): server.shutdown(); server.server_close()
