"""Bounded handoff from authenticated HTTP handlers to the Windows UI thread."""
from collections import deque
from threading import RLock


class DesktopHost:
    ACTIONS = {'obs', 'obs-admin', 'obs-layout', 'startup', 'startup-remove', 'logs',
               'mobile-on', 'mobile-off', 'launcher', 'updates', 'quit'}

    def __init__(self):
        self.lock = RLock()
        self.queue = deque()
        self.info = {'available': True, 'busy': False, 'startup': False,
                     'addresses': [], 'message': 'Live Desk is running in the background.'}

    def snapshot(self):
        with self.lock:
            return {**self.info, 'addresses': list(self.info['addresses'])}

    def update(self, **values):
        with self.lock:
            self.info.update(values)

    def submit(self, data):
        action = data.get('action')
        if not isinstance(action, str) or action not in self.ACTIONS:
            raise ValueError('Choose a supported PC control.')
        if action in ('quit', 'mobile-off') and data.get('confirmed') is not True:
            raise ValueError('Confirm this PC action first.')
        ip = data.get('ip', '')
        if not isinstance(ip, str) or len(ip) > 45:
            raise ValueError('Choose a local network address.')
        with self.lock:
            if not self.info['available']:
                raise ValueError('Live Desk is closing.')
            if self.info['busy']:
                raise ValueError('Wait for the current PC action to finish.')
            self.info.update(busy=True, message='PC action queued: '+action)
            self.queue.append((action, ip))

    def drain(self, callback):
        with self.lock:
            if not self.queue:
                return
            action, ip = self.queue.popleft()
        try:
            result = callback(action, ip)
        except Exception as exc:
            # Do not return paths, credentials or arbitrary exception text to the UI.
            result = type(exc).__name__+': PC action failed. Check Activity and Windows permissions.'
        if result is not None:
            self.finish(result)
        return result

    def finish(self, message):
        self.update(busy=False, message=str(message))
