"""DARSHANFLOW connections and deliberate posting. No browser-stored secrets.

YouTube Community and WhatsApp handoffs are never reported as API deliveries.
The original photo sequencer remains an independent, preserved document.
"""
from __future__ import annotations
import copy, json, re, threading
from datetime import timedelta, date
from urllib.parse import urlsplit
from core import atomic_json, now_ist, Journal
from connections import Facebook, YouTube, SetupError
from social_publish import Publisher
from telegram_publish import Telegram, channel_id, bot_token, caption_length
from studio_batch import StudioBatch

SECRETS = {'instagram_login_token', 'instagram_imgbb_key'}
DOCS = 'https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/'


def public_link(value, platform):
    if not isinstance(value, str) or len(value) > 2048:raise ValueError('Use a valid public post link.')
    value=value.strip()
    if not value:return ''
    p=urlsplit(value)
    allowed={'youtube':{'youtube.com','www.youtube.com','youtu.be'},
             'facebook':{'facebook.com','www.facebook.com','m.facebook.com','fb.watch'},
             'whatsapp':{'chat.whatsapp.com','www.whatsapp.com','whatsapp.com'}}[platform]
    if p.scheme!='https' or p.hostname not in allowed or p.username or p.password or p.port not in (None,443):
        raise ValueError('Use an HTTPS '+platform+' link from that platform.')
    if not p.path.strip('/'):raise ValueError('Use the link to the post or destination, not the website homepage.')
    return value


class DirectInstagram(Publisher):
    """Instagram Login tokens use graph.instagram.com, never the Page token."""
    def graph(self,method,path,values=None,file=None,video=False):
        import requests
        token=self.vault.get('instagram_login_token')
        if not token:raise SetupError('Save an Instagram Login access token in DARSHANFLOW Connections.',retryable=False)
        version=self.cfg.get('graph_version','v23.0')
        if not re.fullmatch(r'v\d+\.0',version):raise SetupError('Invalid Meta API version.',retryable=False)
        try:
            response=requests.request(method,'https://graph.instagram.com/'+version+'/'+path,
                headers={'Authorization':'Bearer '+token},
                **{'params' if method=='GET' else 'data':values or {}},timeout=(10,60),allow_redirects=False)
            result=response.json()
        except Exception:raise SetupError('Instagram request outcome is uncertain. Check Instagram before retrying.',retryable=False) from None
        if not response.ok or 'error' in result:
            code=result.get('error',{}).get('code')
            if code==190:message='Instagram login expired or was revoked. Save a new Instagram Login token.'
            elif code in (4,17,32,613):message='Instagram request limit reached. Wait before checking again; no automatic retry was sent.'
            else:message='Instagram rejected the request. Check the professional account, token and content publishing permission.'
            raise SetupError(message,retryable=False)
        return result

    def identity(self):
        item=self.graph('GET','me',{'fields':'user_id,username'})
        ident=str(item.get('user_id') or item.get('id') or '')
        if not re.fullmatch(r'[0-9]{5,30}',ident):raise SetupError('Instagram did not return a professional account ID.',retryable=False)
        return {'id':ident,'name':str(item.get('username','Instagram'))[:120]}

    def instagram_source(self,job,ident):
        import requests
        key=self.vault.get('instagram_imgbb_key')
        if not key:raise SetupError('Save an ImgBB key for temporary Instagram photo hosting.',retryable=False)
        path,asset=self.manager.media_path(ident)
        if asset['type']!='image/jpeg':raise SetupError('Instagram carousel needs JPG photos.',retryable=False)
        self.cancelled();self.checkpoint(job,'instagram',status='sending',stage='Preparing temporary Instagram photo')
        try:
            with path.open('rb') as f:
                r=requests.post('https://api.imgbb.com/1/upload',data={'key':key,'expiration':'3600'},
                    files={'image':('darshan.jpg',f,'image/jpeg')},timeout=(10,90),allow_redirects=False)
            body=r.json();url=body.get('data',{}).get('url','');p=urlsplit(url)
            if not r.ok or body.get('success') is not True or p.scheme!='https' or p.hostname!='i.ibb.co' or p.username or p.password:
                raise ValueError()
        except Exception:raise SetupError('Temporary photo hosting failed. Check the ImgBB key; no Instagram post was confirmed.',retryable=False) from None
        return url

    def publish(self,job):
        self.cancelled();self.verify_media(job)
        if job['platforms']!=['instagram'] or self.identity()['id']!=job['targets']['instagram']:
            raise SetupError('Instagram account changed. Review the selected account before posting.',retryable=False)
        self.post_instagram(job)


