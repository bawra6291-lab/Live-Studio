"""Visible Community photo posting in the operator's consented Chrome session.

No private YouTube endpoint, cookies or credentials are read. A published
receipt needs a new post permalink with the reviewed caption, not a toast.
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
 const visible=n=>!!n&&n.getClientRects().length>0&&getComputedStyle(n).visibility!=='hidden';
 const text=n=>(n?.innerText||n?.textContent||'').trim();
 const norm=s=>s.replace(/\s+/g,' ').trim();
 const unique=nodes=>{nodes=[...new Set(nodes)].filter(visible);return nodes.length===1?nodes[0]:null;};
 const box=()=>unique(all('ytd-backstage-post-dialog-renderer, ytd-backstage-post-creation-box-renderer').filter(n=>!n.querySelector('ytd-backstage-post-dialog-renderer, ytd-backstage-post-creation-box-renderer')));
 const point=n=>{if(!n||n.disabled||n.getAttribute('aria-disabled')==='true')return null;n.scrollIntoView({block:'center'});const r=n.getBoundingClientRect(),x=r.x+r.width/2,y=r.y+r.height/2,top=document.elementFromPoint(x,y);return top&&(top===n||n.contains(top))?{x,y}:null;};
 const button=(label,root=document)=>unique(all('button,[role="button"]',root).filter(n=>norm(n.getAttribute('aria-label')||text(n)).toLowerCase()===label));
 const field=()=>{const r=box();return r&&unique(all('[contenteditable="true"],[contenteditable="plaintext-only"],textarea',r));};
 const input=()=>{const r=box(),nodes=all('input[type="file"]').filter(n=>/image|\.jpg|\.png/i.test(n.accept||'')&&n.multiple);return nodes.length===1?nodes[0]:r&&all('input[type="file"]',r).length===1?all('input[type="file"]',r)[0]:null;};
 const images=()=>{const roots=[box(),...all('ytd-backstage-image-upload-renderer').filter(visible)].filter(Boolean);return [...new Set(roots.flatMap(r=>all('ytd-backstage-image-renderer img, ytd-backstage-image-upload-renderer img, #attachments img, #image-attachment-previewer img, #image-attachment-preview img, img',r).filter(n=>(n.currentSrc||n.src)&&n.naturalWidth>32&&n.naturalHeight>32).filter(n=>r.tagName==='YTD-BACKSTAGE-IMAGE-UPLOAD-RENDERER'||n.closest('ytd-backstage-image-renderer, ytd-backstage-image-upload-renderer, #attachments, #image-attachment-previewer, #image-attachment-preview'))).map(n=>n.currentSrc||n.src))];};
 const posts=()=>all('ytd-backstage-post-renderer').map(n=>{const d=n.data||{},content=n.querySelector('#content-text'),links=all('a[href*="/post/"]',n),author=n.querySelector('#author-text, #author-thumbnail'),ident=d.authorEndpoint?.browseEndpoint?.browseId;return {caption:d.contentText?.runs?.map(r=>r.text||'').join('')||d.contentText?.simpleText||content?.innerText||content?.textContent||'',published:text(n.querySelector('#published-time-text'))||d.publishedTimeText?.simpleText||d.publishedTimeText?.runs?.map(r=>r.text||'').join('')||'',url:links.map(a=>a.href).find(u=>/\/post\/[A-Za-z0-9_-]+/.test(u))||(typeof d.postId==='string'&&/^Ug[\w-]+$/.test(d.postId)?location.origin+'/post/'+d.postId:''),authors:[...new Set([ident,author?.getAttribute('href')?.match(/\/channel\/(UC[\w-]{22})(?:[/?#]|$)/)?.[1]].filter(s=>typeof s==='string'&&/^UC[\w-]{22}$/.test(s)))]};});
 if(arg.action==='account'){
  const exact=all('#channel-id, [aria-label="Channel ID"], [aria-label="Channel ID"] input').flatMap(n=>[n.value||'',text(n),...all('input',n).map(i=>i.value||'')]);
  const values=exact.length?exact.join(' '):document.body.innerText;
  return [...new Set(values.match(/\bUC[A-Za-z0-9_-]{22}\b/g)||[])];
 }
 if(arg.action==='composer')return !!box();
 if(arg.action==='create')return point(button('create'));
 if(arg.action==='createPost')return point(button('create post')||unique(all('ytd-compact-link-renderer').filter(n=>norm(text(n)).toLowerCase()==='create post')));
 if(arg.action==='caption')return point(field()||box()?.querySelector('#placeholder-area'));
 if(arg.action==='image')return point(button('image',box()||document)||button('image'));
 if(arg.action==='input')return input();
 if(arg.action==='state'){const f=field(),i=input();return {caption:f?(f.value??f.innerText):'',photos:images().length,files:i?Array.from(i.files||[]).map(f=>({name:f.name,size:f.size})):[],publish:point(button('post',box()||document))};}
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

    def wait(self,fn,timeout=None):
        end=time.monotonic()+(timeout or self.TIMEOUT)
        while time.monotonic()<end:
            self.guard();value=fn()
            if value:return value
            time.sleep(.2)
        raise SetupError('YouTube page did not reach the expected posting step. Inspect the Chrome tab; this draft will not be repeated automatically.',retryable=False)

    def navigate(self,page,path):
        self.guard();page.call('Page.enable');page.call('Page.bringToFront');page.call('Page.navigate',url=self.SITE+path)
        def loaded():
            self.guard();address=page.evaluate('location.href')
            if not address or address=='about:blank':return False
            if origin(address)!=origin(self.SITE):return False
            return urlsplit(address).path.rstrip('/')==path.split('?',1)[0].rstrip('/') and page.evaluate('document.readyState') in ('interactive','complete')
        self.wait(loaded)

    def click(self,page,point):
        self.guard(page);page.call('Page.bringToFront')
        for kind in ('mouseMoved','mousePressed','mouseReleased'):
            self.guard(page);page.call('Input.dispatchMouseEvent',type=kind,x=point['x'],y=point['y'],**({'button':'left','clickCount':1} if kind!='mouseMoved' else {}))

    def account(self,page,channel):
        self.navigate(page,'/account_advanced?hl=en')
        identities=self.wait(lambda:self.read(page,'account'))
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
                if state['caption'].strip() or state['photos'] or state['files']:
                    raise SetupError('The YouTube composer already contains another draft. It was retained; finish or discard it locally before posting.',retryable=False)
                self.s.checkpoint(job['id'],'youtube',status='posting',stage='Entering reviewed caption')
                self.click(page,self.wait(lambda:self.read(page,'caption')))
                if not self.read(page,'focus'):raise SetupError('YouTube caption field lost focus. No text was entered.',retryable=False)
                page.call('Input.insertText',text=job['caption'])
                self.s.checkpoint(job['id'],'youtube',status='posting',stage='Uploading '+str(len(files))+' photos in preview order')
                expression=DOM+'('+json.dumps({'action':'input'})+')'
                result=page.call('Runtime.evaluate',expression=expression,returnByValue=False).get('result',{})
                if result.get('subtype')!='node':
                    self.click(page,self.wait(lambda:self.read(page,'image')))
                    def file_node():
                        self.guard(page);return page.call('Runtime.evaluate',expression=expression,returnByValue=False).get('result',{})
                    result=self.wait(lambda:(r if (r:=file_node()).get('subtype')=='node' else None))
                obj=result['objectId']
                try:
                    self.guard(page);page.call('DOM.setFileInputFiles',files=[str(p.resolve()) for p in files],objectId=obj)
                finally:page.call('Runtime.releaseObject',objectId=obj)
                def uploaded():
                    state=self.read(page,'state')
                    expected=[{'name':p.name,'size':p.stat().st_size} for p in files]
                    if state['files'] and state['files']!=expected:raise SetupError('YouTube selected photos do not match the reviewed order. Nothing was published.',retryable=False)
                    return state if state['photos']==len(files) else None
                self.wait(uploaded,self.UPLOAD_TIMEOUT)
                done=self.read(page,'done')
                if done:self.click(page,done)
                self.account(identity,channel)  # Recheck the current Chrome identity immediately before Publish.
                state=self.wait(lambda:(s if (s:=uploaded()) and s['publish'] else None))
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
                                and post['authors']==[channel] and ' '.join(post['caption'].split())==wanted):matches.append(post)
                    return matches[0] if len(matches)==1 else None
                posted=self.wait(receipt,self.RECEIPT_TIMEOUT);url=self.SITE+urlsplit(posted['url']).path
                self.s.checkpoint(job['id'],'youtube',status='published',stage='Published in Chrome; new post link verified',id=urlsplit(url).path.rsplit('/',1)[1],url=url,photos=len(files))
            finally:
                if page:
                    try:page.call('Page.setInterceptFileChooserDialog',enabled=False)
                    except Exception:pass
                    page.close()
                identity.close()
