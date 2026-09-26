"""Daily scheduler with explicit, opt-in end times and camera actions."""
from __future__ import annotations
import json, re, os, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30))
SLOTS = [
    dict(id='mangal', name='Mangal Arati Darshan', at='04:30', reference='P8-DKvGQLDs'),
    dict(id='darshan', name='Darshan Arati & Guru Puja', at='07:30', reference='KZRUBssugnk'),
    dict(id='rajbhog', name='Rajbhog Arati', at='12:00', reference='F_lPWbVnx4U'),
    dict(id='sandhya', name='Sandhya Arati', at='18:00', reference='XDfqL9VUJGw'),
]

def now_ist(): return datetime.now(IST)
def date_prefix(day):
    n = day.day
    suffix = 'th' if 10 <= n % 100 <= 20 else {1:'st',2:'nd',3:'rd'}.get(n % 10,'th')
    month = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sept','Oct','Nov','Dec'][day.month-1]
    return f'{n}{suffix} {month} {day.year}'

def title_for(source_title, slot, day):
    # Preserve the entire original program/channel suffix, replacing only its date.
    pattern = r'^\s*\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+\d{4}\s*\|\s*'
    if not re.match(pattern, source_title, re.I):
        raise RuntimeError('Reference title has an unrecognised date. Edit the reference title or ask for help.')
    if slot['name'].casefold() not in source_title.casefold():
        raise RuntimeError('Reference title does not match this program.')
    result = re.sub(pattern, date_prefix(day)+' | ', source_title, count=1, flags=re.I)
    if len(result) > 100: raise RuntimeError('YouTube title is longer than 100 characters.')
    return result

def slot_time(day, slot):
    h,m = map(int,slot['at'].split(':'))
    return datetime(day.year,day.month,day.day,h,m,tzinfo=IST)

def atomic_json(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(data,indent=2), encoding='utf-8')
    os.replace(temp,path)

class Journal:
    def __init__(self, path):
        self.path=Path(path)
        self.data=json.loads(self.path.read_text('utf-8')) if self.path.exists() else {}
    def key(self, slot, day): return f'{day.isoformat()}:{slot["id"]}'
    def get(self, slot, day): return self.data.get(self.key(slot,day),{})
    def put(self, slot, day, **changes):
        key=self.key(slot,day)
        self.data.setdefault(key,{}).update(changes)
        atomic_json(self.path,self.data)
        return self.data[key]

def safe_error(exc):
    # Third-party errors may contain request URLs or credentials.
    if type(exc).__module__ == 'connections' and type(exc).__name__ == 'SetupError':
        return str(exc)
    return type(exc).__name__ + ': operation failed; inspect the platforms before retrying.'

