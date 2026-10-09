"""Read-only readiness, observed live status and run progress. No launch or write APIs."""
import base64, json, os, re, threading, time
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from core import Journal, now_ist, title_for
from schedule_config import get_schedule, action_time


def progress(journal,mode='',armed=False):
    rows=[(k,r) for k,r in journal.data.items() if r.get('plan')]
    rows.sort(key=lambda x:x[1].get('scheduled_at',x[0]),reverse=True)
    rows.sort(key=lambda x:2 if x[1].get('phase') in ('starting','live') else 1 if x[1].get('phase') in ('preparing','prepared','needs_review') else 0,reverse=True)
    if not rows:return {'name':'Connections' if mode in ('arm','check') else 'No recorded run','stage':'Checking connections' if mode in ('arm','check') else 'Waiting for your saved schedule','steps':[],'camera':[],'error':''}
    key,r=rows[0];phase=r.get('phase','new');stage=r.get('stage','');failed=phase=='needs_review' or r.get('end_state')=='needs_review'
    defs=[('prepare','Connection checks'),('youtube','YouTube schedule'),('facebook','Facebook draft'),('obs','OBS output'),('live','Both destinations live'),('camera','Camera plan'),('end','Ending')]
    current=0 if stage=='prepare' else 1 if stage.startswith(('youtube','visible_youtube')) else 2 if stage.startswith(('facebook','visible_facebook')) else 3 if stage in ('obs_configure','starting_obs','waiting_for_ingest','publishing_live','youtube_publish','facebook_publish','confirming_live') else 4 if phase in ('live','done') else 6 if stage in ('ending','operator_ending','finished') else 1
    done=[bool(r.get('yt_id')),bool(r.get('yt_id') and not stage.startswith(('youtube','visible_youtube'))),bool(r.get('fb_id') and stage not in ('facebook_prepare','visible_facebook_prepare')),bool(r.get('obs_start_epoch')),bool(r.get('confirmed_at')),bool(r.get('camera_states')) and all(x=='sent' for x in r['camera_states'].values()),r.get('phase')=='ended']
    steps=[{'id':ident,'label':label,'status':'failed' if failed and i==current else 'done' if done[i] else 'running' if i==current and phase in ('preparing','starting') else 'waiting'} for i,(ident,label) in enumerate(defs)]
    if not r['plan'].get('camera_actions'):steps[5]['status']='not requested'
    if not r['plan'].get('end_at') and phase!='ended':steps[6]['status']='manual end'
    camera=[]
    for i,a in enumerate(r['plan'].get('camera_actions',[])):
        due=action_time(datetime.fromisoformat(key.split(':')[0]).date(),a,r)
        camera.append({'label':a['kind'].replace('_',' ')+' '+str(a['number']),'state':r.get('camera_states',{}).get(str(i),'pending'),'due':due.isoformat() if due else None})
    return {'key':key,'name':r['plan']['name'],'phase':phase,'stage':stage.replace('_',' ') or phase,'steps':steps,'camera':camera,'error':r.get('last_error',''),'confirmed_at':r.get('confirmed_at'),'started_by_app':bool(r.get('obs_start_epoch')),'end_at':r['plan'].get('end_at','')}


def readiness(controller):
    c=controller;cfg=c.cfg;items=[]
    def add(ident,label,status,detail,view='connections',action=''):
        items.append({'id':ident,'label':label,'status':status,'detail':detail,'view':view,'action':action})
    slots=[s for s in get_schedule(cfg) if s['enabled']]
    add('schedule','Saved programs','ready' if slots else 'blocked',str(len(slots))+' enabled program(s).','schedule')
    for key,label in [('obs','OBS'),('youtube','YouTube authorization'),('facebook','Facebook Page token'),('camera','Camera actions')]:
        value=c.connections.get(key,'unchecked')
        add(key,label,'ready' if value in ('verified','skipped') else 'pending','Latest connection check: '+value+'. Enable performs a fresh check.','connections','youtube' if key=='youtube' else 'check')
    if cfg.get('google_client_file') and not Path(cfg['google_client_file']).is_file():add('oauth_file','Google OAuth JSON','blocked','Saved file is missing. Select the newly downloaded JSON in Connections.')
    for slot in slots:
        try:
            if slot.get('title_template'):title_for('',slot,now_ist().date())
            for ident in set(slot.get('thumbnail_days',{}).values()):c.content.get(ident)
        except (ValueError,RuntimeError):add('content_'+slot['id'],slot['name']+' content','blocked','Title or saved thumbnail needs repair.','content')
    v=c.visible
    if v.config['mode']=='visible':
        missing=sorted(v.required(cfg)-set(v.config['recipes']))
        add('workflows','Visible workflows','blocked' if missing else 'ready','Missing: '+', '.join(missing) if missing else 'Required workflows are saved.','visible')
        if v.config.get('browser_source')=='running_chrome':add('chrome','Running Chrome','ready' if v.browser.chrome and not v.browser.chrome.closed else 'blocked','Connect your existing Chrome locally after app/browser restart.','visible')
        if v.browser.recording:add('recording','Workflow recording','blocked','Finish recording before enabling.','visible')
    recent=c.checked and datetime.fromisoformat(c.checked)>now_ist()-timedelta(minutes=10)
    add('fresh','Recent full check','ready' if recent else 'pending','A full connection check is recommended before enabling.','connections','check')
    if c.error:add('last_error','Last operation','blocked',c.message[:500],'recovery')
    return {'items':items,'blockers':sum(x['status']=='blocked' for x in items),'pending':sum(x['status']=='pending' for x in items),'checked_at':c.checked}


