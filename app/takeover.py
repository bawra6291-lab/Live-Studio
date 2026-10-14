"""Read-only discovery and explicit attachment of an existing dual-platform live."""
from copy import deepcopy
from datetime import date, datetime, timedelta
import hashlib, json, math
from urllib.parse import urlsplit
from core import IST, slot_time
from schedule_config import action_time, end_time, occurs_on


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def select_plan(schedule, slot_id, day_text, now):
    try: day = date.fromisoformat(day_text)
    except (ValueError, TypeError): raise ValueError('Choose the program start date in IST.') from None
    slot = next((s for s in schedule if s['id'] == slot_id), None)
    if not slot or not occurs_on(slot, day): raise ValueError('Choose an enabled program that runs on this date.')
    due = slot_time(day, slot)
    end = end_time(day, slot)
    following = [slot_time(day + timedelta(days=i), s) - timedelta(minutes=s.get('prepare_minutes', 5))
                 for i in (0, 1) for s in schedule if occurs_on(s, day + timedelta(days=i))
                 and slot_time(day + timedelta(days=i), s) > due]
    cutoff = min([due + timedelta(hours=24)] + following + ([end] if end else []))
    if not due <= now < cutoff:
        raise ValueError('This program is outside its current run window. Check its saved start/end and IST date.')
    return deepcopy(slot), day


def require_unused(journal, slot, day, candidate=None):
    rec = journal.get(slot, day)
    if rec.get('obs_start_epoch') or rec.get('confirmed_at') or rec.get('phase') in ('live', 'done', 'ended', 'reviewed'):
        raise ValueError('This program already has a recorded run. Resume its saved automation or inspect Run history; it cannot be replaced.')
    if rec.get('plan') and rec['plan']!=slot and (rec.get('yt_id') or rec.get('fb_id') or rec.get('camera_states')):
        raise ValueError('The recorded preparation uses a different plan. Inspect that run before taking control.')
    if candidate:
        if any(rec.get(k) and rec[k]!=candidate[k] for k in ('yt_id','fb_id','yt_stream_id')):
            raise ValueError('The running live differs from this program’s recorded preparation. It cannot be replaced.')
        for key,other in journal.data.items():
            if key==journal.key(slot,day):continue
            if other.get('yt_id') == candidate['yt_id'] or other.get('fb_id') == candidate['fb_id']:
                raise ValueError('This live is already associated with another recorded run. Inspect Run history first.')


def stream_parts(url):
    parts = urlsplit(url or '')
    if parts.scheme not in ('rtmp', 'rtmps') or not parts.netloc or '/' not in parts.path.rstrip('/'):
        raise ValueError('Facebook did not provide a verifiable live ingest address.')
    path, key = parts.path.rsplit('/', 1)
    if not key: raise ValueError('Facebook live ingest key is unavailable.')
    return f'{parts.scheme}://{parts.netloc}{path}/', key + ('?' + parts.query if parts.query else '')


def output_epoch(status):
    import time
    duration = status.get('outputDuration')
    if status.get('outputActive') is not True or status.get('outputReconnecting') or type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0:
        raise ValueError('Both OBS streaming outputs must be active, stable and have a readable duration.')
    return time.time() - duration / 1000


