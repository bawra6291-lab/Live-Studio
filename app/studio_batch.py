"""Reviewed multi-destination drafts and local ordered photo packages."""
import copy, secrets, threading, time
from core import now_ist


def posting_modes(platform,section):
    if section not in ('P1','P2','FB','BOTH'):raise ValueError('Choose 7 portraits, 10 landscapes, 17 mixed or both posts.')
    if platform=='telegram':return ['TG'] if section in ('FB','BOTH') else [section]
    if platform=='facebook':return ['P1','P2'] if section=='BOTH' else [section]
    if platform in ('instagram','youtube'):return ['P1','P2'] if section in ('FB','BOTH') else [section]
    raise ValueError('Choose a supported posting account.')


class StudioBatch:
    def prepare_batch(self,data):
        with self.c.lock,self.s.lock:
            self.ready()
            if self.s.busy:raise ValueError('Wait for the current posting operation.')
            platforms=data.get('platforms');section=data.get('section');media=data.get('media')
            if (not isinstance(platforms,list) or not platforms or len(platforms)>4 or any(not isinstance(p,str) for p in platforms) or len(set(platforms))!=len(platforms)
                    or any(p not in ('facebook','instagram','youtube','telegram') for p in platforms) or not isinstance(media,dict)):
                raise ValueError('Select the accounts to include in this review.')
            specs=[]
            # WhatsApp is a reviewed manual handoff, never an API send or receipt.
            whatsapp=data.get('whatsapp')
            if whatsapp is not None:
                if not isinstance(whatsapp,dict) or whatsapp.get('mode')!=section:raise ValueError('Review the selected WhatsApp photo section.')
                values=whatsapp.get('media');caption=whatsapp.get('caption','');title=whatsapp.get('title','Daily darshan')
                if not isinstance(values,list) or len(values)!={'P1':7,'P2':10,'FB':17,'BOTH':17}.get(section):raise ValueError('Upload every reviewed WhatsApp photo.')
                if any(not isinstance(v,str) for v in values) or len(set(values))!=len(values):raise ValueError('Use a different photo in every WhatsApp position.')
                if not isinstance(caption,str) or len(caption)>5000 or not isinstance(title,str) or len(title)>100:raise ValueError('Shorten the WhatsApp title or caption.')
                for ident in values:
                    _,asset=self.s.media_path(ident)
                    if not asset['type'].startswith('image/'):raise ValueError('Choose photos for WhatsApp.')
                whatsapp={'mode':section,'media':values.copy(),'caption':caption,'title':title,'status':'manual_ready'}
            for platform in platforms:
                groups=media.get(platform,{})
                if not isinstance(groups,dict):raise ValueError('Upload every selected photo sequence.')
                for mode in posting_modes(platform,section):
                    values=groups.get(mode)
                    specs.append({'platform':platform,'mode':mode,'media':values,'caption':data.get('caption',''),
                        'title':str(data.get('title','Daily darshan'))[:80]+(' · Portrait' if mode=='P1' else ' · Landscape' if mode=='P2' else '')})
            before=copy.deepcopy(self.s.data);settings=copy.deepcopy(self.data)
            try:
                jobs=[self.prepare(spec,_persist=False) for spec in specs]
                batch={'id':secrets.token_hex(12),'revision':1,'section':section,'jobs':[j['id'] for j in jobs],
                       'revisions':{j['id']:j['revision'] for j in jobs},'status':'draft','created_at':now_ist().isoformat(),'error':''}
                if whatsapp is not None:batch['whatsapp']=whatsapp
                self.data.setdefault('batches',[]).append(batch)
                self.data['batches']=self.data['batches'][-30:]
                self.s.persist();self.persist()
                return copy.deepcopy(batch)
            except Exception:
                self.s.data=before;self.data=settings;self.s.persist();self.persist();raise

    def send_batch(self,data):
        with self.c.lock,self.s.lock:
            self.ready()
            batch=next((b for b in self.data.get('batches',[]) if b['id']==data.get('id')),None)
            if not batch or batch['status']!='draft' or data.get('revision')!=batch['revision'] or data.get('confirmed') is not True:
                raise ValueError('Review this batch first. A started batch cannot be sent again.')
            if self.s.busy or self.s.live_blocked():raise ValueError('Wait for the current operation or live session to finish before posting.')
            jobs=[self.s.job(i) for i in batch['jobs']]
            for job in jobs:
                if job['id'] not in self.data.get('jobs',[]) or job['revision']!=batch['revisions'][job['id']]:raise ValueError('A draft changed after the batch preview. Prepare a new review.')
                self.validate_send(job)
            before=copy.deepcopy(self.s.data)
            try:
                for job in jobs:self.approve_job(job)
            except Exception:self.s.data=before;self.s.persist();raise
            api_jobs=[job for job in jobs if job.get('delivery')!='manual']
            for job in api_jobs:job.update(status='publishing',error='')
            batch['status']='publishing' if api_jobs else 'manual_ready';batch['error']=''
            self.s.persist();self.persist()
            frozen=[copy.deepcopy(job) for job in api_jobs];cfg=copy.deepcopy(self.c.cfg)
            cfg['telegram_channel']=self.data.get('telegram',{}).get('channel','')
            def work():
                index=0
                try:
                    for index,item in enumerate(frozen):
                        self.publisher(item)(cfg,self.c.vault,self.s,self.s.stop).publish(item)
                        with self.s.lock:self.s.job(item['id'])['status']='published';self.s.persist()
                    with self.s.lock:
                        batch['status']='manual_ready' if batch.get('whatsapp') or any(j.get('delivery')=='manual' for j in jobs) else 'completed';self.persist()
                except Exception as exc:
                    with self.s.lock:
                        error=self.s.safe_failure(exc)
                        self.s.job(frozen[index]['id']).update(status='needs_review',error=error)
                        # No request was started for the remaining items.
                        for item in frozen[index+1:]:self.s.job(item['id']).update(status='draft',approved_at=None,targets={})
                        batch.update(status='needs_review',error=error);self.s.persist();self.persist()
            if api_jobs:self.s.worker=threading.Thread(target=work,daemon=True);self.s.worker.start()
            return {'ok':True,'status':batch['status']}

    def prepare_export(self,data):
        with self.c.lock,self.s.lock:
            self.ready();mode=data.get('mode');media=data.get('media');caption=data.get('caption','');title=data.get('title','Daily darshan')
            if mode not in ('P1','P2','FB','BOTH') or not isinstance(media,list) or len(media)!={'P1':7,'P2':10,'FB':17,'BOTH':17}[mode]:raise ValueError('Upload every photo for the selected download.')
            if any(not isinstance(m,str) for m in media) or len(set(media))!=len(media):raise ValueError('Use a different photo in every selected position.')
            if not isinstance(caption,str) or len(caption)>5000 or not isinstance(title,str) or len(title)>100:raise ValueError('Shorten the title or caption.')
            for ident in media:
                _,asset=self.s.media_path(ident)
                if not asset['type'].startswith('image/'):raise ValueError('Choose photos for the package.')
            self.exports={k:v for k,v in self.exports.items() if v['expires']>time.monotonic()}
            if len(self.exports)>=10:self.exports.pop(next(iter(self.exports)))
            ident=secrets.token_hex(12)
            self.exports[ident]={'expires':time.monotonic()+900,'mode':mode,'job':{'id':ident,'title':title,'caption':caption,'media':media,
                'platforms':[],'publish_at':'','delivery':'download','revision':1}}
            return {'id':ident,'url':'/api/studio/export/'+ident,'photos':len(media),'mode':mode}

    def export_package(self,ident):
        with self.c.lock,self.s.lock:
            self.ready();item=self.exports.get(ident)
            if not item or item['expires']<=time.monotonic():raise ValueError('Prepare the photo download again; this local link expired.')
            job=copy.deepcopy(item['job']);groups=[('01_Portrait',7),('02_Landscape',10)] if item['mode']=='BOTH' else None
        return self.s.export_post(ident,_job=job,groups=groups)
