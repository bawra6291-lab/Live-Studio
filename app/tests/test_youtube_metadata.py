"""YouTube preparation regression: validate metadata before external writes."""
import copy
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from connections import SetupError, YouTube
from core import IST, SLOTS


class Session:
    def __init__(self):
        self.calls=[];self.fail_update=False;self.events=[]
        self.original={'id':'previous','snippet':{
            'channelId':'channel','title':'26th Sept 2026 | Sandhya Arati',
            'description':'Previous description','tags':['Arati'],
            'categoryId':'29','defaultLanguage':'en',
            'thumbnails':{'high':{'url':'https://i.ytimg.com/vi/previous/hqdefault.jpg'}}}}
        self.reference={'id':SLOTS[3]['reference'],'snippet':{'channelId':'channel','categoryId':'22'}}
        self.source={'id':'previous','snippet':copy.deepcopy(self.original['snippet']),
                     'status':{'privacyStatus':'public'},'contentDetails':{}}

    def request(self,method,url,**kw):
        resource=url.split('/v3/')[1];p=kw['params']
        self.calls.append((method,resource,copy.deepcopy(kw)))
        ok=True
        if method=='GET' and resource=='videos':
            value={'previous':self.original,SLOTS[3]['reference']:self.reference}.get(p['id'])
            out={'items':[copy.deepcopy(value)] if value else []}
        elif method=='GET' and resource=='liveBroadcasts':
            if p.get('broadcastStatus')=='completed':out={'items':[copy.deepcopy(self.source)]}
            else:out={'items':copy.deepcopy(self.events)}
        elif method=='POST' and resource=='liveBroadcasts':
            event=copy.deepcopy(kw['json']);event['id']='new-event'
            self.events.append(event);out=copy.deepcopy(event)
        elif method=='PUT' and resource=='videos':
            ok=not self.fail_update
            out=kw['json'] if ok else {'error':{'errors':[{'reason':'invalidVideoMetadata'}]}}
        elif resource=='liveBroadcasts/bind':
            self.events[0]['contentDetails']['boundStreamId']=p['streamId'];out={}
        elif resource=='thumbnails/set':out={}
        else:raise AssertionError((method,resource,p))
        return Mock(ok=ok,status_code=200 if ok else 400,json=lambda:out)


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.yt=YouTube({},None);self.wire=Session();self.yt.session=self.wire
        self.yt.owned_channel=Mock(return_value={'id':'channel'})
        self.yt.no_other_live=Mock()
        self.yt.stream_for_obs=Mock(return_value={'id':'stream'})
        self.persist=Mock();self.slot=dict(SLOTS[3])
        self.due=datetime(2026,9,27,10,5,tzinfo=IST)

    def prepare(self):
        response=Mock(content=b'thumbnail',headers={'Content-Type':'image/jpeg'})
        with patch.dict(sys.modules,{'requests':Mock(get=Mock(return_value=response))}):
            return self.yt.prepare(self.slot,self.due,'local-key',self.persist)

    def writes(self,method=None,resource=None):
        return [x for x in self.wire.calls if x[0]!='GET' and
                (method is None or x[0]==method) and (resource is None or x[1]==resource)]

    def test_required_fields_copied_and_checked_before_creation(self):
        record=self.prepare();self.assertEqual(record['yt_id'],'new-event')
        body=self.writes('PUT','videos')[0][2]['json']
        self.assertEqual(body,{'id':'new-event','snippet':{
            'title':'27th Sept 2026 | Sandhya Arati','categoryId':'29',
            'description':'Previous description','tags':['Arati'],'defaultLanguage':'en'}})
        reads=[i for i,x in enumerate(self.wire.calls) if x[:2]==('GET','videos')]
        create=next(i for i,x in enumerate(self.wire.calls) if x[:2]==('POST','liveBroadcasts'))
        self.assertLess(max(reads),create)

    def test_missing_category_uses_only_reference_category(self):
        del self.wire.original['snippet']['categoryId'];self.prepare()
        snippet=self.writes('PUT','videos')[0][2]['json']['snippet']
        self.assertEqual(snippet['categoryId'],'22')
        self.assertEqual(snippet['description'],'Previous description')
        self.assertEqual(snippet['tags'],['Arati'])

    def test_missing_or_invalid_category_blocks_before_create(self):
        for value in (None,'',0,'invalid'):
            with self.subTest(value=value):
                self.setUp();self.wire.original['snippet']['categoryId']=value
                self.wire.reference['snippet'].pop('categoryId')
                with self.assertRaisesRegex(SetupError,'category is missing/invalid'):self.prepare()
                self.assertEqual(self.writes(),[]);self.persist.assert_not_called()

    def test_missing_video_blocks_before_create(self):
        self.wire.original=None
        with self.assertRaisesRegex(SetupError,'metadata source is unavailable'):self.prepare()
        self.assertEqual(self.writes(),[])

    def test_fallback_from_other_channel_is_rejected(self):
        self.wire.original['snippet'].pop('categoryId')
        self.wire.reference['snippet']['channelId']='other-channel'
        with self.assertRaisesRegex(SetupError,'another channel'):self.prepare()
        self.assertEqual(self.writes(),[])

    def test_failure_retains_id_and_does_not_retry_bind_or_upload(self):
        self.wire.fail_update=True
        with self.assertRaisesRegex(SetupError,'Broadcast retained.*title and categoryId were included'):self.prepare()
        self.assertEqual([(x[0],x[1]) for x in self.writes()],
                         [('POST','liveBroadcasts'),('PUT','videos')])
        self.persist.assert_called_once_with(yt_id='new-event',
            title='27th Sept 2026 | Sandhya Arati',stage='youtube_metadata')

    def test_existing_schedule_is_not_duplicated_or_overwritten(self):
        self.prepare();self.wire.calls.clear();self.prepare()
        self.assertEqual(self.writes(),[])


if __name__=='__main__':unittest.main()
