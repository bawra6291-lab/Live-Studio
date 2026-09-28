from __future__ import annotations
import base64, hashlib, json, os, re, socket, time, uuid
from pathlib import Path
from urllib.parse import urlsplit
from datetime import datetime
from core import IST, SLOTS, title_for, atomic_json

class SetupError(RuntimeError):
    def __init__(self, message, *, request_type=None, code=None):
        super().__init__(message)
        self.request_type=request_type
        self.code=code

class Vault:
    SERVICE='ISKCON-Live-Start'
    def __init__(self, service=SERVICE):
        self.SERVICE=service
        import keyring
        self.k=keyring
        # Do not silently use plaintext/fallback storage.
        if os.name!='nt' or 'Windows' not in type(keyring.get_keyring()).__module__:
            raise SetupError('Use this app on Windows with Windows Credential Manager available.')
    def get(self,name): return self.k.get_password(self.SERVICE,name) or ''
    def set(self,name,value):
        if value: self.k.set_password(self.SERVICE,name,value)

class OBS:
    def __init__(self,cfg,vault): self.cfg,self.vault,self.ws=cfg,vault,None
    def close(self):
        if self.ws:
            try:self.ws.close()
            except Exception:pass
            self.ws=None
    def connect(self,launch=False):
        import websocket
        port=int(self.cfg.get('obs_port',4455))
        if launch:
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=1): pass
            except OSError:
                from obs_windows import open_obs, OBSLaunchError
                try: open_obs(self.cfg['obs_exe'], require_window=False)
                except OBSLaunchError as exc: raise SetupError(str(exc)) from None
                for _ in range(25):
                    try:
                        with socket.create_connection(('127.0.0.1',port),timeout=1):break
                    except OSError: time.sleep(1)
                else: raise SetupError('OBS did not open its WebSocket port. Enable WebSocket server in OBS.')
        try:
            self.ws=websocket.create_connection(f'ws://127.0.0.1:{port}',timeout=10,suppress_origin=True)
            hello=json.loads(self.ws.recv())
            if hello.get('op')!=0: raise SetupError('Unexpected OBS handshake.')
            ident={'rpcVersion':1,'eventSubscriptions':0}
            auth=hello['d'].get('authentication')
            if auth:
                pw=self.vault.get('obs_password')
                secret=base64.b64encode(hashlib.sha256((pw+auth['salt']).encode()).digest()).decode()
                ident['authentication']=base64.b64encode(hashlib.sha256((secret+auth['challenge']).encode()).digest()).decode()
            self.ws.send(json.dumps({'op':1,'d':ident}))
            if json.loads(self.ws.recv()).get('op')!=2:raise SetupError('OBS authentication failed.')
        except SetupError: self.close(); raise
        except Exception:
            self.close(); raise SetupError('Cannot connect to OBS. Check WebSocket enable, port 4455 and password locally.') from None
    def call(self,kind,**data):
        if not self.ws:self.connect()
        rid=str(uuid.uuid4())
        try:
            self.ws.send(json.dumps({'op':6,'d':{'requestType':kind,'requestId':rid,'requestData':data}}))
            while True:
                msg=json.loads(self.ws.recv())
                if msg.get('op')==7 and msg['d'].get('requestId')==rid:
                    d=msg['d']
                    if not d['requestStatus']['result']:
                        code=d['requestStatus'].get('code')
                        raise SetupError(f'OBS {kind} failed (code {code}).',request_type=kind,code=code)
                    return d.get('responseData',{})
        except SetupError:raise
        except Exception:
            self.close(); raise SetupError(f'OBS connection interrupted during {kind}. Check OBS before retrying.') from None
    def idle(self):
        for kind in ['GetStreamStatus','GetRecordStatus','GetReplayBufferStatus']:
            try:status=self.call(kind)
            except SetupError as exc:
                # OBS returns InvalidResourceState when no replay buffer output exists.
                # This is optional; do not treat a disabled replay buffer as an active one.
                # All other request errors remain blocking, including 604 on stream/record.
                if kind=='GetReplayBufferStatus' and exc.request_type==kind and exc.code==604:
                    continue
                raise
            if type(status.get('outputActive')) is not bool:
                raise SetupError(f'OBS {kind} returned no valid output status. Check OBS before retrying.')
            if status['outputActive']:raise SetupError('OBS streaming/recording/replay buffer is active. Leave it running; end it manually before a new session.')
        if any(x.get('outputActive') for x in self.call('GetOutputList').get('outputs',[])):
            raise SetupError('An OBS output is active. It will not be interrupted.')
    def profile_file(self):
        name=self.cfg['obs_profile']
        import configparser
        found=[]
        for p in (Path(os.environ['APPDATA'])/'obs-studio/basic/profiles').glob('*/basic.ini'):
            cp=configparser.ConfigParser(strict=False,interpolation=None)
            cp.read(p,encoding='utf-8-sig')
            if cp.get('General','Name',fallback='')==name: found.append(p.parent/'obs-multi-rtmp.json')
        if len(found)!=1:raise SetupError('Cannot identify exactly one OBS profile folder. Standard OBS installation required.')
        return found[0]
    def plugin_target(self):
        p=self.profile_file()
        if not p.exists():raise SetupError('Multiple RTMP plugin configuration is missing for this OBS profile.')
        data=json.loads(p.read_text('utf-8-sig'))
        targets=[x for x in data.get('targets',[]) if x.get('name')==self.cfg['fb_target']]
        if len(targets)!=1 or 'service-param' not in targets[0]:
            raise SetupError('FB Live target/config format not supported. Send the plugin version, not stream keys.')
        return p,data,targets[0]
    def check_profile(self):
        if self.call('GetProfileList')['currentProfileName']!=self.cfg['obs_profile']:
            raise SetupError('OBS current profile differs from the configured profile.')
        if self.call('GetSceneCollectionList')['currentSceneCollectionName']!=self.cfg['obs_collection']:
            raise SetupError('OBS scene collection differs from Temple Live / configured collection.')
        names=[x['sceneName'] for x in self.call('GetSceneList')['scenes']]
        if self.cfg['obs_scene'] not in names:raise SetupError('Configured program scene does not exist.')
    def key(self):
        return self.call('GetStreamServiceSettings')['streamServiceSettings'].get('key','')
    def wait_profile(self,name):
        # CreateProfile queues frontend work: its reply is not proof that the
        # new profile is present/current yet. Never edit an active profile file.
        for _ in range(40):
            state=self.call('GetProfileList')
            if name in state.get('profiles',[]) and state.get('currentProfileName')==name:return
            time.sleep(.25)
        raise SetupError('OBS profile switch was not confirmed within 10 seconds. Check OBS for an open dialog.')
    def prepare_fb_output(self,full_url):
        # The plugin creates its output only on Start. Generic StartOutput cannot replace this.
        # Save an exact backup; switch inactive profiles so the plugin reloads its new key.
        self.idle(); self.check_profile()
        parts=urlsplit(full_url)
        if parts.scheme!='rtmps' or not parts.netloc or '/' not in parts.path.strip('/'):
            raise SetupError('Facebook did not return a supported RTMPS ingest URL.')
        server_path,key=parts.path.rsplit('/',1)
        key += ('?'+parts.query) if parts.query else ''
        server=f'{parts.scheme}://{parts.netloc}{server_path}/'
        path,data,target=self.plugin_target()
        if any(x.get('sync-start') for x in data['targets'] if x['id']!=target['id']):
            raise SetupError('Another Multiple RTMP target has sync-start enabled. Turn it off so FB Backup will not start.')
        service=target['service-param']
        if service.get('server')==server and service.get('key')==key and target.get('sync-start'):
            return
        raw=path.read_bytes()
        backup=path.with_name('obs-multi-rtmp.before-iskcon-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.json')
        backup.write_bytes(raw)
        temp='ISKCON-Reload-'+uuid.uuid4().hex[:8]
        original=self.cfg['obs_profile']
        changed=False;stage='create temporary profile';restored=False
        try:
            self.call('CreateProfile',profileName=temp)
            stage='wait for temporary profile'
            self.wait_profile(temp)
            self.idle()
            # Switching away flushes the plugin's in-memory settings. Back up
            # that freshest version, including any operator changes.
            stage='read FB target'
            raw=path.read_bytes();backup.write_bytes(raw)
            data=json.loads(raw.decode('utf-8-sig'))
            target=next(x for x in data['targets'] if x.get('name')==self.cfg['fb_target'])
            if any(x.get('sync-start') for x in data['targets'] if x['id']!=target['id']):
                raise SetupError('Another Multiple RTMP target has sync-start enabled. Disable it before retrying.')
            target['service-param']['server']=server
            target['service-param']['key']=key
            target['sync-start']=True
            # sync-stop is preserved; v0.3 ending validates and addresses only this run.
            stage='write FB target';changed=True
            atomic_json(path,data)
            stage='restore original profile'
            self.call('SetCurrentProfile',profileName=original)
            self.wait_profile(original)
            self.check_profile()
            stage='verify FB target'
            _,_,loaded=self.plugin_target()
            if loaded['service-param'].get('server')!=server or loaded['service-param'].get('key')!=key or not loaded.get('sync-start'):
                raise SetupError('FB Live settings did not remain saved after the profile reload.')
            stage='remove temporary profile'
            self.idle()
            self.call('RemoveProfile',profileName=temp)
        except Exception as exc:
            # Best effort restore only while inactive; never terminate an active output.
            try:
                self.idle()
                if changed:
                    self.call('SetCurrentProfile',profileName=temp)
                    self.wait_profile(temp)
                    self.idle()
                    path.write_bytes(raw)
                if self.call('GetProfileList').get('currentProfileName')!=original:
                    self.call('SetCurrentProfile',profileName=original)
                self.wait_profile(original)
                self.check_profile();restored=True
            except Exception:pass
            reason=str(exc) if type(exc) is SetupError else type(exc).__name__
            recovery='Original profile restored.' if restored else 'Original profile restore could not be confirmed; select it manually in OBS.'
            raise SetupError(f'FB output reload failed at {stage}: {reason} A local backup was saved. {recovery} No live start was sent.') from None
    def fb_sending(self):
        candidates=[x for x in self.call('GetOutputList').get('outputs',[]) if x.get('outputName','').startswith('multi-output')]
        if len(candidates)!=1:return False
        st=self.call('GetOutputStatus',outputName=candidates[0]['outputName'])
        return st.get('outputActive',False) and not st.get('outputReconnecting',False) and st.get('outputBytes',0)>0
    def start(self):
        self.idle();self.check_profile()
        self.call('SetCurrentProgramScene',sceneName=self.cfg['obs_scene'])
        self.call('StartStream')

