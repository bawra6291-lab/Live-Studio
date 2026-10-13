"""Approved social posts, independent of the live-stream controller.

All platform writes have a durable receipt before being sent. An interrupted
write is held for manual review, never automatically sent a second time.
"""
from __future__ import annotations
import base64, copy, hashlib, ipaddress, json, re, secrets, threading, time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from core import atomic_json, now_ist

PLATFORMS = ('facebook', 'instagram', 'youtube')
MAX_FILE = 1024 * 1024 * 1024
CHUNK = 512 * 1024
MAX_STORAGE = 5 * MAX_FILE


def https_media(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError('Enter a public HTTPS media URL.')
    p = urlsplit(value)
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.fragment or p.port not in (None,443):
        raise ValueError('Media URLs must use public HTTPS without a login or fragment.')
    host = p.hostname.lower()
    if host == 'localhost' or host.endswith(('.local','.internal')) or '.' not in host:
        raise ValueError('Instagram cannot read a private PC media address.')
    try:
        if not ipaddress.ip_address(host).is_global:raise ValueError('Use a public media address.')
    except ValueError as exc:
        if re.fullmatch(r'[0-9.]+',host) or ':' in host:raise ValueError('Use a public media address.') from exc
    return value


def asset_type(path, name):
    size = path.stat().st_size
    with path.open('rb') as f:
        head = f.read(256*1024);f.seek(max(0,size-12));tail=f.read()
    if head.startswith(b'\x89PNG\r\n\x1a\n') and head[12:16] == b'IHDR' and tail.endswith(b'IEND\xaeB`\x82'):
        width=int.from_bytes(head[16:20],'big');height=int.from_bytes(head[20:24],'big');kind='image/png'
    elif head.startswith(b'\xff\xd8') and tail.endswith(b'\xff\xd9'):
        width=height=0;pos=2;kind='image/jpeg'
        while pos+4<len(head):
            if head[pos]!=255:pos+=1;continue
            marker=head[pos+1];pos+=2
            if marker in (0,255,216,217) or 208<=marker<=215:continue
            length=int.from_bytes(head[pos:pos+2],'big')
            if length<2:break
            if marker in (192,193,194) and length>=7:
                height=int.from_bytes(head[pos+3:pos+5],'big');width=int.from_bytes(head[pos+5:pos+7],'big');break
            pos+=length
    elif len(head)>=24 and head[4:8]==b'ftyp' and name.lower().endswith(('.mp4','.mov')):
        return 'video/mp4',0,0
    else:raise ValueError('Upload JPG, PNG or MP4/MOV. Export camera RAW files to JPG first.')
    if not width or not height or max(width,height)>16384 or size>25*1024*1024:
        raise ValueError('Images must be valid, under 25 MB and at most 16384 pixels.')
    return kind,width,height


class Social:
    def __init__(self, controller, publisher_factory=None):
        self.c=controller;self.folder=controller.base/'social-media';self.folder.mkdir(exist_ok=True)
        self.path=controller.base/'social-posts.json';self.lock=threading.RLock()
        self.stop=threading.Event();self.thread=None;self.worker=None;self.uploads={};self.error=''
        self.publisher_factory=publisher_factory
        try:
            self.data=json.loads(self.path.read_text('utf-8')) if self.path.exists() else {'schema':1,'enabled':False,'instagram_id':'','assets':{},'jobs':[]}
            if self.data.get('schema')!=1 or not isinstance(self.data.get('assets'),dict) or not isinstance(self.data.get('jobs'),list):raise ValueError()
            changed=False
            for job in self.data['jobs']:
                if job.get('status')=='publishing':
                    job.update(status='needs_review',error='App restarted during posting. Check the platforms; no duplicate was sent.');changed=True
            if changed:self.persist()
        except (OSError,ValueError,AttributeError):
            self.error='Posting storage needs local review. Existing file was retained; posting is disabled.'
            self.data={'schema':1,'enabled':False,'instagram_id':'','assets':{},'jobs':[]}
        # Partial imports are not posts and are safe to remove after a restart.
        for p in self.folder.glob('*.part'):p.unlink(missing_ok=True)
        self.accounts={};self.account_message='Check your posting accounts before approving a post.'

    def persist(self):
        if self.error:raise ValueError(self.error)
        atomic_json(self.path,self.data)

    @property
    def busy(self):return bool(self.worker and self.worker.is_alive())

    def ready(self):
        if self.error:raise ValueError(self.error)
        if self.c.closing or self.c.maintenance:raise ValueError('Wait for the app update or shutdown.')

    def snapshot(self):
        with self.lock:
            jobs=[]
            for job in self.data['jobs']:
                item={k:copy.deepcopy(job.get(k)) for k in ('id','revision','title','caption','media','platforms','publish_at','privacy','made_for_kids','status','created_at','results','error','approved_at','targets')}
                jobs.append(item)
            return {'enabled':self.data['enabled'],'busy':self.busy,'error':self.error,
                    'instagram_id':self.data['instagram_id'],'accounts':copy.deepcopy(self.accounts),
                    'account_message':self.account_message,'assets':list(copy.deepcopy(self.data['assets']).values()),
                    'jobs':list(reversed(jobs)),'upload_limit_mb':1024}

    def media_path(self, ident):
        if not isinstance(ident,str) or not re.fullmatch('[a-f0-9]{64}',ident):raise ValueError('Invalid media ID.')
        with self.lock:asset=self.data['assets'].get(ident)
        path=self.folder/ident
        if not asset or not path.is_file() or path.stat().st_size!=asset['size']:raise ValueError('Saved media is missing or damaged.')
        return path,asset

    def begin_upload(self, data):
        with self.c.lock,self.lock:
            self.ready()
            size=data.get('size');name=data.get('name')
            if type(size)!=int or not 1<=size<=MAX_FILE or not isinstance(name,str) or not 1<=len(name)<=180:raise ValueError('Use a named file up to 1 GB.')
            self.expire_uploads()
            if len(self.uploads)>=25:raise ValueError('Finish the current batch before uploading more files.')
            total=sum(a['size'] for a in self.data['assets'].values())+sum(a['size'] for a in self.uploads.values())
            if total+size>MAX_STORAGE:raise ValueError('The media library limit is 5 GB. Remove unused media first.')
            ident=secrets.token_hex(16);path=self.folder/(ident+'.part');path.touch()
            self.uploads[ident]={'size':size,'name':Path(name.replace('\\','/')).name,'offset':0,'expires':time.monotonic()+3600}
            return {'upload':ident,'offset':0,'chunk_size':CHUNK}

    def expire_uploads(self):
        for key,row in list(self.uploads.items()):
            if row['expires']<time.monotonic():
                (self.folder/(key+'.part')).unlink(missing_ok=True);self.uploads.pop(key)

    def upload_chunk(self,data):
        with self.c.lock,self.lock:
            self.ready();self.expire_uploads();ident=data.get('upload');row=self.uploads.get(ident) if isinstance(ident,str) else None
            if not row:raise ValueError('Upload expired. Choose the file again.')
            offset=data.get('offset')
            if type(offset)!=int or offset!=row['offset']:raise ValueError('Upload offset changed. Choose the file again.')
            try:raw=base64.b64decode(data.get('data',''),validate=True)
            except Exception:raise ValueError('Invalid media chunk.') from None
            if not raw or len(raw)>CHUNK or offset+len(raw)>row['size']:raise ValueError('Invalid media chunk length.')
            with (self.folder/(ident+'.part')).open('ab') as f:f.write(raw)
            row['offset']+=len(raw);return {'offset':row['offset']}

    def finish_upload(self,data):
        with self.c.lock,self.lock:
            self.ready();ident=data.get('upload');row=self.uploads.get(ident) if isinstance(ident,str) else None
            if not row or row['offset']!=row['size']:raise ValueError('Finish uploading every chunk first.')
            path=self.folder/(ident+'.part')
            try:
                kind,width,height=asset_type(path,row['name']);digest=hashlib.sha256()
                with path.open('rb') as f:
                    for chunk in iter(lambda:f.read(CHUNK),b''):digest.update(chunk)
                key=digest.hexdigest();target=self.folder/key
                if target.exists():path.unlink()
                else:path.replace(target)
                self.data['assets'].setdefault(key,{'id':key,'name':row['name'],'size':row['size'],'type':kind,'width':width,'height':height,'public_url':''})
                self.persist();return copy.deepcopy(self.data['assets'][key])
            finally:self.uploads.pop(ident,None);path.unlink(missing_ok=True)

    def asset_update(self,data):
        with self.c.lock,self.lock:
            self.ready();ident=data.get('id');asset=self.data['assets'].get(ident)
            if not asset:raise ValueError('Choose a saved media file.')
            if any(ident in j['media'] and j['status'] in ('queued','publishing','needs_review','published') for j in self.data['jobs']):raise ValueError('This media belongs to an approved or posted item. Use a new copy to change it.')
            if data.get('action')=='remove':
                if any(ident in j['media'] for j in self.data['jobs']):raise ValueError('Remove its unused drafts first.')
                self.data['assets'].pop(ident);self.persist();(self.folder/ident).unlink(missing_ok=True)
            else:
                value=data.get('public_url','');asset['public_url']=https_media(value) if value else '';self.persist()
            return {'ok':True}

    def job(self, ident):
        job=next((j for j in self.data['jobs'] if j['id']==ident),None)
        if not job:raise ValueError('Post not found.')
        return job

    def targets(self, platforms):
        return {p:(self.c.cfg.get({'facebook':'facebook_page_id','youtube':'youtube_channel_id'}.get(p,''),'') or (self.data.get('youtube_id','') if p=='youtube' else '')) if p!='instagram' else self.data['instagram_id'] for p in platforms}

    def draft(self, data):
        with self.c.lock,self.lock:
            self.ready();existing=self.job(data['id']) if data.get('id') else None
            if existing and data.get('revision')!=existing['revision']:raise ValueError('This draft changed on another device. Reload it before saving.')
            if existing and existing['status'] not in ('draft','cancelled'):raise ValueError('Cancel the queued post before editing. Posted/review items are immutable.')
            title=data.get('title','').strip() if isinstance(data.get('title'),str) else ''
            caption=data.get('caption','')
            platforms=data.get('platforms',[]);media=data.get('media',[])
            if not title or len(title)>100 or not isinstance(caption,str) or len(caption)>5000:raise ValueError('Use a title up to 100 characters and a caption up to 5000.')
            if not isinstance(platforms,list) or not platforms or len(platforms)!=len(set(platforms)) or any(p not in PLATFORMS for p in platforms):raise ValueError('Choose Facebook, Instagram or YouTube.')
            if not isinstance(media,list) or len(media)>10 or len(media)!=len(set(media)) or any(m not in self.data['assets'] for m in media):raise ValueError('Choose up to 10 saved media files.')
            if not caption.strip() and not media:raise ValueError('Add a caption or media.')
            if any(self.data['assets'][m]['type'].startswith('video/') for m in media) and len(media)!=1:raise ValueError('A video post needs exactly one video.')
            if 'youtube' in platforms and any(c in title for c in '<>'):raise ValueError('YouTube titles cannot contain < or >.')
            if 'youtube' in platforms and (len(media)!=1 or self.data['assets'][media[0]]['type']!='video/mp4'):raise ValueError('YouTube posting requires one video; Community posts are not supported by this API.')
            if 'instagram' in platforms and (not media or len(caption)>2200):raise ValueError('Instagram needs media and a caption up to 2200 characters.')
            when=data.get('publish_at','')
            try:
                due=datetime.fromisoformat(when)
                if due.tzinfo is None:raise ValueError()
                due=due.astimezone(now_ist().tzinfo)
            except Exception:raise ValueError('Choose a posting date and time in IST.') from None
            if not now_ist()-timedelta(minutes=1)<=due<=now_ist()+timedelta(days=366):raise ValueError('Choose a posting time within the next year.')
            privacy=data.get('privacy','private')
            if privacy not in ('private','unlisted','public'):raise ValueError('Choose YouTube visibility.')
            if type(data.get('made_for_kids',False))!=bool:raise ValueError('Choose the YouTube audience.')
            job={'id':existing['id'] if existing else secrets.token_hex(12),'revision':(existing['revision']+1) if existing else 1,
                 'title':title,'caption':caption,'platforms':platforms,'media':media,'publish_at':due.isoformat(),
                 'privacy':privacy,'made_for_kids':data.get('made_for_kids',False),'status':'draft',
                 'created_at':existing['created_at'] if existing else now_ist().isoformat(),'results':{},'error':'','approved_at':None,'targets':{}}
            if existing:self.data['jobs'][self.data['jobs'].index(existing)]=job
            else:
                if len(self.data['jobs'])>=300:raise ValueError('Remove unused drafts before adding more posts (300 limit).')
                self.data['jobs'].append(job)
            self.persist();return copy.deepcopy(job)

    def command(self,data):
        with self.c.lock,self.lock:
            self.ready();action=data.get('action')
            if action in ('enable','pause'):
                if action=='enable' and data.get('confirmed') is not True:raise ValueError('Confirm automatic posting before enabling it.')
                self.data['enabled']=action=='enable';self.persist();return {'ok':True}
            job=self.job(data.get('id'))
            if data.get('revision')!=job['revision']:raise ValueError('This post changed. Reload its preview before continuing.')
            if action=='approve':
                if data.get('confirmed') is not True:raise ValueError('Approve the exact preview first.')
                if job['status']!='draft':raise ValueError('Only drafts can be approved.')
                targets=self.targets(job['platforms'])
                if any(not re.fullmatch(r'UC[A-Za-z0-9_-]{22}' if p=='youtube' else r'[0-9]{5,30}',v or '') for p,v in targets.items()):raise ValueError('Save the selected Page/channel and linked Instagram account before approving.')
                due=datetime.fromisoformat(job['publish_at'])
                if due<now_ist():raise ValueError('Choose a future posting time and save the draft again.')
                for ident in job['media']:
                    path,asset=self.media_path(ident)
                    if 'instagram' in job['platforms'] and (asset['type']!='image/jpeg' and not asset.get('public_url')):raise ValueError('Instagram needs JPG images or a public HTTPS URL for a video. Edit PNG as JPG first.')
                    if 'instagram' in job['platforms'] and asset['type']=='image/jpeg' and asset['size']>8*1024*1024:raise ValueError('Export Instagram JPGs under 8 MB with the image editor.')
                    if 'instagram' in job['platforms'] and asset['type']=='image/jpeg' and not 0.8<=asset['width']/asset['height']<=1.91:raise ValueError('Crop Instagram photos to square, 4:5 or landscape (up to 1.91:1).')
                job.update(status='queued',approved_at=now_ist().isoformat(),targets=targets);self.persist()
            elif action=='cancel':
                if job['status'] not in ('queued','draft'):raise ValueError('A started or uncertain post cannot be cancelled here. Inspect the platform first.')
                job.update(status='cancelled',approved_at=None);self.persist()
            elif action=='remove':
                if job['status'] not in ('draft','cancelled'):raise ValueError('Only unused drafts/cancelled posts can be removed.')
                self.data['jobs'].remove(job);self.persist()
            else:raise ValueError('Unsupported posting action.')
            return {'ok':True}

    def reconcile(self,data):
        with self.c.lock,self.lock:
            self.ready()
            if self.busy:raise ValueError('Wait for the posting operation.')
            job=self.job(data.get('id'));platform=data.get('platform');ident=data.get('post_id','')
            if job['status']!='needs_review' or data.get('revision')!=job['revision'] or data.get('confirmed') is not True:raise ValueError('Review the current failed post and confirm its existing platform ID.')
            if platform not in job['platforms'] or job['results'].get(platform,{}).get('status')=='published':raise ValueError('Choose an unresolved destination.')
            if not isinstance(ident,str) or not re.fullmatch(r'[A-Za-z0-9_-]{5,80}',ident):raise ValueError('Paste the existing platform post ID.')
            cfg=copy.deepcopy(self.c.cfg)
            if platform=='youtube':cfg['youtube_channel_id']=job['targets']['youtube']
            frozen=copy.deepcopy(job)
            def work():
                from social_publish import Publisher
                try:
                    result=(self.publisher_factory or Publisher)(cfg,self.c.vault,self,self.stop).review_existing(frozen,platform,ident)
                    with self.lock:
                        item=self.job(frozen['id']);item['results'][platform]={'status':'published','stage':'Existing post verified',**result}
                        if all(item['results'].get(p,{}).get('status')=='published' for p in item['platforms']):item.update(status='published',error='')
                        self.persist()
                except Exception as exc:
                    with self.lock:self.job(frozen['id'])['error']=self.safe_failure(exc);self.persist()
            self.worker=threading.Thread(target=work,daemon=True);self.worker.start();return {'ok':True}

    def save_account(self,data):
        with self.c.lock,self.lock:
            self.ready()
            if self.data['enabled'] or self.busy or any(j['status']=='queued' and 'instagram' in j['platforms'] for j in self.data['jobs']):raise ValueError('Pause posting and cancel queued Instagram posts before changing its account.')
            value=data.get('instagram_id','')
            if value and (not isinstance(value,str) or not re.fullmatch('[0-9]{5,30}',value)):raise ValueError('Use the numeric linked Instagram professional account ID.')
            self.data['instagram_id']=value;self.accounts={};self.persist();return {'ok':True}

    def check_accounts(self):
        with self.c.lock,self.lock:
            self.ready()
            if self.busy:raise ValueError('Wait for the posting operation.')
            cfg=copy.deepcopy(self.c.cfg);ig=self.data['instagram_id']
            def work():
                from social_publish import Publisher
                try:
                    result=(self.publisher_factory or Publisher)(cfg,self.c.vault,self,self.stop).check(ig)
                    with self.lock:
                        self.accounts=result;self.account_message='Accounts checked. Publishing permissions are verified by the actual approved post.'
                        if result.get('youtube') and not self.c.cfg.get('youtube_channel_id'):self.data['youtube_id']=result['youtube']['id'];self.persist()
                except Exception as exc:
                    with self.lock:self.account_message=self.safe_failure(exc)
            self.worker=threading.Thread(target=work,daemon=True);self.worker.start();return {'ok':True}

    @staticmethod
    def safe_failure(exc):
        from connections import SetupError
        return str(exc) if isinstance(exc,SetupError) else 'Posting request failed. Inspect the selected platform before retrying; no automatic duplicate will be sent.'

    def live_blocked(self):
        with self.c.lock:
            if self.c.closing or self.c.maintenance:return True
            if self.c.mode not in ('','arm') or (self.c.mode=='arm' and not self.c.armed):return True
            observed=self.c.monitor.snapshot()
            if observed.get('obs',{}).get('active'):return True
            if self.c.armed:
                from schedule_config import get_schedule, upcoming
                now=now_ist()
                for run in upcoming(get_schedule(self.c.cfg),now-timedelta(minutes=15),days=2,limit=32):
                    prepare=datetime.fromisoformat(run['prepare_at']);due=datetime.fromisoformat(run['due'])
                    if prepare-timedelta(minutes=2)<=now<=due+timedelta(minutes=3):return True
            return False

    def tick(self, now=None):
        now=now or now_ist()
        with self.c.lock,self.lock:
            if self.error or not self.data['enabled'] or self.c.closing or self.c.maintenance or self.busy:return
            # Keep upload traffic out of the live preparation/start/end window.
            if self.live_blocked():return
            job=next((j for j in self.data['jobs'] if j['status']=='queued' and datetime.fromisoformat(j['publish_at'])<=now),None)
            if not job:return
            if (now-datetime.fromisoformat(job['publish_at'])).total_seconds()>15*60:
                job.update(status='needs_review',error='Posting window passed by more than 15 minutes. Review and create a new draft.');self.persist();return
            if job['targets']!=self.targets(job['platforms']):
                job.update(status='needs_review',error='Destination changed after approval. Inspect the targets and create a new draft.');self.persist();return
            job.update(status='publishing',error='');self.persist();ident=job['id'];cfg=copy.deepcopy(self.c.cfg)
            if 'youtube' in job['platforms']:cfg['youtube_channel_id']=job['targets']['youtube']
            def work():
                from social_publish import Publisher
                try:
                    publisher=(self.publisher_factory or Publisher)(cfg,self.c.vault,self,self.stop)
                    publisher.publish(copy.deepcopy(self.job(ident)))
                    with self.lock:self.job(ident)['status']='published';self.persist()
                    self.c.log('Social post completed: '+job['title'])
                except Exception as exc:
                    with self.lock:
                        self.job(ident).update(status='needs_review',error=self.safe_failure(exc));self.data['enabled']=False;self.persist()
                    self.c.log('Social post needs review: '+job['title'])
            self.worker=threading.Thread(target=work,daemon=True);self.worker.start()

    def checkpoint(self,ident,platform,**values):
        with self.lock:
            result=self.job(ident)['results'].setdefault(platform,{})
            result.update(values);self.persist()

    def start(self):
        if self.thread and self.thread.is_alive():return
        def work():
            while not self.stop.wait(2):
                try:self.tick()
                except Exception:
                    with self.lock:self.error='Posting storage could not be updated; review it locally before continuing.'
        self.thread=threading.Thread(target=work,daemon=True);self.thread.start()

    def close(self):self.stop.set()