class Scheduler:
    """Snapshot each started plan; never blindly replay an ambiguous external write."""
    def __init__(self, service, journal, log=print, cancelled=lambda:False, clock=None, slots=None, grace_seconds=120):
        from schedule_config import get_schedule
        self.service,self.journal,self.log,self.cancelled=service,journal,log,cancelled
        self.clock=clock or (lambda:now_ist());self.slots=slots if slots is not None else get_schedule({})
        self.grace=grace_seconds
    def tick(self,now):
        # Previous day handles overnight ends; tomorrow handles preparation before midnight.
        for offset in (-1,0,1):
            day=now.date()+timedelta(days=offset)
            for slot in self.slots:
                if self.cancelled():return
                if offset==-1 and not self.journal.get(slot,day):continue
                self.run_slot(slot,day,now)
    def run_slot(self,current,day,now):
        from copy import deepcopy
        from schedule_config import action_time,end_time,get_schedule
        rec=self.journal.get(current,day)
        if not current['enabled'] and not rec.get('plan'):return
        plan=rec.get('plan',current);due=slot_time(day,plan)
        clocks=[action_time(day,a,rec) for a in plan['camera_actions'] if a['timing']=='clock']
        if now<min([due-timedelta(minutes=5)]+clocks):return
        def put(**kw):return self.journal.put(current,day,**kw)
        if not rec.get('plan'):
            # Old journals never gain newly configured ending/movement permissions.
            if rec and rec.get('phase') not in ('new','missed'):
                plan=next(x for x in get_schedule({}) if x['id']==current['id']);due=slot_time(day,plan)
            states={}
            if rec.get('phase')=='done':states['0']=rec.get('patrol_result','sent')
            if rec.get('phase')=='patrol_sending':states['0']='needs_review'
            rec=put(plan=deepcopy(plan),camera_states=states,phase=rec.get('phase','new'),scheduled_at=due.isoformat())
        phase=rec.get('phase','new')
        if phase in ('preparing','starting','patrol_sending'):
            rec=put(phase='needs_review',last_error='Interrupted operation. Inspect OBS and both platforms before retrying.')
            self.log(plan['name']+': interrupted operation; manual review required.');phase='needs_review'
        end=end_time(day,plan)
        # Camera steps scheduled before live (explicit "Only while live" off).
        self.camera_steps(current,day,now,rec,pre_start=True)
        if phase in ('new','prepared'):
            if now>due+timedelta(seconds=self.grace):
                rec=put(phase='missed',last_error=f'Start window passed: scheduled {due.isoformat()}, worker reached it at {now.isoformat()}.')
                self.log(plan['name']+': skipped; start window passed. Check app launch time, pause state and PC/network availability.')
            elif now>=due-timedelta(minutes=5):
                try:
                    if phase=='new':
                        put(phase='preparing',stage='prepare',attempt_at=now.isoformat())
                        self.log(plan['name']+': preparing broadcasts for '+plan['at']+' IST.')
                        prepared=self.service.prepare(plan,due,put)
                        rec=put(**prepared,phase='prepared',stage='waiting_for_start')
                        self.log(plan['name']+': prepared; waiting for '+plan['at']+' IST.')
                    actual=self.clock()
                    if actual>=due and not self.cancelled():
                        if actual>due+timedelta(seconds=self.grace):
                            rec=put(phase='missed',last_error='Preparation finished after the allowed start window.')
                            self.log(plan['name']+': preparation finished too late; start skipped.')
                        else:
                            rec=put(phase='starting',stage='starting_obs')
                            self.service.persist_run=put
                            self.service.start(rec)
                            confirmed=self.clock()
                            rec=put(phase='live',stage='live_confirmed',confirmed_at=confirmed.isoformat(),patrol_due=(confirmed+timedelta(seconds=120)).isoformat())
                            self.log(plan['name']+': BOTH destinations LIVE confirmed. '+('Scheduled end '+plan['end_at']+' IST.' if end else 'End manually.'))
                except Exception as exc:
                    rec=put(phase='needs_review',last_error=safe_error(exc))
                    self.log(plan['name']+': '+safe_error(exc)+' Inspect OBS and both platforms before retrying.')
        if self.cancelled():return
        rec=self.journal.get(current,day)
        # Never start a patrol at/after the end; an explicit patrol-stop at the end runs first.
        self.camera_steps(current,day,self.clock(),rec)
        rec=self.journal.get(current,day)
        if end and self.clock()>=end and rec.get('end_state') not in ('ended','missed','needs_review','not_started'):
            if rec.get('end_state')=='sending':
                put(end_state='needs_review',last_error='Interrupted end request. Inspect both platforms.');return
            if self.clock()>end+timedelta(minutes=2):
                put(end_state='missed',last_error='End window missed. End the live manually.')
                self.log(plan['name']+': end window missed; end manually.');return
            if not rec.get('obs_start_epoch') or not rec.get('yt_id') or not rec.get('fb_id'):
                put(end_state='not_started');self.log(plan['name']+': automatic end skipped; this app did not record starting this run.');return
            try:
                put(end_state='sending',stage='ending');self.service.end(rec,put)
                put(end_state='ended',phase='ended',ended_at=self.clock().isoformat(),stage='finished')
                self.log(plan['name']+': scheduled end confirmed for YouTube, Facebook and the associated OBS outputs.')
            except Exception as exc:
                put(end_state='needs_review',last_error=safe_error(exc))
                self.log(plan['name']+': end needs review. '+safe_error(exc))
    def camera_steps(self,slot,day,now,rec,pre_start=False):
        from schedule_config import action_time,end_time
        plan=rec['plan'];states=dict(rec.get('camera_states',{}));end=end_time(day,plan)
        for index,action in enumerate(plan['camera_actions']):
            if self.cancelled():return
            is_pre=action['timing']=='clock' and not action['only_if_live']
            if is_pre!=pre_start:continue
            key=str(index);status=states.get(key,'pending')
            if status=='sending':
                states[key]='needs_review';self.journal.put(slot,day,camera_states=states,last_error='Interrupted camera request; inspect camera.');continue
            if status!='pending':continue
            due=action_time(day,action,rec)
            if due is None or now<due:continue
            if now>due+timedelta(minutes=2):states[key]='missed'
            elif end and now>=end and action['kind']!='patrol_stop':states[key]='skipped_at_end'
            else:
                try:
                    if action['only_if_live'] and (not rec.get('confirmed_at') and rec.get('phase') not in ('live','done') or not rec.get('yt_id') or not rec.get('fb_id')):
                        # Wait within the camera window while a scheduled start finishes.
                        continue
                    if action['only_if_live'] and not self.service.both_live(rec):states[key]='skipped_not_live'
                    else:
                        states[key]='sending';self.journal.put(slot,day,camera_states=dict(states))
                        if hasattr(self.service,'camera_action'):self.service.camera_action(action)
                        elif action['kind']=='patrol_start' and action['number']==8:self.service.camera_start()
                        else:raise RuntimeError('Camera action adapter unavailable')
                        states[key]='sent'
                        self.log(f'{plan["name"]}: camera {action["kind"]} {action["number"]} acknowledged.')
                except Exception as exc:
                    states[key]='needs_review'
                    self.journal.put(slot,day,last_error=safe_error(exc))
                    self.log(plan['name']+': camera needs review. '+safe_error(exc))
            self.journal.put(slot,day,camera_states=dict(states),patrol_result=states.get('0',''))