def recovery_guide(record):
    error=record.get('last_error','').lower();kind='inspection';view='recovery'
    if 'youtube login' in error or 'oauth' in error:kind='youtube_login';view='connections'
    elif 'facebook' in error and any(x in error for x in ('token','190')):kind='facebook_token';view='connections'
    elif 'metadata' in error or 'category' in error:kind='youtube_metadata';view='content'
    elif 'output reload' in error or 'profile' in error:kind='obs_output';view='connections'
    elif 'window' in error or record.get('phase')=='missed':kind='missed_window';view='schedule'
    elif 'chrome' in error or 'visible' in error:kind='chrome_workflow';view='visible'
    details={'youtube_login':'Reconnect YouTube on this PC, then check connections.', 'facebook_token':'Replace the Page token on this PC, save, then check connections.', 'youtube_metadata':'Check the reference category, title and saved content. Keep the existing draft for inspection.', 'obs_output':'Check the selected OBS profile and FB Live target. Inspect outputs before attempting another start.', 'missed_window':'Check PC awake/startup and your IST timing. A missed run is not started late automatically.', 'chrome_workflow':'Connect Chrome and review the recorded workflow locally.', 'inspection':'Inspect the exact recorded OBS outputs and both platform events first.'}
    return {'kind':kind,'view':view,'detail':details[kind],'steps':['Pause automation.','Open the recorded platform events and inspect the run.',details[kind],'Mark reviewed only after inactive outputs are verified. Save a future time and enable after a fresh check.'],'automatic_retry':False}


class LiveMonitor:
    def __init__(self,controller):
        self.c=controller;self.lock=threading.RLock();self.stop=threading.Event();self.thread=None;self.last_platform=0;self.record_key='';self.last_bytes=None
        self.value={'observed_at':None,'platform_at':None,'obs':{'connected':False},'youtube':'unknown','facebook':'unknown','frame':'','frame_at':None,'error':''}
    def snapshot(self):
        with self.lock:return deepcopy(self.value)
    def start(self):
        if self.thread and self.thread.is_alive():return
        self.thread=threading.Thread(target=self.work,daemon=True);self.thread.start()
    def close(self):self.stop.set()
    def work(self):
        while not self.stop.is_set():
            try:self.sample()
            except Exception:
                with self.lock:self.value.update(error='Live monitor unavailable; inspect OBS on this PC.',observed_at=now_ist().isoformat(),frame='',frame_at=None)
            self.stop.wait(15)
    def sample(self):
        c=self.c
        with c.lock:
            if c.maintenance or c.closing:return
            cfg=dict(c.cfg);journal=Journal(c.base/'journal.json')
        rows=[(k,r) for k,r in journal.data.items() if r.get('yt_id') or r.get('fb_id')]
        rows.sort(key=lambda x:x[1].get('scheduled_at',x[0]),reverse=True);rows.sort(key=lambda x:x[1].get('phase') in ('starting','live'),reverse=True);key,record=next(((k,r) for k,r in rows if r.get('phase') in ('starting','live','needs_review','prepared')),rows[0] if rows else ('',{}))
        service=c.factory(cfg,c.vault,lambda _:None);result=self.snapshot();result.update(observed_at=now_ist().isoformat(),error='',frame='',frame_at=None,record_key=key)
        try:
            try:
                service.obs.connect(launch=False)
                status=service.obs.call('GetStreamStatus');outputs=service.obs.call('GetOutputList').get('outputs',[])
                result['obs']={'connected':True,'active':bool(status.get('outputActive') or any(x.get('outputActive') for x in outputs)),'main_active':bool(status.get('outputActive')),'reconnecting':bool(status.get('outputReconnecting')),'duration_ms':status.get('outputDuration',0),'bytes':status.get('outputBytes',0),'outputs':[{'name':x.get('outputName',''),'active':bool(x.get('outputActive'))} for x in outputs]}
                t=time.monotonic();b=status.get('outputBytes',0)
                result['obs']['kbps']=max(0,round((b-self.last_bytes[1])*8/(t-self.last_bytes[0])/1000)) if self.last_bytes and b>=self.last_bytes[1] and t>self.last_bytes[0] else None
                self.last_bytes=(t,b)
                scene=service.obs.call('GetCurrentProgramScene').get('currentProgramSceneName','')
                result['obs']['scene']=scene
                try:
                    frame=service.obs.call('GetSourceScreenshot',sourceName=scene,imageFormat='jpg',imageWidth=320,imageHeight=180,imageCompressionQuality=20).get('imageData','')
                    if re.fullmatch(r'data:image/(?:jpeg|jpg);base64,[A-Za-z0-9+/=]+',frame) and len(frame)<=22000:
                        data=base64.b64decode(frame.split(',',1)[1],validate=True)
                        if data.startswith(b'\xff\xd8'):result.update(frame=frame,frame_at=now_ist().isoformat())
                except Exception:pass
            except Exception:result['obs']={'connected':False};result['error']='OBS monitoring unavailable. Open OBS and check WebSocket locally.'
            if key!=self.record_key or time.monotonic()-self.last_platform>=60:
                result.update(youtube='not recorded',facebook='not recorded',platform_at=now_ist().isoformat())
                if record.get('yt_id'):
                    try:service.yt.owned_channel();result['youtube']=service.yt.event(record['yt_id'])['status']['lifeCycleStatus']
                    except Exception:result['youtube']='unavailable'
                if record.get('fb_id'):
                    try:
                        service.fb.identity()
                        if not any(x['id']==record['fb_id'] for x in service.fb.recent()):raise ValueError('Wrong Page event')
                        result['facebook']=service.fb.api('GET',record['fb_id'],{'fields':'status'}).get('status','unknown')
                    except Exception:result['facebook']='unavailable'
                self.last_platform=time.monotonic();self.record_key=key
        finally:service.close()
        with self.lock:self.value=result
