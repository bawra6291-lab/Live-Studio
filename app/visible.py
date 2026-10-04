"""Opt-in calibrated UI workflows. Platform API writes are not used in this mode."""
import json
import re
import threading
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from connections import Services, SetupError
from core import atomic_json, now_ist, title_for
from visible_browser import Browser, origin

FLOWS = ('youtube_prepare','facebook_prepare','youtube_go','facebook_go',
         'youtube_end','facebook_end','camera_patrol_start','camera_patrol_stop','camera_preset')
VARIABLES = ('title','description','date','time','number')


def locator(value):
    if not isinstance(value,dict):raise ValueError('Choose a recorded target.')
    if set(value).issubset({'css','label'}) and isinstance(value.get('css'),str) and 0<len(value['css'])<=200:
        if 'label' in value and (not isinstance(value['label'],str) or len(value['label'])>160):raise ValueError('Invalid target label.')
        return dict(value)
    if (set(value)=={'tag','text'} and value['tag'] in ('button','input','textarea','select','a','div','span','ytcp-button','tp-yt-paper-button','yt-formatted-string')
            and isinstance(value['text'],str) and 0<len(value['text'])<=160):
        return dict(value)
    raise ValueError('Invalid visible target. Use a unique CSS selector or a supported recorded label.')


def validate_recipe(raw):
    if not isinstance(raw,dict):raise ValueError('Invalid workflow.')
    identity=raw.get('identity',{})
    text=identity.get('text')
    if not isinstance(text,str) or not text.strip() or len(text)>200:
        raise ValueError('Enter the exact visible account/Page name to check before any clicks.')
    out={'identity':{'locator':locator(identity.get('locator')), 'text':text},'steps':[]}
    steps=raw.get('steps')
    if not isinstance(steps,list) or not 1<=len(steps)<=80:raise ValueError('A workflow needs 1–80 reviewed steps.')
    for step in steps:
        if not isinstance(step,dict) or step.get('kind') not in ('click','fill','assert'):raise ValueError('Unsupported visible step.')
        item={'kind':step['kind'],'locator':locator(step.get('locator'))}
        if item['kind']=='fill':
            if step.get('variable') not in VARIABLES:raise ValueError('Map each text field to title, description, date, time or camera number. Typed values and passwords are not saved.')
            item['variable']=step['variable']
        if item['kind']=='assert':
            if not isinstance(step.get('text'),str) or not 0<len(step['text'])<=200:raise ValueError('Enter the expected result text.')
            item['text']=step['text']
        out['steps'].append(item)
    return out


