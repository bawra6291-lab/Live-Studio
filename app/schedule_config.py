"""Validated daily plans. Existing installations keep manual ending by default."""
from copy import deepcopy
from datetime import date, timedelta
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

def calendar_date(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):raise ValueError('Use calendar dates in YYYY-MM-DD format.')
    try:return date.fromisoformat(value)
    except ValueError:raise ValueError('Invalid calendar date.') from None

def occurs_on(slot,day):
    if not slot.get('enabled',True) or day.isoformat() in slot.get('skip_dates',[]):return False
    repeat=slot.get('repeat','daily')
    if repeat=='once':return day.isoformat()==slot.get('on_date')
    return repeat=='daily' or day.weekday() in slot.get('weekdays',[])

def upcoming(schedule,now,days=32,limit=100):
    """Pure calendar preview: no platform calls, credentials or resource creation."""
    rows=[]
    for offset in range(days):
        day=now.date()+timedelta(days=offset)
        for slot in schedule:
            due=slot_time(day,slot)
            if occurs_on(slot,day) and due>=now:
                rows.append({'id':slot['id'],'name':slot['name'],'due':due.isoformat(),
                    'prepare_at':(due-timedelta(minutes=slot.get('prepare_minutes',5))).isoformat(),
                    'end_at':end_time(day,slot).isoformat() if end_time(day,slot) else None,
                    'camera_actions':slot['camera_actions'],'at':slot['at']})
        if len(rows)>=limit:break
    return sorted(rows,key=lambda row:row['due'])[:limit]

def validate_schedule(raw):
    if not isinstance(raw,list) or len(raw)>24:raise ValueError('Use at most 24 daily programs.')
    output=[];seen=set();names=set()
    for row in raw:
        if not isinstance(row,dict):raise ValueError('Invalid program.')
        legacy=next((s for s in SLOTS if s['id']==row.get('id')),{})
        ident=row.get('id','')
        if not isinstance(ident,str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,47}',ident) or ident in seen:raise ValueError('Invalid/duplicate program ID.')
        name=row.get('name',legacy.get('name',''))
        reference=row.get('reference',legacy.get('reference',''))
        template=row.get('title_template','')
        if not isinstance(name,str) or not name.strip() or len(name)>60 or any(ord(c)<32 for c in name):raise ValueError('Program name must be 1–60 characters.')
        if name.strip().casefold() in names:raise ValueError('Give each program a different name.')
        names.add(name.strip().casefold())
        if not isinstance(reference,str) or not re.fullmatch(r'[A-Za-z0-9_-]{11}',reference):raise ValueError('Enter the 11-character YouTube reference livestream ID from your channel.')
        if not isinstance(template,str) or len(template)>100:raise ValueError('Title template must be at most 100 characters.')
        if template:
            expanded=template.replace('{date}','28th Sept 2026').replace('{program}',name.strip())
            if '{' in expanded or '}' in expanded or len(expanded)>100 or not expanded.strip() or any(ord(c)<32 or c in '<>' for c in expanded):raise ValueError('Use only {date} and {program}; the expanded title must be at most 100 characters.')
        elif not legacy:raise ValueError('Enter a title template, for example {date} | {program}.')
        base=dict(id=ident,name=name.strip(),reference=reference)
        if template:base['title_template']=template
        repeat=row.get('repeat','daily');lead=row.get('prepare_minutes',5)
        if repeat not in ('daily','weekdays','once'):raise ValueError('Choose daily, selected weekdays or one date.')
        if type(lead)!=int or not 5<=lead<=60:raise ValueError('Preparation must begin 5–60 minutes before start.')
        # Omit default fields to preserve frozen legacy plans byte-for-byte.
        if repeat!='daily':base['repeat']=repeat
        if lead!=5:base['prepare_minutes']=lead
        if repeat=='once':base['on_date']=calendar_date(row.get('on_date')).isoformat()
        if repeat=='weekdays':
            weekdays=row.get('weekdays')
            if not isinstance(weekdays,list) or not weekdays or any(type(d)!=int or not 0<=d<=6 for d in weekdays):raise ValueError('Select at least one weekday (Monday=0, Sunday=6).')
            base['weekdays']=sorted(set(weekdays))
        skip=row.get('skip_dates',[])
        if not isinstance(skip,list) or len(skip)>366:raise ValueError('Use at most 366 skipped dates.')
        if skip:base['skip_dates']=sorted(set(calendar_date(d).isoformat() for d in skip))
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
    # 400 days covers weekly patterns even after the maximum 366 exceptions.
    # Include far-future one-off dates and their neighbours as well.
    from core import now_ist
    anchor=now_ist().date();days={anchor+timedelta(days=i) for i in range(-1,400)}
    for s in output:
        if s.get('repeat')=='once':days.update(calendar_date(s['on_date'])+timedelta(days=i) for i in (-1,0,1))
    events=sorted(((slot_time(d,s),s) for d in days for s in output if occurs_on(s,d)),key=lambda x:(x[0],x[1]['id']))
    for (due,s),(following,n) in zip(events,events[1:]):
        prep=following-timedelta(minutes=n.get('prepare_minutes',5))
        if prep<=due:raise ValueError('Start times must leave room for the next program’s preparation (at least 6 minutes with default preparation).')
        if s['end_at'] and end_time(due.date(),s)>prep:raise ValueError('End the previous run before the next preparation begins (5 minutes before start by default).')
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
