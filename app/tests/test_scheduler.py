import unittest,tempfile
from pathlib import Path
from datetime import datetime,timedelta,date
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import SLOTS,IST,Scheduler,Journal,title_for,date_prefix

class Fake:
    def __init__(self):self.prepared=0;self.started=0;self.patrols=0;self.active=True;self.fail=None
    def prepare(self,slot,due,persist):
        self.prepared+=1;persist(yt_id='yt')
        if self.fail=='prepare':raise RuntimeError('Ambiguous create timeout')
        return {'yt_id':'yt','fb_id':'fb','yt_stream_id':'stream','title':'title'}
    def start(self,record):
        self.started+=1
        if self.fail=='start':raise RuntimeError('Facebook failed after YouTube started')
    def both_live(self,record):return self.active
    def camera_start(self):self.patrols+=1

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'state.json'
        self.journal=Journal(self.path);self.service=Fake();self.logs=[]
        self.scheduler=Scheduler(self.service,self.journal,self.logs.append)
        self.due=datetime(2026,9,22,4,30,tzinfo=IST)
    def tearDown(self):self.tmp.cleanup()
    def tick(self,dt):
        with patch('core.now_ist',return_value=dt):self.scheduler.tick(dt)
    def test_no_8am_and_four_only(self):
        self.assertEqual([x['at'] for x in SLOTS],['04:30','07:30','12:00','18:00'])
    def test_prepare_five_minutes_before_without_start(self):
        self.tick(self.due-timedelta(minutes=5,seconds=1));self.assertEqual(self.service.prepared,0)
        self.tick(self.due-timedelta(minutes=5));self.assertEqual(self.service.prepared,1);self.assertEqual(self.service.started,0)
    def test_one_start_and_one_patrol(self):
        self.tick(self.due);self.tick(self.due+timedelta(seconds=1))
        self.assertEqual(self.service.started,1)
        self.tick(self.due+timedelta(seconds=119));self.assertEqual(self.service.patrols,0)
        self.tick(self.due+timedelta(seconds=120));self.tick(self.due+timedelta(seconds=125))
        self.assertEqual(self.service.patrols,1)
    def test_failed_write_not_retried(self):
        self.service.fail='prepare';self.tick(self.due);self.tick(self.due+timedelta(seconds=1))
        self.assertEqual(self.service.prepared,1);self.assertEqual(self.service.started,0)
        self.assertEqual(Journal(self.path).get(SLOTS[0],self.due.date())['yt_id'],'yt')
    def test_partial_live_failure_no_patrol_or_retry(self):
        self.service.fail='start';self.tick(self.due);self.tick(self.due+timedelta(seconds=120))
        self.assertEqual(self.service.started,1);self.assertEqual(self.service.patrols,0)
    def test_manual_end_cancels_camera(self):
        self.tick(self.due);self.service.active=False;self.tick(self.due+timedelta(seconds=120))
        self.assertEqual(self.service.patrols,0)
    def test_restart_does_not_duplicate_broadcast(self):
        self.tick(self.due)
        self.scheduler=Scheduler(self.service,Journal(self.path),self.logs.append)
        self.tick(self.due+timedelta(seconds=120))
        self.assertEqual(self.service.started,1);self.assertEqual(self.service.patrols,1)
    def test_interrupted_start_needs_review(self):
        self.journal.put(SLOTS[0],self.due.date(),phase='starting')
        self.tick(self.due);self.assertEqual(self.service.started,0)
        self.assertEqual(self.journal.get(SLOTS[0],self.due.date())['phase'],'needs_review')
    def test_no_late_catchup(self):
        self.tick(self.due+timedelta(seconds=121));self.assertEqual(self.service.started,0)
    def test_stale_patrol_not_sent(self):
        self.tick(self.due);self.tick(self.due+timedelta(minutes=10));self.assertEqual(self.service.patrols,0)
    def test_pause_does_not_start_prepared(self):
        self.scheduler.cancelled=lambda:True;self.tick(self.due);self.assertEqual(self.service.started,0)
    def test_date_rollover_new_event(self):
        self.tick(self.due);self.tick(self.due+timedelta(days=1));self.assertEqual(self.service.started,2)
    def test_reuse_title_only_date(self):
        title='20th sept 2026 | Mangal Arati Darshan | ISKCON Kolkata Official'
        self.assertEqual(title_for(title,SLOTS[0],date(2026,10,1)), '1st Oct 2026 | Mangal Arati Darshan | ISKCON Kolkata Official')
    def test_ordinals_and_31(self):
        for n,s in [(1,'st'),(2,'nd'),(3,'rd'),(11,'th'),(12,'th'),(13,'th'),(21,'st'),(31,'st')]:
            self.assertTrue(date_prefix(date(2026,10,n)).startswith(str(n)+s+' '))
    def test_wrong_program_refused(self):
        with self.assertRaises(RuntimeError):title_for('20th Sept 2026 | Rajbhog Arati | ISKCON Kolkata',SLOTS[0],self.due.date())
    def test_default_schedule_never_ends_automatically(self):
        from schedule_config import get_schedule
        self.assertTrue(all(not s['end_at'] for s in get_schedule({})))
        self.tick(self.due);self.tick(self.due+timedelta(minutes=30))
        self.assertNotEqual(self.journal.get(SLOTS[0],self.due.date()).get('phase'),'ended')

if __name__=='__main__':unittest.main()
