"""Visible Community photo posting in the operator's consented Chrome session.

No private YouTube endpoint, cookies or credentials are read. A published
receipt needs a new post permalink with the reviewed caption and photo count.
"""
import hashlib
import json
import re
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

from connections import SetupError
from visible_browser import origin


DOM = r'''(arg => {
 const all=(s,r=document)=>Array.from(r.querySelectorAll(s));
 const deep=(s,r=document)=>all(s,r).concat(all('*',r).flatMap(n=>n.shadowRoot?deep(s,n.shadowRoot):[]));
 const visible=n=>!!n&&n.getClientRects().length>0&&getComputedStyle(n).visibility!=='hidden';
 const text=n=>(n?.innerText||n?.textContent||'').trim();
 const norm=s=>s.replace(/\s+/g,' ').trim();
 const unique=nodes=>{nodes=[...new Set(nodes)].filter(visible);return nodes.length===1?nodes[0]:null;};
 const box=()=>unique(all('ytd-backstage-post-dialog-renderer, ytd-backstage-post-creation-box-renderer').filter(n=>!n.querySelector('ytd-backstage-post-dialog-renderer, ytd-backstage-post-creation-box-renderer')));
 const point=n=>{if(!n||n.disabled||n.getAttribute('aria-disabled')==='true')return null;n.scrollIntoView({block:'center'});const r=n.getBoundingClientRect(),x=r.x+r.width/2,y=r.y+r.height/2,top=document.elementFromPoint(x,y);return top&&(top===n||n.contains(top))?{x,y}:null;};
 const button=(label,root=document)=>unique(all('button,[role="button"]',root).filter(n=>norm(n.getAttribute('aria-label')||text(n)).toLowerCase()===label));
 const field=()=>{const r=box();return r&&unique(all('[contenteditable="true"],[contenteditable="plaintext-only"],textarea',r));};
 const input=()=>{const r=box(),nodes=all('input[type="file"]').filter(n=>/image|\.jpg|\.png/i.test(n.accept||'')&&n.multiple);return nodes.length===1?nodes[0]:r&&all('input[type="file"]',r).length===1?all('input[type="file"]',r)[0]:null;};
 const uploaders=()=>all('ytd-backstage-image-upload-renderer').filter(visible);
 const attachedImages=root=>root?[...new Set(all('img',root).filter(n=>(n.currentSrc||n.src)&&n.naturalWidth>32&&n.naturalHeight>32&&(root.tagName==='YTD-BACKSTAGE-IMAGE-UPLOAD-RENDERER'||n.closest('ytd-backstage-image-renderer, ytd-backstage-image-upload-renderer, #attachments, #image-attachment-previewer, #image-attachment-preview'))).map(n=>n.currentSrc||n.src))]:[];
 const postPhotos=n=>{
  const attachment=n.data?.backstageAttachment;
  const items=attachment?.postMultiImageRenderer?.images;
  const hasImage=r=>r?.image?.thumbnails?.some(t=>typeof t.url==='string'&&t.url.length>0);
  if(Array.isArray(items))return items.filter(i=>hasImage(i.backstageImageRenderer)).length;
  if(hasImage(attachment?.backstageImageRenderer))return 1;
  return attachedImages(n).length;
 };
 const posts=()=>all('ytd-backstage-post-renderer').map(n=>{const d=n.data||{},content=n.querySelector('#content-text'),links=all('a[href*="/post/"]',n),author=n.querySelector('#author-text, #author-thumbnail'),ident=d.authorEndpoint?.browseEndpoint?.browseId;return {photos:postPhotos(n),caption:d.contentText?.runs?.map(r=>r.text||'').join('')||d.contentText?.simpleText||content?.innerText||content?.textContent||'',published:text(n.querySelector('#published-time-text'))||d.publishedTimeText?.simpleText||d.publishedTimeText?.runs?.map(r=>r.text||'').join('')||'',url:links.map(a=>a.href).find(u=>/\/post\/[A-Za-z0-9_-]+/.test(u))||(typeof d.postId==='string'&&/^Ug[\w-]+$/.test(d.postId)?location.origin+'/post/'+d.postId:''),authors:[...new Set([ident,author?.getAttribute('href')?.match(/\/channel\/(UC[\w-]{22})(?:[/?#]|$)/)?.[1]].filter(s=>typeof s==='string'&&/^UC[\w-]{22}$/.test(s)))]};});
 if(arg.action==='account'){
  // Read only the labelled account setting. A channel link elsewhere on the
  // page is not evidence of the signed-in account. Input values are absent
  // from innerText; modern settings can also wrap them in open shadow roots.
  const ids=s=>Array.from(String(s).matchAll(/(?:^|[^A-Za-z0-9_-])(UC[A-Za-z0-9_-]{22})(?=$|[^A-Za-z0-9_-])/g),m=>m[1]);
  const value=n=>ids([n.value||'',text(n),...deep('input,textarea',n).filter(visible).map(i=>i.value||'')].join(' '));
  const labels=deep('*').filter(n=>visible(n)&&(n.id==='channel-id'||/^channel id:?$/i.test(n.getAttribute('aria-label')||'')||(!n.children.length&&/^channel id:?$/i.test(text(n)))));
  const found=[];
  for(const label of labels){
   const linked=deep('input,textarea').filter(n=>visible(n)&&((label.htmlFor&&n.id===label.htmlFor)||(label.id&&(n.getAttribute('aria-labelledby')||'').split(/\s+/).includes(label.id))));
   let matches=[...value(label),...linked.flatMap(value)];
   // A label and readonly field are often siblings inside a setting row.
   let row=label;
   for(let depth=0;!matches.length&&depth<3;depth++){
    row=row.parentElement||row.getRootNode()?.host;
    if(!row||row===document.body||row===document.documentElement)break;
    const fields=deep('input,textarea',row).filter(visible);
    if(fields.length===1)matches=value(fields[0]);
    else if(!fields.length&&row.children.length<=3)matches=value(row);
   }
   found.push(...matches);
  }
  return [...new Set(found)];
 }
 if(arg.action==='composer')return !!box();
 if(arg.action==='create')return point(button('create'));
 if(arg.action==='createPost')return point(button('create post')||unique(all('ytd-compact-link-renderer').filter(n=>norm(text(n)).toLowerCase()==='create post')));
 if(arg.action==='caption')return point(field()||box()?.querySelector('#placeholder-area'));
 if(arg.action==='image')return point(button('image',box()||document)||button('image'));
 if(arg.action==='selectFiles'){const roots=[box(),...uploaders()].filter(Boolean);return point(unique(roots.flatMap(r=>all('*',r).filter(n=>!n.children.length&&norm(text(n)).toLowerCase()==='select from your computer'))));}
 if(arg.action==='input')return input();
 if(arg.action==='state'){const f=field(),i=input();return {caption:f?(f.value??f.innerText):'',photos:attachedImages(box()).length,uploadPhotos:Math.max(0,...uploaders().map(r=>attachedImages(r).length)),uploadOpen:uploaders().some(r=>!box()?.contains(r)),busy:!!box()&&all('[aria-busy="true"],[role="progressbar"]',box()).some(visible),files:i?Array.from(i.files||[]).map(f=>({name:f.name,size:f.size})):[],publish:point(button('post',box()||document))};}
 if(arg.action==='done')return point(button('done',box()||document)||button('done'));
 if(arg.action==='posts')return posts();
 if(arg.action==='focus')return !!field()&&(document.activeElement===field());
 return null;
})'''


