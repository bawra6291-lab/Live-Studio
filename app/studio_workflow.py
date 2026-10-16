"""Real local workflow helpers adapted from the supplied daily-darshan design."""
import copy, hashlib, json
from core import now_ist
from telegram_publish import caption_length

TEMPLATE_KEYS=('facebook','instagram_P1','instagram_P2','telegram','youtube_P1','youtube_P2')


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


class StudioWorkflow:
    def save_workflow(self,values):
        if not isinstance(values,dict):raise ValueError('Invalid workflow settings.')
        templates=values.get('templates',{})
        if not isinstance(templates,dict) or any(k not in TEMPLATE_KEYS or not isinstance(v,str) or len(v)>5000 for k,v in templates.items()):
            raise ValueError('Use supported caption templates up to 5000 characters.')
        audio=values.get('instagram_audio',{})
        if not isinstance(audio,dict) or type(audio.get('required',False))!=bool or not isinstance(audio.get('reference',''),str) or len(audio.get('reference',''))>300:
            raise ValueError('Use a saved Instagram audio reference up to 300 characters.')
        if audio.get('required') and not audio.get('reference','').strip():raise ValueError('Add the saved audio title or link first.')
        order=values.get('telegram_order','portrait')
        if order not in ('portrait','mixed'):raise ValueError('Choose a supported Telegram sequence.')
        return {'telegram_order':order,'templates':copy.deepcopy(templates),'instagram_audio':{'required':audio.get('required',False),'reference':audio.get('reference','').strip()}}

    def pretest(self,data):
        """No network calls, approvals, uploads or publishing, including in Chrome."""
        with self.c.lock,self.s.lock:
            self.ready();ids=data.get('jobs',[])
            if not isinstance(ids,list) or len(ids)>10 or any(not isinstance(i,str) for i in ids) or len(ids)!=len(set(ids)):
                raise ValueError('Choose up to ten saved draft reviews.')
            checks=[]
            def check(name,ok,detail):checks.append({'name':name,'ok':bool(ok),'detail':detail})
            check('PC available',not self.s.busy and not self.s.live_blocked(),'Posting must be idle and live sessions finished.')
            for platform in ('facebook','instagram','youtube','telegram'):
                a=self.accounts.get(platform,{})
                check(platform+' connection',a.get('status')=='verified',a.get('message') or a.get('name') or 'Use Connections to verify this account; this pre-test does not contact the platform.')
            evidence=[]
            for ident in ids:
                if ident not in self.data.get('jobs',[]):raise ValueError('Choose a DARSHANFLOW draft.')
                job=self.s.job(ident);error=''
                try:
                    self.validate_send(job,pretest=True)
                    for media in job['media']:self.s.media_path(media)
                except Exception as exc:error=self.s.safe_failure(exc)
                check(job['platforms'][0]+' draft '+ident[:8],not error,error or 'Saved destination, caption, media hashes and draft state checked. Not published.')
                evidence.append({k:copy.deepcopy(job.get(k)) for k in ('id','revision','media','caption','studio_target','studio_service_date','studio_album_split','studio_audio')})
            if not ids:check('Saved drafts',False,'Prepare an individual or batch preview, then run pre-test to check its exact photos and target.')
            return {'at':now_ist().isoformat(),'checks':checks,'ready':bool(ids) and all(c['ok'] for c in checks if ' connection' not in c['name']),
                    'fingerprint':fingerprint(evidence) if evidence else '',
                    'note':'Local read-only pre-test. Saved connection checks are shown separately; it does not prove a live platform publish or repair Chrome login.'}
