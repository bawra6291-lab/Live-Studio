"""Run the production adapter against an isolated local browser fixture only."""
import hashlib,json,sys,tempfile,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from visible_browser import Browser,BrowserCDP
from youtube_post import YouTubePost

address,site,case,payload=sys.argv[1:]
if not site.startswith('http://127.0.0.1:'):raise ValueError('Local fixtures only')
data=json.loads(Path(payload).read_text())
with tempfile.TemporaryDirectory(prefix='youtube-post-fixture-') as folder:
    class Media:
        def __init__(self):self.folder=Path(folder)/'social-media';self.folder.mkdir();self.assets={};self.result={}
        def media_path(self,ident):return self.folder/ident,self.assets[ident]
        def checkpoint(self,ident,platform,**values):self.result.update(values)
    media=Media();ids=[]
    import base64
    for item in data['photos']:
        raw=base64.b64decode(item);ident=hashlib.sha256(raw).hexdigest();(media.folder/ident).write_bytes(raw)
        media.assets[ident]={'type':'image/jpeg','size':len(raw)};ids.append(ident)
    if case=='corrupt':(media.folder/ids[0]).write_bytes(b'changed')
    browser=Browser(folder,ready=lambda:None);browser.source='running_chrome';browser.chrome=BrowserCDP(address)
    class FixturePost(YouTubePost):
        SITE=site;TIMEOUT=3;UPLOAD_TIMEOUT=4;RECEIPT_TIMEOUT=3
    adapter=FixturePost({},None,media,threading.Event(),browser)
    job={'id':'fixture-job','platforms':['youtube'],'studio_youtube_browser':True,'privacy':'public',
         'media':ids,'caption':data['caption'],'targets':{'youtube':data['channel']},'results':{}}
    error=''
    try:adapter.publish(job)
    except Exception as exc:error=str(exc)
    finally:browser.disconnect()
    print(json.dumps({'result':media.result,'error':error}))