class YouTube:
    SCOPES=['https://www.googleapis.com/auth/youtube.force-ssl']
    STREAM_TITLE='YouTube Official Livestream'
    def __init__(self,cfg,vault):self.cfg,self.vault,self.session=cfg,vault,None
    def connect(self,interactive=False):
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request, AuthorizedSession
        saved=self.vault.get('youtube_oauth')
        creds=Credentials.from_authorized_user_info(json.loads(saved),self.SCOPES) if saved else None
        if creds and creds.expired and creds.refresh_token:
            try:creds.refresh(Request())
            except Exception:creds=None
        if not creds or not creds.valid:
            if not interactive:raise SetupError('YouTube login is missing/expired. Use Connect YouTube locally.')
            from google_auth_oauthlib.flow import InstalledAppFlow
            flow=InstalledAppFlow.from_client_secrets_file(self.cfg['google_client_file'],self.SCOPES)
            creds=flow.run_local_server(port=0,access_type='offline',prompt='consent',timeout_seconds=180)
        self.vault.set('youtube_oauth',creds.to_json())
        self.session=AuthorizedSession(creds)
    def api(self,method,resource,params=None,body=None,data=None,content_type=None):
        if not self.session:self.connect()
        prefix='https://www.googleapis.com/upload/youtube/v3/' if data is not None else 'https://www.googleapis.com/youtube/v3/'
        kwargs={'params':params or {},'timeout':30}
        if body is not None:kwargs['json']=body
        if data is not None:kwargs.update(data=data,headers={'Content-Type':content_type or 'image/jpeg'})
        try:
            r=self.session.request(method,prefix+resource,**kwargs)
            out=r.json()
        except Exception:raise SetupError(f'YouTube {resource}: connection/response failed. Check Studio before retrying a write.') from None
        if not r.ok:
            reason=out.get('error',{}).get('errors',[{}])[0].get('reason','request_failed')
            raise SetupError(f'YouTube {resource}: HTTP {r.status_code}, {reason}.')
        return out
    def list(self,resource,max_pages=40,allow_partial=False,**params):
        result=[]
        for _ in range(max_pages):
            page=self.api('GET',resource,params)
            result.extend(page.get('items',[]))
            if not page.get('nextPageToken'):return result
            params['pageToken']=page['nextPageToken']
        if allow_partial:return result
        raise SetupError('Too many YouTube pages to inspect safely.')
    def owned_channel(self):
        mine=self.list('channels',part='id,snippet',mine='true')
        selected=self.cfg.get('youtube_channel_id','')
        if selected:
            channel=next((x for x in mine if x['id']==selected),None)
            if not channel:raise SetupError('Connected YouTube account does not own the configured channel ID. Reconnect the intended channel locally.')
            return channel
        if not self.cfg.get('legacy_setup'):
            raise SetupError('Save your YouTube channel ID in Connections before connecting or enabling automation.')
        refs=self.list('videos',part='snippet',id=','.join(x['reference'] for x in SLOTS))
        ids={x['snippet']['channelId'] for x in refs}
        if len(refs)!=4 or len(ids)!=1:raise SetupError('The four reference videos could not be verified.')
        channel=next((x for x in mine if x['id'] in ids),None)
        if not channel:raise SetupError('Wrong YouTube channel. Connect the ISKCON Kolkata channel that owns the four references.')
        return channel
    def no_other_live(self,allowed=None):
        items=self.list('liveBroadcasts',part='id,status',broadcastStatus='active',broadcastType='all',maxResults=50)
        if any(x['id']!=allowed for x in items):raise SetupError('Another YouTube live is active. End it manually first.')
    def stream_for_obs(self,key):
        if not key:raise SetupError('OBS YouTube stream key could not be read locally.')
        streams=self.list('liveStreams',part='id,snippet,cdn,status',mine='true',maxResults=50)
        matches=[s for s in streams if s['cdn']['ingestionInfo']['streamName']==key]
        if len(matches)!=1:raise SetupError('OBS stream key does not match exactly one reusable stream on the connected YouTube channel.')
        expected=self.cfg.get('youtube_stream_title',self.STREAM_TITLE if self.cfg.get('legacy_setup') else '')
        if not expected:raise SetupError('Save the name of your existing YouTube stream key in Connections.')
        if matches[0].get('snippet',{}).get('title','').strip()!=expected:
            raise SetupError('OBS must use the configured existing YouTube stream key name. Select that same existing key in Studio and OBS; do not create or reset a key.')
        return matches[0]
    def bind_stream(self,event,stream):
        if event['contentDetails'].get('boundStreamId')!=stream['id']:
            self.api('POST','liveBroadcasts/bind',{'id':event['id'],'streamId':stream['id'],'part':'id,contentDetails'})
        verified=self.event(event['id'])
        if verified['contentDetails'].get('boundStreamId')!=stream['id']:
            raise SetupError('YouTube did not confirm the selected stream binding. Inspect Studio before retrying.')
        if verified['status']['privacyStatus']!='public':
            raise SetupError('YouTube API project restricted this broadcast to private. Resolve API access; it has not been made live.')
        return verified
    def video_template(self,source_id,reference_id,title,channel_id):
        # videos.update requires BOTH title and categoryId, even for a live video.
        # Resolve these before inserting a broadcast so an incomplete template
        # cannot leave a new, unusable schedule behind.
        def snippet(video_id):
            items=self.list('videos',part='snippet',id=video_id)
            if len(items)!=1 or items[0].get('id')!=video_id:
                raise SetupError('YouTube metadata source is unavailable. Check the previous/reference video in Studio.')
            value=items[0].get('snippet',{})
            if value.get('channelId')!=channel_id:
                raise SetupError('YouTube metadata source belongs to another channel.')
            return value
        original=snippet(source_id)
        category=original.get('categoryId')
        if not category and reference_id!=source_id:
            category=snippet(reference_id).get('categoryId')
        if not isinstance(category,str) or not re.fullmatch(r'[1-9][0-9]*',category):
            raise SetupError('YouTube category is missing/invalid in the video template. Set Category on the previous/reference video in YouTube Studio, then retry after review. No new broadcast was created.')
        if not isinstance(title,str) or not title.strip() or len(title)>100:
            raise SetupError('YouTube metadata needs a non-empty title of at most 100 characters.')
        # Copy the documented videos.update snippet fields only. In particular,
        # do not replay defaultAudioLanguage or empty optional language values
        # from an older video's response into a new broadcast.
        metadata={k:v for k,v in original.items() if k in ('description','tags') and v is not None}
        language=original.get('defaultLanguage')
        if isinstance(language,str) and language.strip():metadata['defaultLanguage']=language.strip()
        metadata.update(title=title,categoryId=category)
        return original,metadata
    def prepare(self,slot,due,obs_key,persist):
        channel=self.owned_channel();self.no_other_live()
        previous=[] if slot.get('title_template') else self.list('liveBroadcasts',part='id,snippet,status,contentDetails',broadcastStatus='completed',broadcastType='all',maxResults=50,max_pages=4,allow_partial=True)
        previous=[x for x in previous if slot['name'].casefold() in x['snippet']['title'].casefold() and x['snippet']['channelId']==channel['id']]
        previous.sort(key=lambda x:x['snippet'].get('actualStartTime',x['snippet'].get('publishedAt','')),reverse=True)
        if previous: source=previous[0]
        else:
            refs=self.list('liveBroadcasts',part='id,snippet,status,contentDetails',id=slot['reference'])
            if len(refs)!=1:raise SetupError('Previous live settings unavailable through the connected account.')
            source=refs[0]
        if source['snippet'].get('channelId')!=channel['id']:raise SetupError('Reference livestream belongs to another channel.')
        title=title_for(source['snippet']['title'],slot,due.date())
        stream=self.stream_for_obs(obs_key)
        upcoming=self.list('liveBroadcasts',part='id,snippet,status,contentDetails',broadcastStatus='upcoming',broadcastType='all',maxResults=50)
        matches=[x for x in upcoming if x['snippet']['title']==title]
        if len(matches)>1:raise SetupError('Duplicate YouTube schedules already exist for this title. Resolve them manually.')
        if matches:
            event=matches[0];details=event['contentDetails']
            scheduled=datetime.fromisoformat(event['snippet']['scheduledStartTime'].replace('Z','+00:00'))
            if abs((scheduled-due).total_seconds())>60:raise SetupError('Existing YouTube schedule has a different start time; review it in Studio.')
            if details.get('enableAutoStop') or details.get('enableAutoStart'):
                raise SetupError('Existing schedule has auto-start/auto-stop enabled. Disable both in Studio, then retry.')
            if details.get('monitorStream',{}).get('enableMonitorStream',True):
                raise SetupError('Existing schedule requires testing mode. Disable its monitor stream or create the schedule with this app.')
            if event['status']['privacyStatus']!='public':raise SetupError('Existing schedule is not public; check Studio.')
            if details.get('boundStreamId') not in (None,'',stream['id']):raise SetupError('Existing YouTube schedule uses another stream key.')
        else:
            original,metadata=self.video_template(source['id'],slot['reference'],title,channel['id'])
            details={k:v for k,v in source.get('contentDetails',{}).items() if k in ('enableDvr','recordFromStart','enableEmbed','enableClosedCaptions','closedCaptionsType','latencyPreference','projection')}
            details.update(enableAutoStart=False,enableAutoStop=False,monitorStream={'enableMonitorStream':False,'broadcastStreamDelayMs':0})
            status={'privacyStatus':'public','selfDeclaredMadeForKids':source['status'].get('selfDeclaredMadeForKids',source['status'].get('madeForKids',False))}
            event=self.api('POST','liveBroadcasts',{'part':'snippet,status,contentDetails'},body={
                'snippet':{'title':title,'description':source['snippet'].get('description',''),'scheduledStartTime':due.isoformat()},
                'status':status,'contentDetails':details})
            persist(yt_id=event['id'],title=title,yt_stream_id=stream['id'],stage='youtube_bind')
            event=self.bind_stream(event,stream)
            persist(stage='youtube_metadata')
            # Copy video metadata and the previous thumbnail; no new artwork or local thumbnail folder.
            try:
                self.api('PUT','videos',{'part':'snippet'},body={'id':event['id'],'snippet':metadata})
            except SetupError as exc:
                raise SetupError(str(exc)+' Broadcast retained for review in YouTube Studio; title and categoryId were included. No automatic retry was sent.') from None
            thumbs=original.get('thumbnails',{})
            thumb=next((thumbs[k]['url'] for k in ('maxres','standard','high','medium','default') if k in thumbs),None)
            if not thumb:raise SetupError('Previous thumbnail could not be found. New broadcast retained for manual review.')
            # Download without OAuth headers, and only from YouTube image hosts.
            import requests
            host=urlsplit(thumb).hostname or ''
            if not (host.endswith('.ytimg.com') or host=='ytimg.com'):raise SetupError('Unexpected YouTube thumbnail host.')
            try:
                r=requests.get(thumb,timeout=25);r.raise_for_status()
            except Exception:raise SetupError('Previous thumbnail download failed.') from None
            if len(r.content)>2*1024*1024:raise SetupError('Previous thumbnail exceeds YouTube upload limit.')
            self.api('POST','thumbnails/set',{'videoId':event['id'],'uploadType':'media'},data=r.content,content_type=r.headers.get('Content-Type','image/jpeg'))
        persist(yt_id=event['id'],title=title)
        self.bind_stream(event,stream)
        return {'yt_id':event['id'],'yt_stream_id':stream['id'],'title':title}
    def event(self,id):
        out=self.list('liveBroadcasts',part='id,status,contentDetails,snippet',id=id)
        if len(out)!=1:raise SetupError('YouTube broadcast no longer exists.')
        return out[0]
    def stream_active(self,id):
        items=self.list('liveStreams',part='status',id=id)
        return bool(items and items[0]['status']['streamStatus']=='active')
    def live(self,id):return self.event(id)['status']['lifeCycleStatus']=='live'
    def go(self,id):self.api('POST','liveBroadcasts/transition',{'id':id,'broadcastStatus':'live','part':'id,status'})