class Studio(StudioBatch):
    def __init__(self,controller):
        self.c=controller;self.s=controller.social;self.path=controller.base/'darshanflow.json'
        self.accounts={};self.error='';self.exports={}
        self.data={'schema':1,'caption':{},'share':{},'receipts':{}}
        if self.path.exists():
            try:
                data=json.loads(self.path.read_text('utf-8'))
                if data.get('schema')!=1 or not all(isinstance(data.get(k),dict) for k in ('caption','share','receipts')):raise ValueError()
                self.data=data
                for batch in self.data.get('batches',[]):
                    if batch.get('status')=='publishing':batch.update(status='needs_review',error='App restarted during batch posting. Inspect each platform; this batch will not resume automatically.')
            except Exception:self.error='DARSHANFLOW settings need local review. The existing file has been retained.'

    def ready(self):
        self.s.ready()
        if self.error:raise ValueError(self.error)

    def persist(self):self.ready();atomic_json(self.path,self.data)

    def state(self,local=False):
        with self.c.lock,self.s.lock:
            saved={p:self.c.cfg.get(k,'') for p,k in [('facebook','facebook_page_id'),('youtube','youtube_channel_id')]}
            saved['telegram']=self.data.get('telegram',{}).get('channel','')
            accounts=copy.deepcopy(self.accounts)
            for p,ident in saved.items():
                current=accounts.get(p,{})
                if (current.get('source_channel') if p=='telegram' else current.get('id'))!=ident and ident:accounts.pop(p,None)
            result={'accounts':accounts,'saved':saved,'local':local,'error':self.error,
                    'busy':self.s.busy,'caption':copy.deepcopy(self.data['caption']),
                    'share':copy.deepcopy(self.data['share']),'receipts':copy.deepcopy(self.data['receipts']),
                    'instagram_id':self.s.data.get('studio_instagram_id',''),
                    'instagram_token_saved':bool(self.c.vault.get('instagram_login_token')),
                    'hosting_key_saved':bool(self.c.vault.get('instagram_imgbb_key')),
                    'telegram_token_saved':bool(self.c.vault.get('telegram_bot_token')),
                    'jobs':[j for j in self.s.snapshot()['jobs'] if j['id'] in self.data.get('jobs',[])][:80],
                    'batches':copy.deepcopy(self.data.get('batches',[])[-20:]),
                    'live_links':[]}
            for key,rec in Journal(self.c.base/'journal.json').data.items():
                if key.startswith(now_ist().date().isoformat()) and rec.get('confirmed_at'):
                    yt=str(rec.get('yt_id',''));fb=str(rec.get('fb_id',''))
                    result['live_links'].append({'name':rec.get('plan',{}).get('name','Live darshan'),
                        'youtube':'https://www.youtube.com/watch?v='+yt if re.fullmatch(r'[A-Za-z0-9_-]{11}',yt) else '',
                        'facebook':'https://www.facebook.com/'+fb if re.fullmatch(r'[0-9_]{5,70}',fb) else ''})
            return result

    def save(self,data):
        with self.c.lock,self.s.lock:
            self.ready()
            if 'caption' in data:
                values=data['caption']
                if not isinstance(values,dict) or any(not isinstance(values.get(k,''),str) or len(values.get(k,''))>n for k,n in [('title',100),('body',4000),('tags',1000)]):raise ValueError('Shorten the title or caption.')
                day=values.get('date','')
                if not isinstance(day,str):raise ValueError('Choose a caption date.')
                if day:date.fromisoformat(day)
                self.data['caption']={k:values.get(k,'').strip() for k in ('title','body','tags')}
                if day:self.data['caption']['date']=day
            if 'share' in data:
                values=data['share']
                if not isinstance(values,dict):raise ValueError('Invalid sharing settings.')
                day=values.get('date','');date.fromisoformat(day)
                rows=values.get('programs',[]);targets=values.get('targets',[])
                if not isinstance(rows,list) or not 1<=len(rows)<=12 or not isinstance(targets,list) or len(targets)!=9:raise ValueError('Use up to 12 programs, 8 communities and one channel.')
                def name(row):
                    v=row.get('name','')
                    if not isinstance(v,str) or len(v)>100:raise ValueError('Use names up to 100 characters.')
                    return v.strip()
                clean={'date':day,'programs':[{'name':name(r),'youtube':public_link(r.get('youtube',''),'youtube'),'facebook':public_link(r.get('facebook',''),'facebook')} for r in rows],
                       'targets':[{'name':name(r),'url':public_link(r.get('url',''),'whatsapp')} for r in targets]}
                if clean!=self.data['share']:self.data['receipts']={}
                self.data['share']=clean
            self.persist();return {'ok':True}

    def save_instagram(self,data):
        with self.c.lock,self.s.lock:
            self.ready()
            if self.s.busy:raise ValueError('Wait for the current posting operation.')
            for key in SECRETS:
                value=data.get(key,'')
                if not isinstance(value,str) or len(value)>4096 or any(x.isspace() for x in value.strip()):raise ValueError('Paste the complete token/key without spaces.')
            changed=bool(data.get('instagram_login_token','').strip())
            for key in SECRETS:
                if data.get(key,'').strip():self.c.vault.set(key,data[key].strip())
            if changed:self.accounts.pop('instagram',None);self.s.data['studio_instagram_id']='';self.s.persist()
            return {'ok':True}

    def check(self,data):
        platform=data.get('platform')
        if platform not in ('facebook','youtube','instagram','telegram'):raise ValueError('Choose a connection.')
        with self.c.lock,self.s.lock:
            self.ready()
            if self.s.busy:raise ValueError('Wait for the current connection or posting operation.')
            cfg=copy.deepcopy(self.c.cfg)
            cfg['telegram_channel']=self.data.get('telegram',{}).get('channel','')
            self.accounts[platform]={'status':'checking','name':'Checking…'}
            def work():
                try:
                    if platform=='telegram':
                        item=Telegram(cfg,self.c.vault,self.s,self.s.stop).identity()
                        item['source_channel']=cfg['telegram_channel']
                    elif platform=='instagram':item=DirectInstagram(cfg,self.c.vault,self.s,self.s.stop).identity()
                    elif platform=='facebook':
                        item=Facebook(cfg,self.c.vault).identity();item={'id':item['id'],'name':item.get('name','Facebook Page')}
                    else:
                        yt=YouTube(cfg,self.c.vault);yt.connect();channel=yt.owned_channel();item={'id':channel['id'],'name':channel['snippet']['title']}
                    with self.s.lock:
                        self.accounts[platform]={**item,'status':'verified'}
                        if platform=='instagram':self.s.data['studio_instagram_id']=item['id'];self.s.persist()
                except Exception as exc:
                    with self.s.lock:self.accounts[platform]={'status':'error','message':self.s.safe_failure(exc)}
            self.s.worker=threading.Thread(target=work,daemon=True);self.s.worker.start()
            return {'ok':True}

    def save_telegram(self,data):
        with self.c.lock,self.s.lock:
            self.ready()
            if self.s.busy:raise ValueError('Wait for the current connection or posting operation.')
            channel=channel_id(data.get('channel',''))
            value=data.get('token','')
            if not isinstance(value,str):raise ValueError('Paste the Telegram bot token.')
            token=bot_token(value) if value.strip() else ''
            if not token and not self.c.vault.get('telegram_bot_token'):raise ValueError('Save a Telegram bot token from BotFather first.')
            if token:self.c.vault.set('telegram_bot_token',token)
            self.data['telegram']={'channel':channel};self.persist()
            self.accounts.pop('telegram',None)
            return {'ok':True}

    def prepare(self,data, *, _persist=True):
        with self.c.lock,self.s.lock:
            self.ready();platform=data.get('platform');mode=data.get('mode')
            if platform not in ('facebook','instagram','youtube','telegram') or mode not in ('P1','P2','FB','TG'):raise ValueError('Choose a posting destination and photo sequence.')
            if (mode=='FB' and platform!='facebook') or (mode=='TG' and platform!='telegram'):raise ValueError('Use 7 portraits, 10 landscapes, Facebook mixed order or Telegram albums.')
            media=data.get('media',[])
            if not isinstance(media,list) or len(media)!= {'P1':7,'P2':10,'FB':17,'TG':17}[mode]:raise ValueError('Upload and review every photo in the selected sequence first.')
            account=self.accounts.get(platform,{})
            if platform!='youtube' and account.get('status')!='verified':raise ValueError('Verify the selected posting account first.')
            if platform=='facebook' and account.get('id')!=self.c.cfg.get('facebook_page_id'):raise ValueError('Facebook Page changed. Verify it again.')
            if platform=='telegram':
                if account.get('source_channel')!=self.data.get('telegram',{}).get('channel'):raise ValueError('Telegram channel changed. Verify it again.')
                caption=data.get('caption','')
                if not isinstance(caption,str) or caption_length(caption)>1024:raise ValueError('Telegram album captions allow 1024 characters (emoji may count as two). Shorten the shared caption before review.')
            job=self.s.draft({'title':data.get('title','Darshan'),'caption':data.get('caption',''),'media':media,'platforms':[platform],
                'publish_at':(now_ist()+timedelta(minutes=5)).isoformat(),'delivery':'manual' if platform=='youtube' else 'api'},_persist=False,studio=True)
            if platform=='instagram':
                self.s.job(job['id'])['studio_instagram']=True
            self.s.job(job['id'])['studio_target']=account.get('id') or self.c.cfg.get('youtube_channel_id','')
            if platform=='telegram':self.s.job(job['id'])['studio_bot_id']=account['bot_id']
            self.data.setdefault('jobs',[]).append(job['id'])
            if _persist:self.s.persist();self.persist()
            return job

    def validate_send(self,job):
        if job['status']!='draft':raise ValueError('Started posts cannot be sent again. Prepare a new review.')
        platform=job['platforms'][0];direct=bool(job.get('studio_instagram'));telegram=bool(job.get('studio_telegram'))
        account=self.accounts.get(platform,{})
        if platform!='youtube' and account.get('status')!='verified':raise ValueError('Verify this destination in Connections first.')
        expected=job.get('studio_target','')
        actual=account.get('id','') if direct or telegram else self.c.cfg.get('facebook_page_id' if platform=='facebook' else 'youtube_channel_id','')
        if expected and expected!=actual:raise ValueError('The destination changed after preview. Prepare a new draft.')
        if telegram and (account.get('source_channel')!=self.data.get('telegram',{}).get('channel') or account.get('bot_id')!=job.get('studio_bot_id')):raise ValueError('Telegram bot or channel changed after preview. Prepare a new draft.')
        if direct and not self.c.vault.get('instagram_imgbb_key'):raise ValueError('Save an ImgBB key for temporary Instagram photo hosting first.')

    def approve_job(self,job):
        job['publish_at']=(now_ist()+timedelta(minutes=5)).isoformat()
        self.s.command({'action':'approve','id':job['id'],'revision':job['revision'],'confirmed':True},studio=True)

    @staticmethod
    def publisher(job):return Telegram if job.get('studio_telegram') else DirectInstagram if job.get('studio_instagram') else Publisher

    def send(self,data):
        with self.c.lock,self.s.lock:
            self.ready();job=self.s.job(data.get('id'))
            if job['id'] not in self.data.get('jobs',[]):raise ValueError('Select a DARSHANFLOW draft.')
            if self.s.busy or self.s.live_blocked():raise ValueError('Wait for the current operation or live session to finish before posting.')
            if job['status']!='draft' or data.get('revision')!=job['revision'] or data.get('confirmed') is not True:raise ValueError('Review this draft before sending it. Started posts cannot be sent again.')
            platform=job['platforms'][0];self.validate_send(job);self.approve_job(job)
            if platform=='youtube':return {'ok':True,'status':'manual_ready'}
            job.update(status='publishing',error='');self.s.persist()
            frozen=copy.deepcopy(job);cfg=copy.deepcopy(self.c.cfg)
            cfg['telegram_channel']=self.data.get('telegram',{}).get('channel','')
            def work():
                try:
                    self.publisher(frozen)(cfg,self.c.vault,self.s,self.s.stop).publish(frozen)
                    with self.s.lock:job['status']='published';self.s.persist()
                except Exception as exc:
                    with self.s.lock:job.update(status='needs_review',error=self.s.safe_failure(exc));self.s.persist()
            self.s.worker=threading.Thread(target=work,daemon=True);self.s.worker.start()
            return {'ok':True,'status':'publishing'}

    def receipt(self,data):
        with self.c.lock,self.s.lock:
            self.ready()
            if data.get('confirmed') is not True:raise ValueError('Confirm completion on the platform first.')
            if data.get('kind')=='youtube':
                job=self.s.job(data.get('id'))
                if job['id'] not in self.data.get('jobs',[]) or job['platforms']!=['youtube'] or job['status']!='manual_ready':raise ValueError('Prepare this YouTube photo handoff first.')
                link=public_link(data.get('url',''),'youtube')
                if not link:raise ValueError('Paste the published YouTube post link.')
                self.s.command({'action':'manual_done','id':job['id'],'revision':job['revision'],'confirmed':True})
                job['results']['youtube']={'status':'manual_done','url':link,'stage':'Confirmed by you'};self.s.persist()
            else:
                index=data.get('index')
                if type(index)!=int or not 0<=index<9:raise ValueError('Choose a community or channel.')
                if data.get('undo') is True:self.data['receipts'].pop(str(index),None)
                else:self.data['receipts'][str(index)]={'at':now_ist().isoformat(),'status':'confirmed_by_you'}
                self.persist()
            return {'ok':True}
