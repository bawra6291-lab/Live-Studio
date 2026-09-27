"""Replay-buffer regression using real OBS response decoding, with no real outputs."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from connections import OBS, SetupError
from core import IST, Journal, Scheduler
from schedule_config import get_schedule


class Wire:
    def __init__(self, overrides=None):
        self.overrides=overrides or {};self.requests=[]

    def send(self, raw):
        self.request=json.loads(raw)['d'];self.requests.append(self.request['requestType'])

    def recv(self):
        kind=self.request['requestType']
        value=self.overrides.get(kind, 604 if kind=='GetReplayBufferStatus' else
                                 {'outputs':[]} if kind=='GetOutputList' else {'outputActive':False})
        if isinstance(value,int):
            status={'result':False,'code':value,'comment':'Replay buffer is not available.'};data={}
        else:status={'result':True,'code':100};data=value
        return json.dumps({'op':7,'d':{'requestId':self.request['requestId'],
                          'requestStatus':status,'responseData':data}})


def obs_with(overrides=None):
    obs=OBS({},None);obs.ws=Wire(overrides);return obs


class IdleTests(unittest.TestCase):
    def test_unavailable_replay_still_checks_all_other_outputs(self):
        obs=obs_with();obs.idle()
        self.assertEqual(obs.ws.requests,['GetStreamStatus','GetRecordStatus','GetReplayBufferStatus','GetOutputList'])

    def test_available_inactive_replay_is_idle(self):
        obs_with({'GetReplayBufferStatus':{'outputActive':False}}).idle()

    def test_active_stream_record_replay_or_plugin_blocks(self):
        for kind,value in [('GetStreamStatus',{'outputActive':True}),
                           ('GetRecordStatus',{'outputActive':True}),
                           ('GetReplayBufferStatus',{'outputActive':True}),
                           ('GetOutputList',{'outputs':[{'outputActive':True}]})]:
            with self.subTest(kind=kind),self.assertRaises(SetupError):obs_with({kind:value}).idle()

    def test_other_request_errors_remain_blocking(self):
        for kind,code in [('GetStreamStatus',604),('GetRecordStatus',604),
                          ('GetReplayBufferStatus',207),('GetReplayBufferStatus',500),
                          ('GetOutputList',604)]:
            with self.subTest(kind=kind,code=code),self.assertRaises(SetupError) as error:
                obs_with({kind:code}).idle()
            self.assertEqual(error.exception.request_type,kind)
            self.assertEqual(error.exception.code,code)

    def test_unknown_or_disconnected_replay_is_not_assumed_idle(self):
        obs=obs_with()
        with patch.object(obs,'call',side_effect=SetupError('Connection interrupted')):
            with self.assertRaises(SetupError):obs.idle()
        for value in ({},{'outputActive':'false'}):
            with self.subTest(value=value),self.assertRaises(SetupError):
                obs_with({'GetReplayBufferStatus':value}).idle()

    def test_scheduled_preparation_and_start_with_unavailable_replay(self):
        class Service:
            def __init__(self):self.obs=obs_with();self.prepared=0;self.started=0
            def prepare(self,slot,due,persist):
                self.obs.idle();self.prepared+=1
                return {'yt_id':'test-yt','fb_id':'test-fb'}
            def start(self,record):self.obs.idle();self.started+=1
        due=datetime(2026,9,27,7,30,tzinfo=IST)
        slot=get_schedule({})[1];slot['camera_actions']=[]
        service=Service()
        with tempfile.TemporaryDirectory() as folder:
            journal=Journal(Path(folder)/'journal.json')
            scheduler=Scheduler(service,journal,lambda _:None,slots=[slot])
            with patch('core.now_ist',return_value=due-timedelta(minutes=5)):
                scheduler.tick(due-timedelta(minutes=5))
            self.assertEqual(journal.get(slot,due.date())['phase'],'prepared')
            self.assertEqual((service.prepared,service.started),(1,0))
            with patch('core.now_ist',return_value=due):
                scheduler.tick(due);scheduler.tick(due)
            self.assertEqual((service.prepared,service.started),(1,1))
            self.assertEqual(journal.get(slot,due.date())['phase'],'live')


if __name__=='__main__':unittest.main()
