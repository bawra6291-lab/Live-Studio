"""Disposable tenant/queue tests; no deployment, real tokens or external requests."""
import json,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'remote'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from store import Store
from remote_agent import Agent,remote_origin
from core import atomic_json

class Remote(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'relay.db')
        self.workspace=self.store.create_workspace('One');self.other=self.store.create_workspace('Two')
        self.owner=self.principal(self.workspace,'owner');self.operator=self.principal(self.workspace,'operator');self.viewer=self.principal(self.workspace,'viewer');self.foreign=self.principal(self.other,'owner')
        self.enrollment=self.store.grant(self.workspace,'agent');self.agent=self.store.authenticate(self.enrollment['token'],agent=True);self.boot='a'*32
        self.store.poll(self.agent,{'boot':self.boot,'snapshot':{'armed':False,'settings':{'secret':'excluded'}}})
    def tearDown(self):self.tmp.cleanup()
    def principal(self,workspace,role):
        grant=self.store.grant(workspace,role);token,csrf=self.store.login(grant['token']);return self.store.authenticate(token)
    def command(self,**changes):return {'device':self.agent['id'],'boot':self.boot,'action':'arm','args':{},'confirmed':True,'nonce':'a'*32,**changes}
    def test_tenant_isolation_and_snapshot_filtering(self):
        self.assertEqual(self.store.state(self.foreign)['devices'],[])
        with self.assertRaises(PermissionError):self.store.enqueue(self.foreign,self.command())
        self.assertNotIn('settings',self.store.state(self.owner)['devices'][0]['snapshot'])
        self.store.revoke(self.foreign,self.agent['id'],'device')
        self.store.authenticate(self.enrollment['token'],agent=True)
    def test_viewer_cannot_queue_or_revoke(self):
        with self.assertRaises(PermissionError):self.store.enqueue(self.viewer,self.command())
        with self.assertRaises(PermissionError):self.store.revoke(self.viewer,self.agent['id'],'device')
    def test_confirm_boot_and_offline_guard(self):
        for changes in [{'confirmed':False},{'boot':'b'*32},{'action':'shell'},{'nonce':'invalid'}]:
            with self.assertRaises(ValueError):self.store.enqueue(self.owner,self.command(**changes))
        with patch('store.time.time',return_value=time.time()+20):
            with self.assertRaises(ValueError):self.store.enqueue(self.owner,self.command())
    def test_idempotency_and_single_dispatch(self):
        ident=self.store.enqueue(self.owner,self.command());self.assertEqual(ident,self.store.enqueue(self.owner,self.command()))
        with self.assertRaises(ValueError):self.store.enqueue(self.owner,self.command(action='pause'))
        body={'boot':self.boot,'snapshot':{}}
        self.assertEqual(self.store.poll(self.agent,body)['id'],ident)
        self.assertIsNone(self.store.poll(self.agent,body))
        self.store.poll(self.agent,{**body,'ack':{'id':ident,'status':'accepted','message':'Accepted'}})
        self.assertEqual(self.store.state(self.owner)['commands'][0]['status'],'accepted')
    def test_expired_commands_and_restarts_never_replay(self):
        self.store.enqueue(self.owner,self.command())
        with patch('store.time.time',return_value=time.time()+46):self.assertIsNone(self.store.poll(self.agent,{'boot':self.boot,'snapshot':{}}))
        self.assertEqual(self.store.state(self.owner)['commands'][0]['status'],'expired')
        self.store.enqueue(self.owner,self.command(nonce='b'*32))
        self.assertIsNone(self.store.poll(self.agent,{'boot':'c'*32,'snapshot':{}}))
    def test_revoked_actor_cannot_dispatch_queued_command(self):
        self.store.enqueue(self.operator,self.command());self.store.revoke(self.owner,self.operator['id'],'principal')
        self.assertIsNone(self.store.poll(self.agent,{'boot':self.boot,'snapshot':{}}))
        self.store.revoke(self.owner,self.agent['id'],'device')
        with self.assertRaises(PermissionError):self.store.poll(self.agent,{'boot':self.boot,'snapshot':{}})
    def test_ack_cannot_change_other_device_command(self):
        ident=self.store.enqueue(self.owner,self.command());self.store.poll(self.agent,{'boot':self.boot,'snapshot':{}})
        another=self.store.grant(self.workspace,'agent');other=self.store.authenticate(another['token'],agent=True)
        self.store.poll(other,{'boot':self.boot,'snapshot':{},'ack':{'id':ident,'status':'accepted'}})
        self.assertEqual(self.store.state(self.owner)['commands'][0]['status'],'dispatched')
    def test_agent_persists_receipt_before_execution_and_rejects_duplicate(self):
        c=Mock();c.base=Path(self.tmp.name);agent=Agent(c)
        cmd={'id':'e'*32,'boot':agent.boot,'action':'pause','expires':time.time()+45}
        c.pause.side_effect=lambda:self.assertEqual(json.loads(agent.path.read_text())['e'*32]['status'],'received')
        self.assertEqual(agent.execute(cmd)['status'],'accepted');self.assertEqual(agent.execute(cmd)['status'],'rejected');c.pause.assert_called_once()
        restarted=Agent(c);cmd['boot']=restarted.boot;self.assertEqual(restarted.execute(cmd)['status'],'rejected')
    def test_agent_rejects_expired_or_wrong_boot_without_operations(self):
        c=Mock();c.base=Path(self.tmp.name);agent=Agent(c)
        for i,fields in enumerate([{'boot':agent.boot,'expires':time.time()-1},{'boot':'b'*32,'expires':time.time()+45}]):
            self.assertEqual(agent.execute({'id':str(i)*32,'action':'arm',**fields})['status'],'rejected')
        c.run.assert_not_called()
    def test_corrupt_remote_ledger_does_not_break_local_controller(self):
        c=Mock();c.base=Path(self.tmp.name);path=c.base/'remote-command-ledger.json';path.write_text('{broken')
        agent=Agent(c);result=agent.execute({'id':'f'*32,'boot':agent.boot,'expires':time.time()+45,'action':'pause'})
        self.assertEqual(result['status'],'rejected');c.pause.assert_not_called();self.assertEqual(path.read_text(),'{broken')
    def test_origin_validation(self):
        self.assertEqual(remote_origin('https://relay.example/'),'https://relay.example')
        for value in ['http://relay.example','https://user:pw@relay.example','https://relay.example/path','https://relay.example?token=secret']:
            with self.assertRaises(ValueError):remote_origin(value)

if __name__=='__main__':unittest.main()