def discover(service, now):
    """GETs only. Ingest secrets stay in memory and never enter the preview/journal."""
    service.obs.connect(launch=False)
    service.obs.check_profile()
    channel = service.yt.owned_channel()
    page = service.fb.identity()
    stream = service.yt.stream_for_obs(service.obs.key())
    active = service.yt.list('liveBroadcasts', part='id,snippet,status,contentDetails', broadcastStatus='active', broadcastType='all', maxResults=50)
    if len(active) != 1: raise ValueError('Exactly one YouTube live must be active on the configured channel.')
    yt = active[0]
    if yt.get('snippet', {}).get('channelId') != channel['id'] or yt.get('status', {}).get('lifeCycleStatus') != 'live' or yt.get('contentDetails', {}).get('boundStreamId') != stream['id']:
        raise ValueError('The current YouTube live does not match the configured channel and existing OBS stream key.')
    if not service.yt.stream_active(stream['id']): raise ValueError('YouTube is not receiving the configured OBS stream.')
    rows = [x for x in service.fb.recent() if x.get('status') in ('LIVE', 'LIVE_NOW')]
    if len(rows) != 1: raise ValueError('Exactly one Facebook live must be active on the configured Page.')
    fb = service.fb.api('GET', rows[0]['id'], {'fields': 'id,title,status,secure_stream_url,broadcast_start_time'})
    if fb.get('id') != rows[0]['id'] or fb.get('status') not in ('LIVE', 'LIVE_NOW'):
        raise ValueError('Facebook live changed during the check. Inspect and check again.')
    target = service.obs.plugin_target()[2]
    server, key = stream_parts(fb.get('secure_stream_url'))
    settings = target['service-param']
    if settings.get('server', '').rstrip('/') != server.rstrip('/') or settings.get('key') != key:
        raise ValueError('The configured FB Live output does not match this Facebook live. No control was taken.')
    outputs = [x for x in service.obs.call('GetOutputList').get('outputs', []) if x.get('outputName', '').startswith('multi-output') and x.get('outputActive')]
    if len(outputs) != 1: raise ValueError('Exactly one Facebook/plugin output must be active in OBS.')
    name = outputs[0]['outputName']
    fb_epoch = output_epoch(service.obs.call('GetOutputStatus', outputName=name))
    epoch = output_epoch(service.obs.call('GetStreamStatus'))
    try:
        starts = [datetime.fromisoformat(x.replace('Z', '+00:00')) for x in (yt['snippet']['actualStartTime'], fb['broadcast_start_time'])]
        if any(x.tzinfo is None or not now - timedelta(hours=24) < x <= now for x in starts): raise ValueError()
    except (KeyError, ValueError, TypeError):
        raise ValueError('Actual start times could not be verified on both platforms. No camera timing was assumed.') from None
    record = dict(yt_id=yt['id'], fb_id=fb['id'], yt_stream_id=stream['id'], title=yt['snippet'].get('title', ''),
                  fb_title=fb.get('title', ''), obs_start_epoch=epoch, fb_start_epoch=fb_epoch,
                  fb_output_name=name, fb_target_fingerprint=digest(settings),
                  confirmed_at=max(starts).astimezone(IST).isoformat(), youtube_channel_id=channel['id'], facebook_page_id=page['id'])
    service.verify_run_outputs(record)
    if not service.both_live(record): raise ValueError('Both destinations must still be live before taking control.')
    return record


def same_live(before, after):
    keys = ('yt_id', 'fb_id', 'yt_stream_id', 'fb_output_name', 'fb_target_fingerprint', 'confirmed_at', 'youtube_channel_id', 'facebook_page_id', 'title', 'fb_title')
    return all(before.get(k) == after.get(k) for k in keys) and all(abs(before[k] - after[k]) <= 2 for k in ('obs_start_epoch', 'fb_start_epoch'))


def attach_record(plan, day, observed, now):
    rec = {**deepcopy(observed), 'plan': deepcopy(plan), 'phase': 'live', 'stage': 'existing_live_control',
           'origin': 'manual_takeover', 'adopted_at': now.isoformat(), 'scheduled_at': slot_time(day, plan).isoformat(),
           'last_error': '', 'camera_states': {}}
    for i, action in enumerate(plan['camera_actions']):
        due = action_time(day, action, rec)
        if due is None or due <= now: rec['camera_states'][str(i)] = 'skipped_before_takeover'
    return rec


def preview(record, day):
    return {'name': record['plan']['name'], 'date': day.isoformat(), 'youtube_title': record['title'],
            'facebook_title': record['fb_title'], 'youtube_url': 'https://studio.youtube.com/video/' + record['yt_id'] + '/livestreaming',
            'facebook_url': 'https://www.facebook.com/' + record['fb_id'], 'both_live_at': record['confirmed_at'],
            'end_at': end_time(day, record['plan']).isoformat() if record['plan']['end_at'] else None,
            'camera': [{'label': a['kind'].replace('_', ' ') + ' ' + str(a['number']),
                        'due': action_time(day, a, record).isoformat(), 'state': record['camera_states'].get(str(i), 'pending')}
                       for i, a in enumerate(record['plan']['camera_actions'])]}