def chrome_ready(browser):
    if browser.source!='running_chrome':
        raise ValueError('YouTube photo posting needs My running Chrome. Open Connections → YouTube → Chrome posting setup on this PC.')
    if browser.recording:raise ValueError('Finish browser recording before posting photos.')
    browser.ensure()


class YouTubePost:
    SITE='https://www.youtube.com'
    TIMEOUT=30
    UPLOAD_TIMEOUT=180
    RECEIPT_TIMEOUT=60

    def __init__(self,cfg,vault,manager,stop,browser):
        self.s,self.stop,self.browser=manager,stop,browser

    def guard(self,page=None):
        if self.stop.is_set():raise SetupError('YouTube posting stopped. Inspect YouTube before creating another draft.',retryable=False)
        self.browser.guard()
        if page and origin(page.evaluate('location.href'))!=origin(self.SITE):
            raise SetupError('YouTube left its page. Complete Chrome login locally, then review this post. No automatic retry was sent.',retryable=False)

    def read(self,page,action):
        self.guard(page)
        return page.evaluate(DOM+'('+json.dumps({'action':action})+')')

    def wait(self,fn,timeout=None,message=None):
        end=time.monotonic()+(timeout or self.TIMEOUT)
        while time.monotonic()<end:
            self.guard();value=fn()
            if value:return value
            time.sleep(.2)
        raise SetupError(message or 'YouTube page did not reach the expected posting step. Inspect the Chrome tab; this draft will not be repeated automatically.',retryable=False)

    def navigate(self,page,path):
        self.guard();page.call('Page.enable');page.call('Page.bringToFront')
        navigation=page.call('Page.navigate',url=self.SITE+path)
        if navigation.get('errorText'):
            raise SetupError('Chrome could not load YouTube. Check the network and the open Chrome tab, then prepare a new draft. No publish click was sent.',retryable=False)
        def loaded():
            # Reopening the identity tab must inspect the newly loaded account,
            # not the previous document at the same URL.
            loader=navigation.get('loaderId')
            if loader and page.call('Page.getFrameTree').get('frameTree',{}).get('frame',{}).get('loaderId')!=loader:return False
            self.guard();address=page.evaluate('location.href')
            if not address or address=='about:blank':return False
            if origin(address)!=origin(self.SITE):return False
            return urlsplit(address).path.rstrip('/')==path.split('?',1)[0].rstrip('/') and page.evaluate('document.readyState') in ('interactive','complete')
        try:
            self.wait(loaded)
        except SetupError:
            # Do not turn cancellation or a locked desktop into a login error.
            self.guard()
            address=urlsplit(page.evaluate('location.href') or '')
            if address.hostname in ('accounts.google.com','consent.youtube.com','consent.google.com') or address.path in ('/signin','/oops'):
                raise SetupError('Chrome needs YouTube sign-in or consent. Complete the page already open in your running Chrome, then prepare a new draft. No publish click was sent.',retryable=False) from None
            if path.startswith('/account_advanced'):
                raise SetupError('YouTube Advanced settings did not open. In this Chrome profile, select the channel owner account and open YouTube Settings → Advanced settings, then prepare a new draft. No publish click was sent.',retryable=False) from None
            raise

    def click(self,page,point):
        self.guard(page);page.call('Page.bringToFront')
        for kind in ('mouseMoved','mousePressed','mouseReleased'):
            self.guard(page);page.call('Input.dispatchMouseEvent',type=kind,x=point['x'],y=point['y'],**({'button':'left','clickCount':1} if kind!='mouseMoved' else {}))

    def account(self,page,channel):
        self.navigate(page,'/account_advanced?hl=en')
        identities=self.wait(lambda:self.read(page,'account'),message='Chrome channel verification could not read the Channel ID in YouTube Advanced settings. Keep that tab open and check that the channel owner is selected. No photos were published; prepare a new draft after correcting the account.')
        if identities!=[channel]:raise SetupError('Chrome is signed into a different YouTube channel. Switch Chrome to the reviewed channel before sending. No post was published.',retryable=False)

    def publish(self,job):
        channel=job.get('targets',{}).get('youtube','')
        if not job.get('studio_youtube_browser') or job.get('privacy')!='public' or not re.fullmatch(r'UC[\w-]{22}',channel):raise SetupError('Prepare an automatic public YouTube photo draft with a verified channel.',retryable=False)
        if job.get('results',{}).get('youtube',{}).get('write_dispatched'):raise SetupError('A publish click was already dispatched. Inspect YouTube; this post cannot be replayed.',retryable=False)
        photos=job['media']
        if len(photos) not in (7,10) or len(set(photos))!=len(photos):raise SetupError('Review a complete 7- or 10-photo YouTube post.',retryable=False)
        chrome_ready(self.browser)
        with self.browser.lock,tempfile.TemporaryDirectory(prefix='youtube-post-',dir=self.s.folder.parent) as folder:
            files=[]
            for index,ident in enumerate(photos):
                path,asset=self.s.media_path(ident)
                raw=path.read_bytes()
                if path.is_symlink() or asset['type']!='image/jpeg' or hashlib.sha256(raw).hexdigest()!=ident or len(raw)>16*1024*1024:
                    raise SetupError('A reviewed YouTube photo changed or is not a supported JPG. Prepare a new preview.',retryable=False)
                target=Path(folder)/(str(index+1).zfill(2)+'.jpg');target.write_bytes(raw);files.append(target)
            self.s.checkpoint(job['id'],'youtube',status='posting',stage='Checking Chrome channel')
            identity=self.browser.page('youtube-post-identity');page=None
            try:
                self.account(identity,channel)
                page=self.browser.page('youtube-photo-post')
                self.navigate(page,'/channel/'+channel+'/posts?hl=en')
                page.call('Page.setInterceptFileChooserDialog',enabled=True)
                before={urlsplit(p['url']).path for p in self.read(page,'posts')}
                if not self.read(page,'composer'):
                    self.click(page,self.wait(lambda:self.read(page,'create')))
                    self.click(page,self.wait(lambda:self.read(page,'createPost')))
                self.wait(lambda:self.read(page,'composer'))
                state=self.read(page,'state')
                if state['caption'].strip() or state['photos'] or state['uploadOpen'] or state['files']:
                    raise SetupError('The YouTube composer already contains another draft. It was retained; finish or discard it locally before posting.',retryable=False)
                self.s.checkpoint(job['id'],'youtube',status='posting',stage='Entering reviewed caption')
                self.click(page,self.wait(lambda:self.read(page,'caption')))
                if not self.read(page,'focus'):raise SetupError('YouTube caption field lost focus. No text was entered.',retryable=False)
                page.call('Input.insertText',text=job['caption'])
                self.s.checkpoint(job['id'],'youtube',status='posting',stage='Uploading '+str(len(files))+' photos in preview order')
                # Use the native chooser event from this managed tab, not a
                # global hidden input that may belong to a stale uploader.
                page.clear_file_choosers()
                self.click(page,self.wait(lambda:self.read(page,'image'),message='YouTube Image button was not ready. No publish click was sent. Keep the Chrome tab open for review.'))
                def picker_step():
                    self.guard(page)
                    chooser=page.take_file_chooser()
                    if chooser:return {'chooser':chooser}
                    point=self.read(page,'selectFiles')
                    return {'point':point} if point else None
                step=self.wait(picker_step,message='YouTube Select from your computer control did not appear. No publish click was sent. Keep the image panel open for review.')
                if 'point' in step:
                    self.s.checkpoint(job['id'],'youtube',status='posting',stage='Selecting reviewed photos through YouTube file picker')
                    self.click(page,step['point'])
                    chooser=self.wait(lambda:page.take_file_chooser(),message='YouTube file picker did not respond after Select from your computer. No publish click was sent.')
                else:chooser=step['chooser']
                self.guard(page)
                main=page.call('Page.getFrameTree')['frameTree']['frame']['id']
                node_id=chooser.get('backendNodeId')
                if not isinstance(node_id,int) or node_id<=0 or chooser.get('mode')!='selectMultiple' or chooser.get('frameId')!=main:
                    raise SetupError('YouTube did not open the expected multiple-image picker in this tab. No files or publish click were sent.',retryable=False)
                node=page.call('DOM.describeNode',backendNodeId=node_id)['node']
                raw_attrs=node.get('attributes',[]);attrs=dict(zip(raw_attrs[::2],raw_attrs[1::2]))
                if node.get('nodeName')!='INPUT' or attrs.get('type','').lower()!='file' or 'multiple' not in attrs or not re.search(r'image|\.jpg|\.jpeg|\.png|\.gif',attrs.get('accept',''),re.I):
                    raise SetupError('The opened YouTube picker is not a multiple-image input. No files or publish click were sent.',retryable=False)
                obj=page.call('DOM.resolveNode',backendNodeId=node_id)['object']['objectId']
                try:
                    self.guard(page);page.call('DOM.setFileInputFiles',files=[str(p.resolve()) for p in files],backendNodeId=node_id)
                    selected=page.call('Runtime.callFunctionOn',objectId=obj,functionDeclaration='function(){return Array.from(this.files||[]).map(f=>({name:f.name,size:f.size}));}',returnByValue=True)
                    expected=[{'name':p.name,'size':p.stat().st_size} for p in files]
                    if selected.get('exceptionDetails') or selected.get('result',{}).get('value')!=expected:
                        raise SetupError('YouTube picker did not receive the reviewed photos in order. No publish click was sent.',retryable=False)
                finally:page.call('Runtime.releaseObject',objectId=obj)
                def uploaded(committed=False):
                    state=self.read(page,'state')
                    count=state['photos'] if committed else max(state['photos'],state['uploadPhotos'])
                    return state if count==len(files) and (not committed or not state['uploadOpen'] and not state['busy']) else None
                previews=self.wait(uploaded,self.UPLOAD_TIMEOUT,message='YouTube did not display all selected photo previews. No publish click was sent. Check the open image picker; selected files alone do not confirm an upload.')
                if previews['uploadOpen']:
                    done=self.wait(lambda:self.read(page,'done'),self.UPLOAD_TIMEOUT,message='YouTube image picker is still processing the photos. No publish click was sent. Check upload progress in Chrome.')
                    self.click(page,done)
                self.s.checkpoint(job['id'],'youtube',status='posting',stage='Verifying '+str(len(files))+' attached photos in YouTube composer')
                self.wait(lambda:uploaded(True),self.UPLOAD_TIMEOUT,message='YouTube photos were not attached to the post after the image picker. Posting stopped to avoid a text-only post. No publish click was sent.')
                self.s.checkpoint(job['id'],'youtube',status='posting',stage='Rechecking Chrome channel before Publish')
                self.account(identity,channel)  # Recheck the current Chrome identity immediately before Publish.
                state=self.wait(lambda:(s if (s:=uploaded(True)) and s['publish'] else None),self.UPLOAD_TIMEOUT,message='YouTube photo post is not ready to publish. Check the attached photos and upload progress in Chrome. No publish click was sent.')
                # Contenteditable renders inserted newlines as browser block nodes.
                # Ignore layout whitespace while still requiring every word/emoji.
                if ' '.join(state['caption'].split())!=' '.join(job['caption'].split()):
                    raise SetupError('YouTube caption differs from the reviewed preview. Nothing was published.',retryable=False)
                before.update(urlsplit(p['url']).path for p in self.read(page,'posts'))
                self.s.checkpoint(job['id'],'youtube',status='posting',stage='Publish click dispatched; awaiting a new post link',write_dispatched=True)
                self.click(page,state['publish'])  # One publish dispatch. Never repeat this click.
                wanted=' '.join(job['caption'].split())
                def receipt():
                    matches=[]
                    for post in self.read(page,'posts'):
                        url=post['url'];parsed=urlsplit(url)
                        if not url:continue
                        if (parsed.path not in before and origin(url)==origin(self.SITE) and re.fullmatch(r'/post/[A-Za-z0-9_-]+',parsed.path)
                                and (post['published'].lower()=='just now' or re.fullmatch(r'\d{1,2} seconds? ago',post['published'].lower()))
                                and post['authors']==[channel] and post['photos']==len(files) and ' '.join(post['caption'].split())==wanted):matches.append(post)
                    return matches[0] if len(matches)==1 else None
                posted=self.wait(receipt,self.RECEIPT_TIMEOUT,message='YouTube publish was dispatched, but a new post with all reviewed photos could not be verified. Check YouTube; do not resend automatically.');url=self.SITE+urlsplit(posted['url']).path
                self.s.checkpoint(job['id'],'youtube',status='published',stage='Published in Chrome; new post link and photo count verified',id=urlsplit(url).path.rsplit('/',1)[1],url=url,photos=len(files))
            finally:
                if page:
                    try:page.call('Page.setInterceptFileChooserDialog',enabled=False)
                    except Exception:pass
                    page.close()
                identity.close()