class Facebook:
    def __init__(self,cfg,vault):self.cfg,self.vault=cfg,vault
    @property
    def PAGE(self):
        page=self.cfg.get('facebook_page_id','')
        if not re.fullmatch(r'[0-9]{5,30}',page):raise SetupError('Save the target Facebook Page ID in Connections.')
        return page
    def api(self,method,path,params=None):
        import requests
        version=self.cfg.get('graph_version','v23.0')
        if not re.fullmatch(r'v\d+\.0',version):raise SetupError('Invalid Graph API version.')
        token=self.vault.get('facebook_page_token')
        if not token:raise SetupError('Facebook Page access token missing. It must be configured locally.')
        try:
            r=requests.request(method,f'https://graph.facebook.com/{version}/{path}',
                headers={'Authorization':'Bearer '+token},
                **({'params':params or {}} if method=='GET' else {'data':params or {}}),timeout=30)
            out=r.json()
        except Exception:raise SetupError('Facebook connection/response failed. Check Live Producer before retrying a write.') from None
        if not r.ok or 'error' in out:
            err=out.get('error',{})
            raise SetupError(f'Facebook API denied/failed request (code {err.get("code",r.status_code)}, subcode {err.get("error_subcode",0)}). Check Page token, live eligibility and app permissions.')
        return out
    def identity(self):
        page=self.PAGE
        me=self.api('GET','me',{'fields':'id,name'})
        if me.get('id')!=page:raise SetupError('Facebook token does not match the configured Page ID. Use that Page’s token; browser login is not API authorization.')
        return me
    def recent(self):
        # Bounded to the last 100 sessions; no writes use untrusted pagination URLs.
        return self.api('GET',self.PAGE+'/live_videos',{'fields':'id,title,status,creation_time','limit':100})['data']
    def no_other_live(self,allowed=None):
        if any(x.get('status') in ('LIVE','LIVE_NOW') and x['id']!=allowed for x in self.recent()):
            raise SetupError('Another Facebook live is active. End it manually first.')
    def prepare(self,title,persist):
        self.identity();self.no_other_live()
        matches=[x for x in self.recent() if x.get('title')==title and x.get('status') in ('UNPUBLISHED','SCHEDULED_UNPUBLISHED','SCHEDULED_LIVE')]
        if len(matches)>1:raise SetupError('Multiple matching Facebook drafts exist. Resolve them in Live Producer.')
        if matches:
            event=matches[0]
            if event['status']!='UNPUBLISHED':raise SetupError('An existing Facebook event is scheduled. Use an unpublished draft for this app; it will not duplicate it.')
        else:
            event=self.api('POST',self.PAGE+'/live_videos',{'title':title,'description':'','status':'UNPUBLISHED','stream_type':'REGULAR'})
        persist(fb_id=event['id'])
        self.api('POST',event['id'],{'title':title,'is_manual_mode':'true'})
        detail=self.api('GET',event['id'],{'fields':'id,status,secure_stream_url'})
        if not detail.get('secure_stream_url'):raise SetupError('Facebook did not return an ingest URL for this draft.')
        return event['id'],detail['secure_stream_url']
    def live(self,id):return self.api('GET',id,{'fields':'status'}).get('status') in ('LIVE','LIVE_NOW')
    def go(self,id):self.api('POST',id,{'status':'LIVE_NOW'})

