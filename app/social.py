"""Approved social posts, independent of the live-stream controller.

All platform writes have a durable receipt before being sent. An interrupted
write is held for manual review, never automatically sent a second time.
"""
from __future__ import annotations
import base64, copy, hashlib, ipaddress, json, re, secrets, threading, time, tempfile
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from core import atomic_json, now_ist
from social_structure import structure, FACEBOOK_ORDER
from zipfile import ZipFile, ZIP_STORED

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
        self.export_lock=threading.Lock()
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
        # Recover an interrupted local deletion before exposing media again.
        # A corrupt state file is retained for review, including its trash.
        if not self.error:self.recover_deletions()
        self.accounts={};self.account_message='Check your posting accounts before approving a post.'

    def recover_deletions(self):
        for folder in self.folder.glob('.delete-*'):
            if not folder.is_dir() or folder.is_symlink():continue
            for file in folder.iterdir():
                if not re.fullmatch('[a-f0-9]{64}',file.name) or file.is_symlink():continue
                try:
                    target=self.folder/file.name
                    if file.name in self.data['assets'] and not target.exists():file.replace(target)
                    else:file.unlink(missing_ok=True)
                except OSError:pass
            try:folder.rmdir()
            except OSError:pass

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
                item={k:copy.deepcopy(job.get(k)) for k in ('id','revision','title','caption','media','platforms','publish_at','privacy','made_for_kids','status','created_at','results','error','approved_at','targets','delivery','manual_completed_at','batch_revision')}
                jobs.append(item)
            return {'enabled':self.data['enabled'],'busy':self.busy,'error':self.error,
                    'instagram_id':self.data['instagram_id'],'accounts':copy.deepcopy(self.accounts),
                    'account_message':self.account_message,'assets':list(copy.deepcopy(self.data['assets']).values()),
                    'jobs':list(reversed(jobs)),'upload_limit_mb':1024,
                    'reference_ready':len(self.data.get('arrange_reference_images',[]))==17,
                    'structure':structure(),'batch':copy.deepcopy(self.batch_plan())}

    def references(self, data=None):
        """Private operator template, never bundled in the app or posting assets."""
        with self.c.lock,self.lock:
            self.ready()
            if data is None:return {'images':copy.deepcopy(self.data.get('arrange_reference_images',[]))}
            images=data.get('images')
            if data.get('format')!='live-desk-darshan-reference-v1' or not isinstance(images,list) or len(images)!=17:
                raise ValueError('Import a Live Desk reference file with 17 ordered photos.')
            if any(not isinstance(s,str) or len(s)>8000 or not s.startswith('data:image/jpeg;base64,') for s in images) or sum(map(len,images))>60000:
                raise ValueError('Use a small reference template under 60 KB, with JPG previews only.')
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/'reference.jpg'
                for i,s in enumerate(images):
                    try:path.write_bytes(base64.b64decode(s.split(',',1)[1],validate=True))
                    except Exception:raise ValueError('Invalid reference image encoding.') from None
                    kind,w,h=asset_type(path,'reference.jpg')
                    if kind!='image/jpeg' or max(w,h)>128 or min(w,h)<24 or abs(w/h-(.75 if i<7 else 4/3))>.025:
                        raise ValueError('Reference order must be 7 portrait 3:4, then 10 landscape 4:3 previews, up to 128 pixels.')
            old=copy.deepcopy(self.data)
            try:self.data['arrange_reference_images']=copy.deepcopy(images);self.persist()
            except Exception:self.data=old;raise
            return {'ok':True}

    def batch_plan(self):
        return self.data.get('batch', {'revision':0,'slots':['']*17,'title':'Daily darshan',
            'caption':'','times':{'portrait':'','landscape':'','facebook':''},'jobs':[], 'built_revision':None})

    def batch(self, data):
        """Persist mappings, then create exactly five unapproved drafts atomically."""
        with self.c.lock,self.lock:
            self.ready();plan=self.batch_plan()
            if data.get('revision')!=plan['revision']:raise ValueError('The batch changed on another device. Reload the saved batch.')
            if data.get('action')=='save':
                slots=data.get('slots');title=data.get('title','');caption=data.get('caption','');times=data.get('times')
                if not isinstance(slots,list) or len(slots)!=17 or any(not isinstance(m,str) or (m and m not in self.data['assets']) for m in slots):raise ValueError('Assign saved photos to the 17 slots.')
                if any(m and not self.data['assets'][m]['type'].startswith('image/') for m in slots):raise ValueError('The darshan structure uses photos only.')
                if not isinstance(title,str) or not title.strip() or len(title)>65 or not isinstance(caption,str) or len(caption)>2200:raise ValueError('Use a batch name up to 65 characters and shared caption up to 2200.')
                if not isinstance(times,dict) or set(times)!={'portrait','landscape','facebook'} or any(not isinstance(v,str) or len(v)>40 for v in times.values()):raise ValueError('Set the three posting times in IST.')
                fields={'slots':slots,'title':title.strip(),'caption':caption,'times':times}
                if all(plan.get(k)==v for k,v in fields.items()):return copy.deepcopy(plan)
                self.data['batch']={**copy.deepcopy(plan),**fields,'revision':plan['revision']+1}
                self.persist();return copy.deepcopy(self.data['batch'])
            if data.get('action')!='build':raise ValueError('Choose Save batch or Create drafts.')
            if plan.get('built_revision')==plan['revision']:
                if any(not any(j['id']==ident for j in self.data['jobs']) for ident in plan['jobs']):raise ValueError('This batch was already created and some drafts were removed. Change and save the batch before creating a new set.')
                return {'jobs':copy.deepcopy(plan['jobs']),'already_built':True}
            slots=plan['slots']
            if len(slots)!=17 or any(not m or m not in self.data['assets'] for m in slots) or len(set(slots))!=17:raise ValueError('Choose 17 different photos. Fill every slot before creating drafts.')
            for i,m in enumerate(slots):
                _,a=self.media_path(m);ratio=3/4 if i<7 else 4/3
                if not a['type'].startswith('image/') or abs(a['width']/a['height']-ratio)>0.002:raise ValueError(f'Slot {i+1}: crop to {"3:4" if i<7 else "4:3"} with Edit crop first. No silent crop was applied.')
                if i<7 and a['size']>16*1024*1024:raise ValueError(f'Portrait photo {i+1}: save an edited copy under 16 MB for YouTube photo upload.')
                if i>=7 and (a['type']!='image/jpeg' or a['size']>8*1024*1024 or not 320<=a['width']<=1440):raise ValueError(f'Landscape photo {i-6}: use Edit crop to save an Instagram JPG under 8 MB, 320–1440 pixels wide.')
            if len(self.data['jobs'])+5>300:raise ValueError('Remove unused drafts before adding a batch (300 posts limit).')
            backup=copy.deepcopy(self.data)
            try:
                ids=[]
                for spec in structure()['posts']:
                    group=spec['group'];media=slots[:7] if group=='portrait' else slots[7:] if group=='landscape' else [slots[i] for i in FACEBOOK_ORDER]
                    job=self.draft({'title':plan['title']+' · '+{'youtube':'YouTube','facebook':'Facebook','instagram':'Instagram'}[spec['platform']]+' '+group,
                        'caption':plan['caption'],'media':media,'platforms':[spec['platform']],
                        'delivery':spec['delivery'],'publish_at':plan['times'][group],
                        'batch_revision':plan['revision']},_persist=False)
                    ids.append(job['id'])
                self.data['batch'].update(jobs=ids,built_revision=plan['revision']);self.persist()
                return {'jobs':ids,'already_built':False}
            except Exception:
                self.data=backup;raise

    def media_path(self, ident):
        if not isinstance(ident,str) or not re.fullmatch('[a-f0-9]{64}',ident):raise ValueError('Invalid media ID.')
        with self.lock:asset=self.data['assets'].get(ident)
        path=self.folder/ident
        if not asset or not path.is_file() or path.stat().st_size!=asset['size']:raise ValueError('Saved media is missing or damaged.')
        return path,asset

    def export_post(self, ident):
        """Operator download; produces no platform writes or posting receipts.

        A spooled archive bounds memory usage even for a full 17-photo batch.
        Prefixes define upload order and the first file is always the cover.
        """
        if not self.export_lock.acquire(blocking=False):raise ValueError('Wait for the current photo package download.')
        output=None
        try:
            with self.lock:
                self.ready();job=copy.deepcopy(self.job(ident));assets=[]
                for m in job['media']:
                    path,a=self.media_path(m)
                    if not a['type'].startswith('image/'):raise ValueError('Ordered packages are for photo posts.')
                    assets.append((path,copy.deepcopy(a)))
            if not assets:raise ValueError('Choose photos before downloading a package.')
            output=tempfile.SpooledTemporaryFile(max_size=2*1024*1024)
            manifest={'title':job['title'],'caption':job['caption'],'platforms':job['platforms'],
                'delivery':job.get('delivery','api'),'publish_at':job['publish_at'],
                'revision':job['revision'],'cover':1,'photos':[]}
            with ZipFile(output,'w',ZIP_STORED) as archive:
                for i,(path,a) in enumerate(assets,1):
                    name=re.sub(r'[^\w. -]','_',a['name']).strip('. ')[:120] or 'photo'
                    if not name.lower().endswith(('.jpg','.jpeg','.png')):name+='.jpg' if a['type']=='image/jpeg' else '.png'
                    name=f'{i:02d}_{name}';digest=hashlib.sha256()
                    with path.open('rb') as src,archive.open(name,'w') as dest:
                        for chunk in iter(lambda:src.read(CHUNK),b''):digest.update(chunk);dest.write(chunk)
                    if digest.hexdigest()!=a['id']:raise ValueError('A photo changed or is damaged. Re-import it before posting.')
                    manifest['photos'].append({'position':i,'file':name,'original_name':a['name'],
                        'sha256':a['id'],'width':a['width'],'height':a['height']})
                archive.writestr('caption.txt',job['caption'].encode('utf-8'))
                archive.writestr('order.json',json.dumps(manifest,ensure_ascii=False,indent=2).encode('utf-8'))
                archive.writestr('READ-ME.txt',('Upload the numbered photos in ascending order. 01 is the cover.\n'
                    'Copy caption.txt and check the correct account and posting date/time.\n'
                    'This package has NOT posted or scheduled anything on a social platform.\n'
                    'For YouTube: Create > Create post, select photos, paste caption, review then publish or schedule.\n'
                    'Only mark Complete in Live Desk after checking the actual platform post.\n').encode('utf-8'))
            output.seek(0);return output
        except Exception:
            if output:output.close()
            raise
        finally:self.export_lock.release()

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
            if any(ident in j['media'] and j['status'] in ('queued','publishing','needs_review','published','manual_ready','manual_done') for j in self.data['jobs']):raise ValueError('This media belongs to an approved or posted item. Use a new copy to change it.')
            if data.get('action')=='remove':
                if ident in self.batch_plan()['slots']:raise ValueError('Unassign this photo from the saved batch first.')
                if any(ident in j['media'] for j in self.data['jobs']):raise ValueError('Remove its unused drafts first.')
                self.data['assets'].pop(ident);self.persist();(self.folder/ident).unlink(missing_ok=True)
            else:
                value=data.get('public_url','');asset['public_url']=https_media(value) if value else '';self.persist()
            return {'ok':True}

    def removal_plan(self, ids, cleanup):
        rows=[];eligible=[]
        for ident in ids:
            asset=self.data['assets'].get(ident)
            if not asset:raise ValueError('The media selection changed. Reload Media library.')
            refs=[j for j in self.data['jobs'] if ident in j['media']]
            protected=next((j for j in refs if j['status'] not in ('draft','cancelled')),None)
            reason=('Used by '+protected['title']+' ('+protected['status']+')') if protected else 'Used by an unused draft' if refs and not cleanup else 'Assigned to the saved darshan batch' if ident in self.batch_plan()['slots'] and not cleanup else ''
            rows.append({'id':ident,'name':asset['name'],'size':asset['size'],'reason':reason})
            if not reason:eligible.append(ident)
        drafts=[{'id':j['id'],'revision':j['revision'],'title':j['title']}
            for j in self.data['jobs'] if cleanup and j['status'] in ('draft','cancelled') and any(m in eligible for m in j['media'])]
        batch=self.batch_plan();cleared=[i for i,m in enumerate(batch['slots']) if cleanup and m in eligible]
        plan={'files':rows,'drafts':drafts,'batch_slots':cleared,'batch_revision':batch['revision'] if cleared else None,'cleanup_drafts':cleanup}
        plan['fingerprint']=hashlib.sha256(json.dumps(plan,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        return plan

    def assets_bulk(self,data):
        """One exact, confirmed local cleanup; never deletes a platform post."""
        with self.c.lock,self.lock:
            self.ready();ids=data.get('ids');cleanup=data.get('cleanup_drafts',False)
            if not isinstance(ids,list) or not 1<=len(ids)<=500 or any(not isinstance(m,str) or not re.fullmatch('[a-f0-9]{64}',m) for m in ids) or len(ids)!=len(set(ids)) or type(cleanup)!=bool:raise ValueError('Select 1–500 saved media files.')
            if self.busy:raise ValueError('Wait for the active social posting operation.')
            plan=self.removal_plan(ids,cleanup)
            if data.get('action')=='preview':return plan
            if data.get('action')!='remove' or data.get('confirmed') is not True:raise ValueError('Review and confirm the selected media deletion first.')
            if data.get('fingerprint')!=plan['fingerprint']:raise ValueError('A photo, batch or draft changed. Review the deletion again.')
            eligible=[r['id'] for r in plan['files'] if not r['reason']]
            if not eligible:return {'removed':[],'retained':plan['files'],'drafts_removed':0,'batch_slots_cleared':0}
            trash=self.folder/('.delete-'+secrets.token_hex(12));trash.mkdir()
            before=copy.deepcopy(self.data);staged=[];retained=[r for r in plan['files'] if r['reason']]
            try:
                for ident in eligible:
                    try:
                        path=self.folder/ident
                        if path.exists():path.replace(trash/ident)
                        staged.append(ident)
                    except OSError:
                        retained.append({**next(r for r in plan['files'] if r['id']==ident),'reason':'Local file is busy. Try again after closing its preview.'})
                removed_drafts=[j for j in self.data['jobs'] if cleanup and j['status'] in ('draft','cancelled') and any(m in staged for m in j['media'])]
                self.data['jobs']=[j for j in self.data['jobs'] if j not in removed_drafts]
                cleared=0
                if cleanup and any(m in staged for m in self.batch_plan()['slots']):
                    batch=copy.deepcopy(self.batch_plan());cleared=sum(m in staged for m in batch['slots'])
                    batch['slots']=['' if m in staged else m for m in batch['slots']];batch['revision']+=1
                    batch['jobs']=[ident for ident in batch['jobs'] if any(j['id']==ident for j in self.data['jobs'])];self.data['batch']=batch
                for ident in staged:self.data['assets'].pop(ident)
                self.persist()
            except Exception:
                self.data=before
                for ident in staged:
                    try:
                        file=trash/ident
                        if file.exists():file.replace(self.folder/ident)
                    except OSError:pass  # Startup recovery retains the original metadata.
                raise
            finally:
                if not list(trash.iterdir()):trash.rmdir()
            pending=[]
            if trash.exists():
                for file in trash.iterdir():
                    try:file.unlink()
                    except OSError:pending.append(file.name)
                try:trash.rmdir()
                except OSError:pass
            return {'removed':staged,'retained':retained,'drafts_removed':len(removed_drafts),
                'batch_slots_cleared':cleared,'batch_revision':self.batch_plan()['revision'],'cleanup_pending':pending}

    def job(self, ident):
        job=next((j for j in self.data['jobs'] if j['id']==ident),None)
        if not job:raise ValueError('Post not found.')
        return job

    def targets(self, platforms):
        return {p:(self.c.cfg.get({'facebook':'facebook_page_id','youtube':'youtube_channel_id'}.get(p,''),'') or (self.data.get('youtube_id','') if p=='youtube' else '')) if p!='instagram' else self.data['instagram_id'] for p in platforms}

    def draft(self, data, _persist=True):
        with self.c.lock,self.lock:
            self.ready();existing=self.job(data['id']) if data.get('id') else None
            if existing and data.get('revision')!=existing['revision']:raise ValueError('This draft changed on another device. Reload it before saving.')
            if existing and existing['status'] not in ('draft','cancelled'):raise ValueError('Cancel the queued post before editing. Posted/review items are immutable.')
            title=data.get('title','').strip() if isinstance(data.get('title'),str) else ''
            caption=data.get('caption','')
            platforms=data.get('platforms',[]);media=data.get('media',[])
            delivery=data.get('delivery','api')
            if delivery not in ('api','manual'):raise ValueError('Choose API posting or manual handoff.')
            if not title or len(title)>100 or not isinstance(caption,str) or len(caption)>5000:raise ValueError('Use a title up to 100 characters and a caption up to 5000.')
            if not isinstance(platforms,list) or not platforms or len(platforms)!=len(set(platforms)) or any(p not in PLATFORMS for p in platforms):raise ValueError('Choose Facebook, Instagram or YouTube.')
            limit=17 if platforms==['facebook'] else 10
            if not isinstance(media,list) or any(not isinstance(m,str) for m in media) or len(media)>limit or len(media)!=len(set(media)) or any(m not in self.data['assets'] for m in media):raise ValueError('Choose up to 17 photos for Facebook alone, or 10 for other posts.')
            if delivery=='manual' and (len(platforms)!=1 or not media or any(not self.data['assets'][m]['type'].startswith('image/') for m in media)):raise ValueError('Manual photo handoff needs one destination and saved photos.')
            if delivery=='manual' and 'youtube' in platforms and any(self.data['assets'][m]['size']>16*1024*1024 for m in media):raise ValueError('YouTube photo uploads need images under 16 MB. Save an edited copy first.')
            if not caption.strip() and not media:raise ValueError('Add a caption or media.')
            if any(self.data['assets'][m]['type'].startswith('video/') for m in media) and len(media)!=1:raise ValueError('A video post needs exactly one video.')
            if 'youtube' in platforms and len(caption.encode('utf-8'))>5000:raise ValueError('YouTube descriptions must be at most 5000 UTF-8 bytes; shorten the caption.')
            if 'youtube' in platforms and any(c in title for c in '<>'):raise ValueError('YouTube titles cannot contain < or >.')
            if delivery=='api' and 'youtube' in platforms and (len(media)!=1 or self.data['assets'][media[0]]['type']!='video/mp4'):raise ValueError('YouTube API posting requires one video. Choose manual handoff for Community photos.')
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
                 'created_at':existing['created_at'] if existing else now_ist().isoformat(),'results':{},'error':'','approved_at':None,'targets':{},
                 'delivery':delivery,'batch_revision':data.get('batch_revision')}
            if existing:self.data['jobs'][self.data['jobs'].index(existing)]=job
            else:
                if len(self.data['jobs'])>=300:raise ValueError('Remove unused drafts before adding more posts (300 limit).')
                self.data['jobs'].append(job)
            if _persist:self.persist()
            return copy.deepcopy(job)

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
                if job.get('delivery')=='manual':
                    for m in job['media']:self.media_path(m)
                    job.update(status='manual_ready',approved_at=now_ist().isoformat(),targets=self.targets(job['platforms']))
                    self.persist();return {'ok':True}
                targets=self.targets(job['platforms'])
                if any(not re.fullmatch(r'UC[A-Za-z0-9_-]{22}' if p=='youtube' else r'[0-9]{5,30}',v or '') for p,v in targets.items()):raise ValueError('Save the selected Page/channel and linked Instagram account before approving.')
                due=datetime.fromisoformat(job['publish_at'])
                if due<now_ist():raise ValueError('Choose a future posting time and save the draft again.')
                for ident in job['media']:
                    path,asset=self.media_path(ident)
                    if 'instagram' in job['platforms'] and (asset['type']!='image/jpeg' and not asset.get('public_url')):raise ValueError('Instagram needs JPG images or a public HTTPS URL for a video. Edit PNG as JPG first.')
                    if 'instagram' in job['platforms'] and asset['type']=='image/jpeg' and asset['size']>8*1024*1024:raise ValueError('Export Instagram JPGs under 8 MB with the image editor.')
                    if 'instagram' in job['platforms'] and asset['type']=='image/jpeg' and not 320<=asset['width']<=1440:raise ValueError('Instagram JPGs need width 320–1440 pixels. Save an edited copy first.')
                    if 'instagram' in job['platforms'] and asset['type']=='image/jpeg' and not 0.8<=asset['width']/asset['height']<=1.91:raise ValueError('Crop Instagram photos to square, 4:5 or landscape (up to 1.91:1).')
                job.update(status='queued',approved_at=now_ist().isoformat(),targets=targets);self.persist()
            elif action=='manual_done':
                if data.get('confirmed') is not True or job.get('delivery')!='manual' or job['status']!='manual_ready':raise ValueError('Confirm that you completed this photo post on the platform.')
                job.update(status='manual_done',manual_completed_at=now_ist().isoformat());self.persist()
            elif action=='cancel':
                if job['status'] not in ('queued','draft','manual_ready'):raise ValueError('A started or uncertain post cannot be cancelled here. Inspect the platform first.')
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
            job=next((j for j in self.data['jobs'] if j['status']=='queued' and j.get('delivery','api')=='api' and datetime.fromisoformat(j['publish_at'])<=now),None)
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