class Visible:
    def __init__(self, base, stop, log):
        self.path=Path(base)/'visible-workflows.json'
        self.config=json.loads(self.path.read_text('utf-8')) if self.path.exists() else {'mode':'api','recipes':{}}
        if self.config.get('mode') not in ('api','visible'):raise ValueError('Invalid saved execution mode.')
        self.config['recipes']={key:validate_recipe(value) for key,value in self.config.get('recipes',{}).items() if key in FLOWS}
        self.stop,self.log=stop,log
        self.running=False
        self.browser=Browser(base, cancelled=lambda:self.running and stop.is_set())
        self.lock=threading.RLock()
        self.status={'state':'idle','message':'API mode is unchanged. Visible mode requires reviewed workflows for your actual pages.'}
        self.draft=None

    def snapshot(self, local=False):
        with self.lock:
            result={'mode':self.config['mode'],'status':dict(self.status),'recording':self.browser.recording is not None,
                    'configured':list(self.config['recipes'])}
            if local:result.update(recipes=deepcopy(self.config['recipes']),draft=deepcopy(self.draft))
            return result

    def update(self, **data):
        with self.lock:self.status={**data,'at':now_ist().isoformat()}

    def required(self, cfg):
        from schedule_config import get_schedule
        slots=[s for s in get_schedule(cfg) if s['enabled']]
        needed=set(FLOWS[:4])
        if any(s['end_at'] for s in slots):needed.update(FLOWS[4:6])
        for s in slots:
            needed.update('camera_'+a['kind'] for a in s['camera_actions'])
        return needed

    def ready(self, cfg):
        if self.browser.recording:raise ValueError('Finish recording before enabling automation.')
        missing=self.required(cfg)-self.config['recipes'].keys()
        if missing:raise ValueError('Record and review visible workflows first: '+', '.join(sorted(missing)))
        for flow in self.required(cfg):
            if flow.startswith('camera_') and self.config['recipes'][flow]['steps'][-1]['kind']!='assert':
                raise ValueError('Camera workflows must end with an explicit visible result check.')
        self.browser.ready()

    def save(self, data):
        mode=data.get('mode',self.config['mode'])
        if mode not in ('api','visible'):raise ValueError('Choose API or Visible browser mode.')
        if self.browser.recording:raise ValueError('Finish recording before saving.')
        config=deepcopy(self.config)
        if data.get('flow'):
            if data['flow'] not in FLOWS:raise ValueError('Unknown workflow.')
            config['recipes'][data['flow']]=validate_recipe(data.get('recipe'))
        config['mode']=mode
        atomic_json(self.path,config);self.config=config
        self.draft=None
        self.log('Visible workflow settings saved. No browser actions or broadcasts were started.')

    @staticmethod
    def address(flow,cfg,record=None):
        record=record or {}
        service=flow.split('_')[0]
        if service=='youtube':
            ident=record.get('yt_id') or record.get('reference')
            if ident:
                if not re.fullmatch(r'[A-Za-z0-9_-]{11}',str(ident)):raise SetupError('Invalid YouTube event ID for visible page.')
                return 'https://studio.youtube.com/video/'+ident+'/livestreaming'
            channel=cfg.get('youtube_channel_id','')
            return 'https://studio.youtube.com/'+('channel/'+channel+'/livestreaming' if re.fullmatch(r'UC[A-Za-z0-9_-]{22}',channel) else '')
        if service=='facebook':
            page=cfg.get('facebook_page_id','')
            if not re.fullmatch(r'[0-9]{5,30}',page):raise SetupError('Set the verified Facebook Page ID first.')
            ident=record.get('fb_id')
            if ident and not re.fullmatch(r'[0-9_]{5,70}',str(ident)):raise SetupError('Invalid Facebook event ID for visible page.')
            return 'https://www.facebook.com/live/producer/?'+('video_id='+str(ident) if ident else 'page_id='+page)
        base=cfg.get('camera_url','').rstrip('/')
        origin(base)
        if __import__('urllib.parse',fromlist=['urlsplit']).urlsplit(base).path not in ('','/'):
            raise SetupError('Use a camera base address without a page path.')
        return base+'/'

    def command(self, data, cfg):
        action=data.get('action');flow=data.get('flow')
        if flow not in FLOWS and action!='finish':raise ValueError('Choose a workflow.')
        if action=='finish':
            self.draft=None
            try:self.draft=self.browser.finish_recording()
            except SetupError as exc:
                self.update(state='needs_review',message=str(exc));raise
            self.update(state='recorded',message=f'{len(self.draft)} steps captured. Review every step and map text fields before saving. The recording is not automatically approved.')
            self.log(f'Visible recording finished: {len(self.draft)} steps captured. Review is required; no workflow saved yet.')
            return
        record={}
        if flow.startswith('youtube_') and data.get('reference'):record['reference']=data['reference']
        if flow in ('facebook_go','facebook_end') and data.get('facebook_event'):record['fb_id']=data['facebook_event']
        if action=='record' and flow.startswith('youtube_') and not record.get('reference'):
            raise ValueError('Enter the actual YouTube reference/test video ID before recording this workflow.')
        if action=='record' and flow in ('facebook_go','facebook_end') and not record.get('fb_id'):
            raise ValueError('Enter the actual Facebook test video ID before recording Go live or End live.')
        url=self.address(flow,cfg,record)
        if action=='open':
            self.browser.navigate(flow.split('_')[0],url)
            self.update(state='opened',message='Browser opened. Sign in manually and verify the account. No clicks were automated.')
        elif action=='record':
            if data.get('confirmed') is not True:raise ValueError('Confirm recording: your manual clicks can create public events or move a camera.')
            self.draft=None
            self.browser.begin_recording(flow.split('_')[0],url)
            self.update(state='recording',message='Recorder ready. Use only the tab showing LIVE DESK RECORDING and confirm its captured count increases with a harmless click first. Passwords/input values are not recorded.')
        else:raise ValueError('Unknown browser action.')

    def execute(self, flow, cfg, values=None, record=None):
        recipe=self.config['recipes'].get(flow)
        if not recipe:raise SetupError('Visible workflow is not configured: '+flow)
        values=values or {}
        if any(s['kind']=='fill' and s['variable'] not in values for s in recipe['steps']):
            raise SetupError('A visible text field is mapped to data unavailable in this workflow. Correct it before any clicks.')
        def progress(index,total,kind):
            self.update(state='running',flow=flow,step=index,total=total,kind=kind,message=f'{flow}: real browser {kind} {index}/{total}')
        self.running=True
        try:
            self.browser.run(flow.split('_')[0],self.address(flow,cfg,record),recipe,values,progress)
            self.update(state='awaiting_verification',flow=flow,message='Browser steps completed; external result still needs verification.')
        except Exception:
            self.update(state='needs_review',flow=flow,message='Visible step interrupted/failed. Inspect the real page; no automatic API fallback was sent.')
            raise SetupError('Visible '+flow+' failed or was paused. Inspect the browser and both platforms before retrying.') from None
        finally:self.running=False