class Camera:
    def __init__(self,cfg,vault):self.cfg,self.vault=cfg,vault
    @property
    def channel(self):
        value=self.cfg.get('camera_channel','1')
        if not re.fullmatch(r'[1-9][0-9]?',str(value)):raise SetupError('Invalid camera channel.')
        return str(value)
    def request(self,method,path):
        import requests
        from requests.auth import HTTPDigestAuth
        base=self.cfg.get('camera_url','http://192.168.29.10').rstrip('/')
        u=urlsplit(base)
        if u.scheme not in ('http','https') or u.username or u.password or u.path not in ('','/'):
            raise SetupError('Use the camera base address without username/password or page path.')
        try:
            r=requests.request(method,base+path,auth=HTTPDigestAuth(self.cfg.get('camera_user','admin'),self.vault.get('camera_password')),timeout=12)
        except Exception:raise SetupError('Camera is unreachable from this PC.') from None
        if not r.ok:raise SetupError(f'Camera request returned HTTP {r.status_code}; check credentials and ISAPI permission.')
        import xml.etree.ElementTree as ET
        try:root=ET.fromstring(r.content)
        except Exception:raise SetupError('Camera did not return ISAPI XML; firmware endpoint must be checked.') from None
        codes=[e.text for e in root.iter() if e.tag.split('}')[-1]=='statusCode']
        if codes and any(c!='1' for c in codes):raise SetupError('Camera did not acknowledge this ISAPI command.')
        return root
    def check(self):
        self.request('GET','/ISAPI/System/deviceInfo')
        root=self.request('GET',f'/ISAPI/PTZCtrl/channels/{self.channel}/patrols/8')
        if not any(e.tag.split('}')[-1]=='id' and e.text=='8' for e in root.iter()):raise SetupError('Patrol 8 could not be verified on the configured channel.')
    def start(self):self.action({'kind':'patrol_start','number':8})
    def check_action(self,action):
        number=action['number'];kind=action['kind']
        if kind=='preset':
            if type(number)!=int or not 1<=number<=32:raise SetupError('Use an ordinary preset 1–32, not a special camera command.')
            root=self.request('GET',f'/ISAPI/PTZCtrl/channels/{self.channel}/presets')
        else:
            if type(number)!=int or not 1<=number<=8:raise SetupError('Patrol must be 1–8.')
            root=self.request('GET',f'/ISAPI/PTZCtrl/channels/{self.channel}/patrols/{number}')
        if not any(e.tag.split('}')[-1]=='id' and e.text==str(number) for e in root.iter()):
            raise SetupError(f'Camera {kind} {number} is not configured on the configured channel.')
    def action(self,action):
        self.check_action(action);number=action['number'];kind=action['kind']
        suffix={'patrol_start':f'patrols/{number}/start','patrol_stop':f'patrols/{number}/stop','preset':f'presets/{number}/goto'}.get(kind)
        if not suffix:raise SetupError('Unsupported camera action.')
        self.request('PUT',f'/ISAPI/PTZCtrl/channels/{self.channel}/'+suffix)

