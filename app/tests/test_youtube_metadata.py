"""YouTube preparation regression: validate metadata before external writes."""
import copy
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from connections import SetupError, YouTube, Services
from core import IST, SLOTS


class Session:
    def __init__(self):
        self.calls=[];self.fail_update=False;self.events=[];self.ignore_bind=False
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
            if not self.ignore_bind:self.events[0]['contentDetails']['boundStreamId']=p['streamId']
            out={}
        elif resource=='thumbnails/set':out={}
        else:raise AssertionError((method,resource,p))
        return Mock(ok=ok,status_code=200 if ok else 400,json=lambda:out)


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.yt=YouTube({'youtube_stream_title':'YouTube Official Livestream'},None);self.wire=Session();self.yt.session=self.wire
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

    def test_failure_retains_bound_event_and_does_not_retry_or_upload(self):
        self.wire.fail_update=True
        with self.assertRaisesRegex(SetupError,'Broadcast retained.*title and categoryId were included'):self.prepare()
        self.assertEqual([(x[0],x[1]) for x in self.writes()],
                         [('POST','liveBroadcasts'),('POST','liveBroadcasts/bind'),('PUT','videos')])
        self.persist.assert_any_call(yt_id='new-event',yt_stream_id='stream',
            title='27th Sept 2026 | Sandhya Arati',stage='youtube_bind')
        self.assertEqual(self.wire.events[0]['contentDetails']['boundStreamId'],'stream')

    def test_blank_language_and_audio_response_fields_not_replayed(self):
        for language in ('',None,'   '):
            with self.subTest(language=language):
                self.setUp()
                self.wire.original['snippet'].update(defaultLanguage=language,defaultAudioLanguage='',
                    localized={'title':'Read-only title'},liveBroadcastContent='none')
                self.prepare()
                body=self.writes('PUT','videos')[0][2]['json']['snippet']
                self.assertEqual(set(body),{'title','categoryId','description','tags'})

    def test_binding_must_be_confirmed_before_metadata_or_thumbnail(self):
        self.wire.ignore_bind=True
        with self.assertRaisesRegex(SetupError,'did not confirm'):self.prepare()
        self.assertEqual([(x[0],x[1]) for x in self.writes()],
                         [('POST','liveBroadcasts'),('POST','liveBroadcasts/bind')])

    def test_existing_wrong_key_schedule_is_not_rebound(self):
        self.prepare();self.wire.calls.clear()
        self.wire.events[0]['contentDetails']['boundStreamId']='another-stream'
        with self.assertRaisesRegex(SetupError,'another stream key'):self.prepare()
        self.assertEqual(self.writes(),[])

    def test_existing_schedule_is_not_duplicated_or_overwritten(self):
        self.prepare();self.wire.calls.clear();self.prepare()
        self.assertEqual(self.writes(),[])


class StreamSelectionTests(unittest.TestCase):
    def test_binding_change_after_preparation_blocks_obs_start(self):
        service=Services({},None)
        service.obs=Mock();service.yt=Mock();service.fb=Mock()
        service.yt.stream_for_obs.return_value={'id':'official-stream'}
        service.yt.event.return_value={'contentDetails':{'boundStreamId':'default-stream'}}
        with self.assertRaisesRegex(SetupError,'binding changed'):
            service.start({'yt_id':'event','yt_stream_id':'official-stream','fb_id':'fb-event'})
        service.obs.start.assert_not_called()
        service.yt.go.assert_not_called();service.fb.go.assert_not_called()

    def test_requires_both_existing_obs_key_and_official_title(self):
        for title,key,accepted in [('YouTube Official Livestream','same-secret',True),
                ('Default stream key','same-secret',False),
                ('YouTube Official Livestream','different-secret',False)]:
            with self.subTest(title=title,key=key):
                yt=YouTube({'youtube_stream_title':'YouTube Official Livestream'},None)
                yt.list=Mock(return_value=[{'id':'existing-stream','snippet':{'title':title},
                    'cdn':{'ingestionInfo':{'streamName':key}}}])
                if accepted:self.assertEqual(yt.stream_for_obs('same-secret')['id'],'existing-stream')
                else:
                    with self.assertRaises(SetupError) as error:yt.stream_for_obs('same-secret')
                    self.assertNotIn('same-secret',str(error.exception))
                    self.assertNotIn('different-secret',str(error.exception))
                self.assertIn('snippet',yt.list.call_args.kwargs['part'])


if __name__=='__main__':unittest.main()