class VisibleServices(Services):
    """Browser writes, API reads, existing OBS adapter. No duplicate API writer."""
    def __init__(self,cfg,vault,log,visible):
        super().__init__(cfg,vault,log)
        self.visible=visible
        # Existing start/end keep their output-ownership and confirmation checks.
        self.yt.go=lambda ident:self.ui('youtube_go',record={'yt_id':ident})
        self.fb.go=lambda ident:self.ui('facebook_go',record={'fb_id':ident})
        yt_api=self.yt.api;fb_api=self.fb.api
        def yt_read_or_end(method,path,params=None,**kw):
            if method=='GET':return yt_api(method,path,params,**kw)
            if (method=='POST' and path=='liveBroadcasts/transition' and params.get('broadcastStatus')=='complete'):
                self.ui('youtube_end',record={'yt_id':params['id']});return {}
            raise SetupError('API write refused: visible mode owns YouTube writes.')
        def fb_read_or_end(method,path,params=None,**kw):
            if method=='GET':return fb_api(method,path,params,**kw)
            if method=='POST' and params and params.get('end_live_video')=='true':
                self.ui('facebook_end',record={'fb_id':path});return {}
            raise SetupError('API write refused: visible mode owns Facebook writes.')
        self.yt.api=yt_read_or_end;self.fb.api=fb_read_or_end

    def ui(self,flow,values=None,record=None):
        self.visible.execute(flow,self.cfg,values,record)

    def desktop_guard(self):
        if self.visible.stop.is_set():raise SetupError('Visible operation paused before the next OBS/platform step.')
        self.visible.browser.ready()

    def start(self,record):
        self.desktop_guard()
        try:super().start(record)
        except Exception:
            self.visible.update(state='needs_review',message='Start needs review. Inspect OBS and both real platform pages; do not replay blindly.')
            raise
        self.visible.update(state='verified',message='YouTube and Facebook LIVE confirmed through API reads after real browser actions.')

    def end(self,record,persist,*,manual=False):
        self.desktop_guard()
        try:super().end(record,persist,manual=manual)
        except Exception:
            self.visible.update(state='needs_review',message='End needs review. Inspect the recorded broadcasts and OBS outputs.')
            raise
        self.visible.update(state='verified',message='Recorded YouTube/Facebook events ended and associated OBS outputs stopped.')

    def check(self):
        self.visible.ready(self.cfg)
        super().check()
        self.log('Visible browser mode selected: platform clicks use reviewed workflows; OBS uses WebSocket with its real window. Keep Windows unlocked.')

    def prepare(self,slot,due,persist):
        try:return self.prepare_visible(slot,due,persist)
        except Exception:
            self.visible.update(state='needs_review',message='Preparation needs review. A browser action may have created an event. Inspect both platforms before retrying.')
            raise

    def prepare_visible(self,slot,due,persist):
        self.desktop_guard()
        self.obs.close();self.obs.connect(launch=True);self.obs.idle();self.obs.check_profile()
        self.fb.identity();self.fb.no_other_live();channel=self.yt.owned_channel();self.yt.no_other_live()
        for action in slot.get('camera_actions',[]):self.cam.check_action(action)
        source=self.yt.event(slot['reference'])
        if source['snippet']['channelId']!=channel['id']:raise SetupError('Visible reference belongs to another YouTube channel.')
        title=title_for(source['snippet']['title'],slot,due.date())
        stream=self.yt.stream_for_obs(self.obs.key())
        values={'title':title,'description':source['snippet'].get('description',''),'date':due.strftime('%Y-%m-%d'),'time':due.strftime('%H:%M')}
        def matches():
            return [x for x in self.yt.list('liveBroadcasts',part='id,snippet,status,contentDetails',broadcastStatus='upcoming',broadcastType='all',maxResults=50) if x['snippet']['title']==title]
        events=matches()
        if len(events)>1:raise SetupError('Duplicate YouTube schedules exist; review before visible execution.')
        if not events:
            persist(stage='visible_youtube_prepare',title=title,yt_stream_id=stream['id'])
            self.ui('youtube_prepare',values,{'reference':slot['reference']})
            events=matches()
        if len(events)!=1:raise SetupError('Visible YouTube preparation did not produce exactly one verified schedule. Inspect Studio; no automatic retry.')
        event=events[0];persist(yt_id=event['id'],title=title,yt_stream_id=stream['id'])
        details=event['contentDetails']
        if (event['snippet']['channelId']!=channel['id'] or event['status']['privacyStatus']!='public'
                or details.get('boundStreamId')!=stream['id']
                or details.get('enableAutoStart') or details.get('enableAutoStop')):
            raise SetupError('Visible YouTube schedule has the wrong account/privacy/key or automatic start/stop settings. Review it; Official key was not changed by the API.')
        when=datetime.fromisoformat(event['snippet']['scheduledStartTime'].replace('Z','+00:00'))
        if abs((when-due).total_seconds())>60 or event['snippet'].get('description','')!=values['description']:
            raise SetupError('Visible YouTube date/time or description differs from the plan. Review the retained event.')
        recent=self.fb.recent()
        existing=[x for x in recent if x.get('title')==title and x.get('status') in ('UNPUBLISHED','SCHEDULED_UNPUBLISHED','SCHEDULED_LIVE')]
        if len(existing)>1:raise SetupError('Duplicate Facebook schedules exist; review before visible execution.')
        if not existing:
            persist(stage='visible_facebook_prepare')
            self.ui('facebook_prepare',values)
            existing=[x for x in self.fb.recent() if x.get('title')==title and x.get('status') in ('UNPUBLISHED','SCHEDULED_UNPUBLISHED','SCHEDULED_LIVE')]
        if len(existing)!=1:raise SetupError('Visible Facebook preparation did not produce exactly one event on the verified Page. Inspect the Page; no automatic retry.')
        fb_id=existing[0]['id'];persist(fb_id=fb_id)
        detail=self.fb.api('GET',fb_id,{'fields':'secure_stream_url,is_manual_mode,status'})
        if detail.get('status')!='UNPUBLISHED' or detail.get('is_manual_mode') is not True:
            raise SetupError('Visible Facebook draft must use manual Go live, with automatic publishing disabled. Review Live Producer before OBS starts.')
        if not detail.get('secure_stream_url'):raise SetupError('Facebook stream destination is not available for the visible event.')
        self.obs.prepare_fb_output(detail['secure_stream_url'])
        self.visible.update(state='verified',message='Both prepared events verified by API reads. OBS target configured through the existing local adapter.')
        return {'yt_id':event['id'],'yt_stream_id':stream['id'],'fb_id':fb_id,'title':title}

    def camera_action(self,action):
        self.cam.check_action(action)
        recipe=self.visible.config['recipes'].get('camera_'+action['kind'],{})
        if not recipe.get('steps') or recipe['steps'][-1]['kind']!='assert':
            raise SetupError('Visible camera workflow needs a final UI result check before any movement.')
        self.ui('camera_'+action['kind'],{'number':str(action['number'])})
        self.visible.update(state='verified',message='Camera UI result matched its configured check. This is not visual proof of final physical position.')
        self.log('Visible camera UI check passed. Watch the camera feed to confirm actual movement.')
