"""Emulator-only server: real dashboard/auth; fake arm with no engine/platforms."""
import json
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'app'))
from dashboard import Controller, DashboardServer, Handler

class MemoryVault:
    def get(self, key): return ''
    def set(self, key, value): pass

class PhoneController(Controller):
    events = []
    def run(self, mode):
        if mode != 'arm': raise ValueError('Fixture refuses all other operations.')
        with self.lock:
            self.armed = True
            self.events.append('arm')
            self.message = 'Emulator fixture enabled. No platform or engine is started.'
    def pause(self):
        self.events.append('pause')
        super().pause()

class RemoteHandler(Handler):
    def local(self): return False
    def do_GET(self):
        if self.path == '/qa/state':
            return self.reply(200, {'armed': self.server.controller.armed,
                                   'events': self.server.controller.events,
                                   'sessions': len(self.server.sessions)})
        if self.path == '/api/state' and Path('mobile/android/build/offline.flag').exists():
            return self.reply(503, {'error': 'Emulator-only offline simulation.'})
        return super().do_GET()

with tempfile.TemporaryDirectory(prefix='live-desk-android-') as directory:
    controller = PhoneController(directory, lambda *args: None, MemoryVault())
    server = DashboardServer(('0.0.0.0', 8866), controller, 'qa-pairing')
    server.RequestHandlerClass = RemoteHandler
    server.allowed_hosts = {'10.0.2.2', '127.0.0.1'}
    print('Android fixture ready. No real services.', flush=True)
    try: server.serve_forever()
    finally: controller.shutdown(); server.server_close()
