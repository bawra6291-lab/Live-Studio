"""Optional outbound HTTPS relay. Local scheduling never depends on relay uptime."""
import json,secrets,threading,time
from pathlib import Path
from urllib.parse import urlsplit
from core import atomic_json


def remote_origin(value):
    if not isinstance(value,str):raise ValueError('Enter an HTTPS remote service origin.')
    parsed=urlsplit(value)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/'):
        raise ValueError('Use an HTTPS origin, without credentials, paths, queries or fragments.')
    if len(value)>250:raise ValueError('Remote address is too long.')
    return value.rstrip('/')

class Agent:
    def __init__(self,controller):
        self.controller=controller;self.boot=secrets.token_hex(16);self.stop=threading.Event();self.thread=None
        self.path=controller.base/'remote-command-ledger.json'
        self.ledger_error=False
        try:
            self.seen=json.loads(self.path.read_text('utf-8')) if self.path.exists() else {}
            if not isinstance(self.seen,dict):raise ValueError('Invalid command ledger')
        except (OSError,ValueError):self.seen={};self.ledger_error=True
        self.status='Not connected';self.ack=None;self.last_seen=None
    def execute(self,command):
        ident=command.get('id');status='rejected';message='Command rejected'
        if self.ledger_error:return {'id':ident,'status':'rejected','message':'Remote command ledger needs local review'}
        if not isinstance(ident,str) or len(ident)!=32:return None
        if ident in self.seen:return {'id':ident,'status':'rejected','message':'Already received; not replayed'}
        # Persist receipt before execution. Crash/timeout never repeats a live operation.
        self.seen[ident]={'received':time.time(),'status':'received'}
        self.seen=dict(list(self.seen.items())[-500:]);atomic_json(self.path,self.seen)
        try:
            if command.get('boot')!=self.boot or not isinstance(command.get('expires'),(int,float)) or time.time()>command['expires']:raise ValueError('Expired command or different PC session.')
            action=command.get('action');c=self.controller
            if action=='pause':c.pause()
            elif action in ('arm','check'):c.run(action)
            elif action=='end':c.review_run({'action':'end','key':command.get('args',{}).get('key'),'confirmed':True})
            else:raise ValueError('Unsupported remote action.')
            status='accepted';message='Accepted by PC; inspect live status for the operation result'
        except ValueError as exc:message=str(exc)[:200]
        except Exception:message='PC could not accept command; inspect local activity'
        self.seen[ident]['status']=status;atomic_json(self.path,self.seen)
        c=self.controller;c.log('Remote '+str(command.get('action','unknown'))+' command '+status+'.')
        return {'id':ident,'status':status,'message':message}
    def start(self):
        if self.thread and self.thread.is_alive():return
        self.stop.clear();self.thread=threading.Thread(target=self.work,daemon=True);self.thread.start()
    def close(self):self.stop.set()
    def work(self):
        import requests
        while not self.stop.is_set():
            if self.ledger_error:self.status='Remote command ledger needs local review; local automation is available';return
            c=self.controller
            with c.lock:enabled=c.cfg.get('remote_enabled',False);address=c.cfg.get('remote_url','')
            if not enabled:self.status='Disabled';self.stop.wait(3);continue
            token=c.vault.get('remote_agent_token')
            try:
                if not token:raise ValueError('Save an agent enrollment token on this PC.')
                url=remote_origin(address)
                response=requests.post(url+'/api/agent/poll',headers={'Authorization':'Bearer '+token},json={'boot':self.boot,'snapshot':c.snapshot(False),'ack':self.ack},timeout=(5,10),allow_redirects=False)
                if response.status_code in (401,403):
                    self.status='Enrollment expired or revoked. Re-enroll locally.'
                    with c.lock:c.cfg['remote_enabled']=False;atomic_json(c.path,c.cfg)
                    continue
                response.raise_for_status();data=response.json();self.ack=None
                self.last_seen=time.time();self.status='Connected'
                if data.get('command'):
                    # An operator can disable remote access while a network request is in flight.
                    with c.lock:
                        if c.cfg.get('remote_enabled') and c.cfg.get('remote_url')==address and c.vault.get('remote_agent_token')==token and not self.stop.is_set():self.ack=self.execute(data['command'])
            except Exception:self.status='Remote connection unavailable; local automation continues'
            self.stop.wait(3)