class Services:
    def __init__(self,cfg,vault,log=print):
        self.cfg,self.log=cfg,log
        self.persist_run=lambda **kw: None
        self.obs=OBS(cfg,vault);self.yt=YouTube(cfg,vault);self.fb=Facebook(cfg,vault);self.cam=Camera(cfg,vault)
    def check(self):
        self.obs.connect(launch=True);self.obs.check_profile();self.obs.plugin_target()
        self.log('OBS connected. Program scene: '+self.cfg['obs_scene'])
        channel=self.yt.owned_channel();self.log('YouTube channel verified: '+channel['snippet']['title'])
        self.yt.stream_for_obs(self.obs.key())
        page=self.fb.identity();self.fb.recent();self.log('Facebook Page verified: '+page['name'])
        from schedule_config import get_schedule
        actions=[a for slot in get_schedule(self.cfg) if slot['enabled'] for a in slot['camera_actions']]
        checked=set()
        for action in actions:
            key=('preset' if action['kind']=='preset' else 'patrol',action['number'])
            if key not in checked:self.cam.check_action(action);checked.add(key)
        self.log('Camera reachable; configured camera actions checked. No movement requested.' if actions else 'Camera skipped; no scheduled camera actions enabled.')
        self.log('Read-only checks passed. Live-start and locked-PC capture still require a supervised test.')
    def prepare(self,slot,due,persist):
        self.obs.close();self.obs.connect(launch=True);self.obs.idle();self.obs.check_profile()
        # Verify both destinations and camera BEFORE any new broadcast is created.
        self.fb.identity();self.fb.no_other_live()
        for action in slot.get('camera_actions',[]):self.cam.check_action(action)
        record=self.yt.prepare(slot,due,self.obs.key(),persist)
        fb_id,url=self.fb.prepare(record['title'],persist)
        self.obs.prepare_fb_output(url)
        record['fb_id']=fb_id
        return record
    def start(self,record):
        self.obs.idle();self.obs.check_profile()
        self.yt.no_other_live();self.fb.no_other_live()
        # Verify that the reusable stream key has not been changed since preparation.
        if self.yt.stream_for_obs(self.obs.key())['id']!=record['yt_stream_id']:
            raise SetupError('OBS stream key changed after preparation.')
        event=self.yt.event(record['yt_id'])
        if event['contentDetails'].get('boundStreamId')!=record['yt_stream_id']:
            raise SetupError('YouTube broadcast stream binding changed after preparation. Select the configured existing stream in Studio; no OBS start was sent.')
        self.obs.start()
        status=self.obs.call('GetStreamStatus')
        self.persist_run(obs_start_epoch=time.time()-status.get('outputDuration',0)/1000,stage='waiting_for_ingest')
        # OBS sync-start starts the configured FB target; don't address its temporary output by name.
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            if self.yt.stream_active(record['yt_stream_id']) and self.obs.fb_sending():
                candidates=[x for x in self.obs.call('GetOutputList').get('outputs',[]) if x.get('outputName','').startswith('multi-output')]
                if len(candidates)!=1:raise SetupError('Cannot capture exactly one Facebook output for this run.')
                name=candidates[0]['outputName'];st=self.obs.call('GetOutputStatus',outputName=name)
                target=self.obs.plugin_target()[2]
                fingerprint=hashlib.sha256(json.dumps(target['service-param'],sort_keys=True).encode()).hexdigest()
                main_status=self.obs.call('GetStreamStatus')
                self.persist_run(obs_start_epoch=time.time()-main_status.get('outputDuration',0)/1000,fb_output_name=name,fb_start_epoch=time.time()-st.get('outputDuration',0)/1000,fb_target_fingerprint=fingerprint,stage='publishing_live')
                break
            time.sleep(2)
        else:raise SetupError('YouTube ingest and FB output sending were not both confirmed within 90 seconds.')
        self.yt.go(record['yt_id'])
        self.fb.go(record['fb_id'])
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            if self.both_live(record):return
            time.sleep(3)
        raise SetupError('Could not confirm BOTH platforms live. Check both dashboards; do not assume success.')
    def both_live(self,record):return self.yt.live(record['yt_id']) and self.fb.live(record['fb_id'])
    def camera_start(self):self.cam.start()
    def camera_action(self,action):self.cam.action(action)
    def close(self):self.obs.close()
    def verify_run_outputs(self,record):
        self.obs.close();self.obs.connect();self.obs.check_profile()
        if self.yt.stream_for_obs(self.obs.key())['id']!=record['yt_stream_id']:
            raise SetupError('OBS stream key changed. Automatic ending refused.')
        target=self.obs.plugin_target()[2]
        fingerprint=hashlib.sha256(json.dumps(target['service-param'],sort_keys=True).encode()).hexdigest()
        if fingerprint!=record.get('fb_target_fingerprint'):
            raise SetupError('Facebook output settings changed. Automatic ending refused.')
        outputs=self.obs.call('GetOutputList').get('outputs',[])
        others=[x for x in outputs if x.get('outputActive') and x.get('outputName','').startswith('multi-output') and x.get('outputName')!=record.get('fb_output_name')]
        if others:raise SetupError('Another Facebook/plugin output is active. Automatic OBS ending refused.')
        main=self.obs.call('GetStreamStatus')
        self.check_output_epoch(main,record.get('obs_start_epoch'))
        fb=next((x for x in outputs if x.get('outputName')==record.get('fb_output_name')),None)
        if fb:
            status=self.obs.call('GetOutputStatus',outputName=record['fb_output_name'])
            self.check_output_epoch(status,record.get('fb_start_epoch'))
        return main,fb
    @staticmethod
    def check_output_epoch(status,expected):
        if not status.get('outputActive'):return
        if expected is None or 'outputDuration' not in status or abs(time.time()-status['outputDuration']/1000-expected)>2:
            raise SetupError('OBS output was restarted or its identity cannot be verified. End manually.')
    def end(self,record,persist):
        # Exact recorded IDs only. Never address whichever broadcast happens to be live.
        if not record.get('plan',{}).get('end_at'):raise SetupError('No scheduled end is authorized for this run.')
        self.fb.identity();self.yt.owned_channel()
        self.yt.no_other_live(record['yt_id']);self.fb.no_other_live(record['fb_id'])
        event=self.yt.event(record['yt_id'])
        if event['contentDetails'].get('boundStreamId')!=record['yt_stream_id']:
            raise SetupError('YouTube broadcast binding changed. End manually.')
        if not any(x['id']==record['fb_id'] for x in self.fb.recent()):
            raise SetupError('Recorded Facebook video could not be verified on this Page.')
        self.verify_run_outputs(record)
        if self.yt.live(record['yt_id']):
            self.yt.api('POST','liveBroadcasts/transition',{'id':record['yt_id'],'broadcastStatus':'complete','part':'id,status'})
        persist(yt_end_requested=True)
        if self.fb.live(record['fb_id']):self.fb.api('POST',record['fb_id'],{'end_live_video':'true'})
        persist(fb_end_requested=True)
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            yt_status=self.yt.event(record['yt_id'])['status']['lifeCycleStatus']
            fb_status=self.fb.api('GET',record['fb_id'],{'fields':'status'}).get('status')
            if yt_status=='complete' and fb_status in ('VOD','PROCESSING'):
                break
            time.sleep(1)
        else:raise SetupError('Platform end was not confirmed on both destinations. Inspect them manually.')
        # Check again after network waits so a manual restart cannot be stopped silently.
        main,fb=self.verify_run_outputs(record)
        if fb and self.obs.call('GetOutputStatus',outputName=record['fb_output_name']).get('outputActive'):
            self.obs.call('StopOutput',outputName=record['fb_output_name'])
        main=self.obs.call('GetStreamStatus');self.check_output_epoch(main,record.get('obs_start_epoch'))
        if main.get('outputActive'):self.obs.call('StopStream')
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            main_active=self.obs.call('GetStreamStatus').get('outputActive')
            outputs=self.obs.call('GetOutputList').get('outputs',[])
            fb_active=any(x.get('outputName')==record.get('fb_output_name') and x.get('outputActive') for x in outputs)
            if not main_active and not fb_active:return
            time.sleep(1)
        raise SetupError('OBS did not confirm that this run stopped. Check OBS manually.')
