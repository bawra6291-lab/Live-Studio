"""Official platform posting adapters. No live broadcast, OBS or camera writes."""
import hashlib, json, re, secrets, time
from urllib.parse import urlsplit
from connections import Facebook, YouTube, SetupError
from social import https_media


class Publisher:
    def __init__(self,cfg,vault,manager,stop):
        self.cfg=cfg;self.vault=vault;self.manager=manager;self.stop=stop
        self.fb=Facebook(cfg,vault);self.yt=YouTube(cfg,vault)

    def cancelled(self):
        if self.stop.is_set() or self.manager.live_blocked():raise SetupError('Posting interrupted for shutdown or live preparation. Inspect the platform; this item will not be repeated automatically.',retryable=False)

    def check(self,instagram_id=''):
        result={}
        if self.cfg.get('facebook_page_id'):
            page=self.fb.identity();result['facebook']={'id':page['id'],'name':page.get('name','Facebook Page')}
            try:linked=self.fb.api('GET',self.fb.PAGE,{'fields':'instagram_business_account{id,username}'})
            except SetupError:
                if instagram_id:raise
                linked={}
            if linked.get('instagram_business_account') or instagram_id:
                ig=linked.get('instagram_business_account',{})
                if instagram_id and ig.get('id')!=instagram_id:raise SetupError('Instagram account is not linked to the selected Facebook Page.',retryable=False)
                result['instagram']={'id':ig['id'],'name':ig.get('username','Instagram professional account')}
        if self.cfg.get('youtube_channel_id') or self.cfg.get('legacy_setup'):
            self.yt.connect();channel=self.yt.owned_channel();result['youtube']={'id':channel['id'],'name':channel['snippet']['title']}
        if not result:raise SetupError('Save your Facebook Page and/or YouTube channel in Connections first.',retryable=False)
        return result

    def graph(self,method,path,values=None,file=None,video=False):
        import requests
        token=self.vault.get('facebook_page_token');version=self.cfg.get('graph_version','v23.0')
        if not token or not re.fullmatch(r'v\d+\.0',version):raise SetupError('Save a valid Page token and Graph API version in Connections.',retryable=False)
        host='graph-video.facebook.com' if video else 'graph.facebook.com'
        headers={'Authorization':'Bearer '+token};kwargs={'timeout':(10,90),'allow_redirects':False}
        if file:
            with file.open('rb') as f:is_png=f.read(8)==b'\x89PNG\r\n\x1a\n'
            boundary='LiveDesk'+secrets.token_hex(16);before=b''
            for key,value in (values or {}).items():
                before+=('--'+boundary+'\r\nContent-Disposition: form-data; name="'+key+'"\r\n\r\n'+str(value)+'\r\n').encode('utf-8')
            before+=('--'+boundary+'\r\nContent-Disposition: form-data; name="source"; filename="media'+('.mp4' if video else '.png' if is_png else '.jpg')+'"\r\nContent-Type: '+('video/mp4' if video else 'image/png' if is_png else 'image/jpeg')+'\r\n\r\n').encode()
            after=('\r\n--'+boundary+'--\r\n').encode()
            length=len(before)+file.stat().st_size+len(after)
            headers.update({'Content-Type':'multipart/form-data; boundary='+boundary,'Content-Length':str(length)})
            def stream():
                yield before
                with file.open('rb') as f:
                    for chunk in iter(lambda:f.read(512*1024),b''):
                        self.cancelled();yield chunk
                yield after
            class UploadBody:
                def __len__(self):return length
                def __iter__(self):return stream()
            kwargs['data']=UploadBody()
        else:kwargs['params' if method=='GET' else 'data']=values or {}
        try:
            r=requests.request(method,'https://'+host+'/'+version+'/'+path,headers=headers,**kwargs);out=r.json()
        except SetupError:raise
        except Exception:raise SetupError('Meta request outcome is uncertain. Inspect the Page/Instagram before creating another post.',retryable=False) from None
        if not r.ok or 'error' in out:
            code=out.get('error',{}).get('code','request_failed')
            raise SetupError('Meta posting failed (code '+str(code)+'). Check Page/Instagram permissions and inspect the platform before retrying.',retryable=False)
        return out

    def review_existing(self,job,platform,ident):
        if platform=='facebook':
            self.fb.identity();detail=self.fb.api('GET',ident,{'fields':'id,from'})
            if detail.get('from',{}).get('id')!=job['targets'][platform]:raise SetupError('That Facebook post does not belong to the approved Page.',retryable=False)
            return {'id':detail['id'],'url':'https://www.facebook.com/'+detail['id']}
        if platform=='youtube':
            self.yt.connect();channel=self.yt.owned_channel()
            if channel['id']!=job['targets'][platform]:raise SetupError('Wrong YouTube channel.',retryable=False)
            rows=self.yt.api('GET','videos',{'part':'snippet,status','id':ident}).get('items',[])
            if not rows or rows[0].get('snippet',{}).get('channelId')!=channel['id']:raise SetupError('That video does not belong to the approved channel.',retryable=False)
            if rows[0].get('status',{}).get('privacyStatus')!=job['privacy']:raise SetupError('This video has a different visibility. Review it in Studio before marking this post complete.',retryable=False)
            return {'id':ident,'url':'https://www.youtube.com/watch?v='+ident}
        self.fb.identity();linked=self.fb.api('GET',self.fb.PAGE,{'fields':'instagram_business_account'})
        if linked.get('instagram_business_account',{}).get('id')!=job['targets'][platform]:raise SetupError('Wrong linked Instagram account.',retryable=False)
        rows=self.graph('GET',job['targets'][platform]+'/media',{'fields':'id,permalink','limit':100}).get('data',[])
        item=next((x for x in rows if x['id']==ident),None)
        if not item:raise SetupError('That post was not found in the approved Instagram account’s latest 100 posts.',retryable=False)
        return {'id':ident,'url':item.get('permalink','')}

    def checkpoint(self,job,platform,**values):self.manager.checkpoint(job['id'],platform,**values)

    def verify_media(self,job):
        for ident in job['media']:
            path,_=self.manager.media_path(ident);digest=hashlib.sha256()
            with path.open('rb') as f:
                for b in iter(lambda:f.read(512*1024),b''):digest.update(b)
            if digest.hexdigest()!=ident:raise SetupError('Saved post media changed or is damaged. Import a fresh copy and approve a new draft.',retryable=False)

    def publish(self,job):
        if job.get('delivery','api')!='api':raise SetupError('Manual photo handoffs cannot be sent through a posting API.',retryable=False)
        self.cancelled();self.verify_media(job)
        # Verify all selected accounts before the first platform write.
        if any(p in job['platforms'] for p in ('facebook','instagram')):
            if self.fb.identity()['id']!=self.cfg['facebook_page_id']:raise SetupError('Wrong Facebook Page token.',retryable=False)
        if 'instagram' in job['platforms']:
            linked=self.fb.api('GET',self.fb.PAGE,{'fields':'instagram_business_account'})
            if linked.get('instagram_business_account',{}).get('id')!=job['targets']['instagram']:raise SetupError('The approved Instagram account is no longer linked to this Page.',retryable=False)
        if 'youtube' in job['platforms']:
            self.yt.connect()
            if self.yt.owned_channel()['id']!=job['targets']['youtube']:raise SetupError('YouTube login does not own the approved channel.',retryable=False)
        for platform in job['platforms']:
            self.cancelled()
            if job.get('results',{}).get(platform,{}).get('status')=='published':continue
            getattr(self,'post_'+platform)(job)

    def post_facebook(self,job):
        caption=job['caption'];assets=[self.manager.media_path(m) for m in job['media']]
        self.checkpoint(job,'facebook',status='sending',stage='Creating Page post')
        if not assets:
            result=self.graph('POST',self.fb.PAGE+'/feed',{'message':caption})
        elif assets[0][1]['type'].startswith('video/'):
            result=self.graph('POST',self.fb.PAGE+'/videos',{'title':job['title'],'description':caption},file=assets[0][0],video=True)
        elif len(assets)==1:
            result=self.graph('POST',self.fb.PAGE+'/photos',{'caption':caption,'published':'true'},file=assets[0][0])
        else:
            attached=[]
            for index,(path,asset) in enumerate(assets):
                self.cancelled();self.checkpoint(job,'facebook',stage='Uploading photo '+str(index+1))
                photo=self.graph('POST',self.fb.PAGE+'/photos',{'published':'false'},file=path)
                attached.append({'media_fbid':photo['id']});self.checkpoint(job,'facebook',photo_ids=[x['media_fbid'] for x in attached])
            self.cancelled();self.checkpoint(job,'facebook',stage='Publishing photo collection')
            result=self.graph('POST',self.fb.PAGE+'/feed',{'message':caption,'attached_media':json.dumps(attached)})
        ident=result.get('post_id') or result.get('id')
        if not ident:raise SetupError('Facebook did not return a post ID. Inspect the Page; do not repeat the post.',retryable=False)
        self.checkpoint(job,'facebook',status='published',stage='Posted',id=ident,url='https://www.facebook.com/'+ident)

    def instagram_source(self,job,ident):
        path,asset=self.manager.media_path(ident)
        if asset['type'].startswith('video/') and asset.get('public_url'):return https_media(asset['public_url'])
        if asset['type']!='image/jpeg':raise SetupError('Instagram video needs a public HTTPS media URL.',retryable=False)
        self.checkpoint(job,'instagram',status='sending',stage='Hosting JPG as an unpublished Page photo')
        photo=self.graph('POST',self.fb.PAGE+'/photos',{'published':'false'},file=path)
        prior=self.manager.job(job['id'])['results'].get('instagram',{}).get('host_photo_ids',[])
        self.checkpoint(job,'instagram',host_photo_ids=prior+[photo['id']])
        detail=self.graph('GET',photo['id'],{'fields':'images'})
        images=detail.get('images',[])
        if not images:raise SetupError('Meta did not return a fetchable JPG address. Add a public media URL and approve a fresh draft.',retryable=False)
        url=sorted(images,key=lambda x:x.get('width',0)*x.get('height',0),reverse=True)[0].get('source','')
        parsed=urlsplit(https_media(url))
        if not (parsed.hostname.endswith('.fbcdn.net') or parsed.hostname.endswith('.facebook.com')):raise SetupError('Unexpected Meta media host.',retryable=False)
        return url

    def post_instagram(self,job):
        ig=job['targets']['instagram'];containers=[]
        for ident in job['media']:
            self.cancelled();_,asset=self.manager.media_path(ident);source=self.instagram_source(job,ident)
            values={'video_url':source,'media_type':'REELS','share_to_feed':'true'} if asset['type'].startswith('video/') else {'image_url':source}
            if len(job['media'])>1:values['is_carousel_item']='true'
            else:values['caption']=job['caption']
            self.checkpoint(job,'instagram',status='sending',stage='Preparing Instagram container')
            container=self.graph('POST',ig+'/media',values)['id'];containers.append(container)
            self.checkpoint(job,'instagram',container_ids=containers)
            self.wait_container(container)
        if len(containers)>1:
            self.checkpoint(job,'instagram',stage='Preparing carousel')
            container=self.graph('POST',ig+'/media',{'media_type':'CAROUSEL','children':','.join(containers),'caption':job['caption']})['id']
            self.checkpoint(job,'instagram',carousel_id=container);self.wait_container(container)
        else:container=containers[0]
        self.cancelled();self.checkpoint(job,'instagram',stage='Publishing Instagram post')
        result=self.graph('POST',ig+'/media_publish',{'creation_id':container});ident=result['id']
        # Persist success before an optional permalink read; a failed read is not
        # evidence that the successful publishing request failed.
        self.checkpoint(job,'instagram',status='published',stage='Posted',id=ident,url='')
        try:
            detail=self.graph('GET',ident,{'fields':'permalink'});url=detail.get('permalink','')
            if url.startswith('https://www.instagram.com/'):self.checkpoint(job,'instagram',url=url)
        except SetupError:pass

    def wait_container(self,ident):
        for _ in range(36):
            self.cancelled();state=self.graph('GET',ident,{'fields':'status_code'}).get('status_code')
            if state=='FINISHED':return
            if state in ('ERROR','EXPIRED'):raise SetupError('Instagram rejected the media container. Inspect its size/format and approve a corrected draft.',retryable=False)
            if self.stop.wait(5):self.cancelled()
        raise SetupError('Instagram processing is still pending. Inspect it before creating another post.',retryable=False)

    def post_youtube(self,job):
        path,asset=self.manager.media_path(job['media'][0]);total=asset['size']
        self.checkpoint(job,'youtube',status='sending',stage='Starting video upload')
        metadata={'snippet':{'title':job['title'],'description':job['caption'],'categoryId':'22'},'status':{'privacyStatus':job['privacy'],'selfDeclaredMadeForKids':job['made_for_kids']}}
        try:
            response=self.yt.session.post('https://www.googleapis.com/upload/youtube/v3/videos',params={'uploadType':'resumable','part':'snippet,status','notifySubscribers':'false'},json=metadata,headers={'X-Upload-Content-Length':str(total),'X-Upload-Content-Type':'video/mp4'},timeout=30,allow_redirects=False)
            if response.status_code not in (200,201):raise SetupError('YouTube rejected upload preparation. Check permissions, quota and video metadata.',retryable=False)
            url=response.headers.get('Location','');p=urlsplit(url)
            if p.scheme!='https' or p.netloc!='www.googleapis.com' or p.path!='/upload/youtube/v3/videos':raise SetupError('YouTube returned an unexpected upload address.',retryable=False)
            # Upload session is kept only in memory, never browser state or logs.
            offset=0
            with path.open('rb') as f:
                while offset<total:
                    self.cancelled();chunk=f.read(4*1024*1024);end=offset+len(chunk)-1
                    self.checkpoint(job,'youtube',stage='Uploading video',percent=round(offset*100/total))
                    response=self.yt.session.put(url,data=chunk,headers={'Content-Type':'video/mp4','Content-Length':str(len(chunk)),'Content-Range':f'bytes {offset}-{end}/{total}'},timeout=(10,90),allow_redirects=False)
                    if response.status_code==308:
                        acknowledged=response.headers.get('Range','');match=re.fullmatch(r'bytes=0-(\d+)',acknowledged)
                        if not match or int(match[1])!=end:raise SetupError('YouTube upload acknowledgement changed. Inspect the upload before retrying.',retryable=False)
                        offset=end+1;continue
                    if response.status_code in (200,201):
                        body=response.json();ident=body.get('id','')
                        if not re.fullmatch(r'[A-Za-z0-9_-]{11}',ident):raise SetupError('YouTube returned no usable video ID. Inspect Studio before retrying.',retryable=False)
                        actual=body.get('status',{}).get('privacyStatus')
                        self.checkpoint(job,'youtube',status='published' if actual==job['privacy'] else 'uploaded',stage='Uploaded; YouTube may still be processing' if actual==job['privacy'] else 'Uploaded with different/unknown visibility; inspect Studio',percent=100,id=ident,url='https://www.youtube.com/watch?v='+ident,visibility=actual or 'unknown')
                        if actual!=job['privacy']:raise SetupError('YouTube did not confirm the requested visibility. The video ID is retained; inspect Studio and app audit restrictions before retrying.',retryable=False)
                        return
                    raise SetupError('YouTube upload did not complete. Inspect Studio; this item will not be uploaded again automatically.',retryable=False)
            raise SetupError('YouTube upload outcome is pending. Inspect Studio before creating another draft.',retryable=False)
        except SetupError:raise
        except Exception:raise SetupError('YouTube upload outcome is uncertain. Inspect Studio; no automatic duplicate will be sent.',retryable=False) from None
