"""Fixed local IPC with the in-process OBS Qt layout helper; no stream commands."""
import json
import os
import threading
import time
import uuid
from pathlib import Path
from core import atomic_json

_LOCK = threading.RLock()

class LayoutError(RuntimeError):
    pass

def directory():
    return Path(os.environ['APPDATA'])/'obs-studio/plugin_config/live-desk-layout'

def request(action, token=''):
    if action not in ('status', 'capture', 'restore'):
        raise ValueError('Unknown OBS layout action.')
    with _LOCK:
        folder=directory();folder.mkdir(parents=True,exist_ok=True)
        rid=uuid.uuid4().hex
        atomic_json(folder/'request.json',{'id':rid,'action':action,'token':token,'at':time.time()})
        deadline=time.monotonic()+4
        try:
            while time.monotonic()<deadline:
                response=folder/'response.json'
                if response.is_file() and response.stat().st_size<=4096:
                    try:result=json.loads(response.read_text('utf-8'))
                    except (ValueError,OSError):result={}
                    if result.get('id')==rid:
                        if result.get('protocol')!=1 or result.get('ok') is not True:
                            raise LayoutError('OBS could not preserve the dock layout. No new live was started; inspect OBS before retrying.')
                        if action=='capture' and result.get('token')!=rid:
                            raise LayoutError('OBS layout capture was not confirmed. No new live was started.')
                        return result
                time.sleep(.1)
            raise LayoutError('OBS layout helper is not ready. On this PC use This PC → Set up OBS layout protection once, then reopen OBS when idle and Check connections.')
        finally:
            # Do not let a delayed helper execute an expired request.
            try:
                if json.loads((folder/'request.json').read_text('utf-8')).get('id')==rid:
                    (folder/'request.json').unlink()
            except (OSError,ValueError):pass

def status():return request('status')
def capture():return request('capture')['token']
def restore(token):return request('restore',token)
