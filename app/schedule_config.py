"""Validated daily plans. Existing installations keep manual ending by default."""
from copy import deepcopy
from datetime import timedelta
import re
from core import SLOTS, slot_time

DEFAULT_ACTION={'kind':'patrol_start','number':8,'timing':'after_live','delay_seconds':120,'at':'','next_day':False,'only_if_live':True}

def get_schedule(cfg):
    raw=cfg.get('schedule')
    if raw is None:
        raw=[{**s,'enabled':True,'end_at':'','end_next_day':False,'camera_actions':[deepcopy(DEFAULT_ACTION)]} for s in SLOTS]
    return validate_schedule(raw)

def clock(value,label):
    if not isinstance(value,str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',value):raise ValueError(label+' must use HH:MM (24-hour IST).')
    h,m=map(int,value.split(':'));return h*60+m

def validate_schedule(raw):
    if not isinstance(raw,list) or len(raw)!=4:raise ValueError('Keep all four program rows; switch unwanted programs off.')
    output=[];seen=set()
    for row in raw:
        if not isinstance(row,dict):raise ValueError('Invalid program.')
        base=next((s for s in SLOTS if s['id']==row.get('id')),None)
        if not base or base['id'] in seen:raise ValueError('Invalid/duplicate program.')
        seen.add(base['id']);start=clock(row.get('at'),base['name']+' start')
        enabled=row.get('enabled',True);next_day=row.get('end_next_day',False)
        if type(enabled)!=bool or type(next_day)!=bool:raise ValueError('Invalid enabled/next-day choice.')
        end=row.get('end_at','');end_min=None
        if end:
            end_min=clock(end,'End time')+(1440 if next_day else 0)
            if not start<end_min<start+1440:raise ValueError('End must be after start and less than 24 hours later. Select next day for overnight runs.')
        elif next_day:raise ValueError('Enter an end time or turn off next day.')
        actions=row.get('camera_actions',[])
        if not isinstance(actions,list) or len(actions)>8:raise ValueError('Use at most 8 camera actions per program.')
        clean=[];action_times=set()
        for a in actions:
            if not isinstance(a,dict):raise ValueError('Invalid camera action.')
            kind=a.get('kind');number=a.get('number');timing=a.get('timing')
            if kind not in ('patrol_start','patrol_stop','preset'):raise ValueError('Choose patrol start, patrol stop or go to preset.')
            # Presets 33–99 include camera service commands (e.g. reboot); never expose these as positions.
            limit=32 if kind=='preset' else 8
            if type(number)!=int or not 1<=number<=limit:raise ValueError(f'{kind}: number must be 1–{limit}.')
            if timing not in ('clock','after_live'):raise ValueError('Invalid camera timing.')
            nd=a.get('next_day',False);only=a.get('only_if_live',True)
            if type(nd)!=bool or type(only)!=bool:raise ValueError('Invalid camera checkbox.')
            delay=a.get('delay_seconds',120);at=a.get('at','')
            if timing=='after_live':
                if type(delay)!=int or not 0<=delay<=43200:raise ValueError('Camera delay must be 0–43200 seconds.')
                if end_min is not None and start*60+delay>=end_min*60:raise ValueError('Camera delay must be before the end time.')
                at='';nd=False;only=True;key=('after_live',delay)
            else:
                moment=clock(at,'Camera time')+(1440 if nd else 0)
                if moment>start+1440:raise ValueError('Camera time must be within this program day or its overnight run.')
                if end_min is not None and moment>end_min:raise ValueError('Camera action must be at or before the end time.')
                if only and moment<start:raise ValueError('For a camera move before live starts, untick Only while both live.')
                if end_min is not None and moment==end_min and kind!='patrol_stop':raise ValueError('At the end time, only patrol stop is allowed.')
                delay=0;key=('clock',moment)
            if key in action_times:raise ValueError('Give camera actions different times.')
            action_times.add(key)
            clean.append(dict(kind=kind,number=number,timing=timing,delay_seconds=delay,at=at,next_day=nd,only_if_live=only))
        output.append({**base,'at':row['at'],'enabled':enabled,'end_at':end,'end_next_day':next_day,'camera_actions':clean})
    active=sorted((s for s in output if s['enabled']),key=lambda s:s['at'])
    for i,s in enumerate(active):
        start=clock(s['at'],'Start');n=active[(i+1)%len(active)]
        following=clock(n['at'],'Start')+(1440 if i==len(active)-1 else 0)
        if following-start<6:raise ValueError('Start times must be at least 6 minutes apart to allow preparation.')
        if s['end_at']:
            end=clock(s['end_at'],'End')+(1440 if s['end_next_day'] else 0)
            if end>following-5:raise ValueError('End the previous run at least 5 minutes before the next start.')
    return sorted(output,key=lambda s:s['at'])

def end_time(day,slot):
    if not slot.get('end_at'):return None
    return slot_time(day+timedelta(days=bool(slot.get('end_next_day'))),{'at':slot['end_at']})

def action_time(day,action,record):
    from datetime import datetime
    if action['timing']=='clock':return slot_time(day+timedelta(days=action['next_day']),{'at':action['at']})
    if record.get('confirmed_at'):return datetime.fromisoformat(record['confirmed_at'])+timedelta(seconds=action['delay_seconds'])
    # v0.1/v0.2 journal migration: retain the already-authorized Patrol 8 due time.
    if record.get('patrol_due') and action['kind']=='patrol_start' and action['number']==8:return datetime.fromisoformat(record['patrol_due'])
    return None
