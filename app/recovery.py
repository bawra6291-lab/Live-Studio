"""Read-only run inspection and portable, credential-free configuration backups."""
from copy import deepcopy
import re
from core import now_ist
from schedule_config import get_schedule, validate_schedule
from workspace import validate_settings

# Executable paths, OAuth files, network addresses and credential namespaces are
# intentionally not portable. Import must never introduce a new code path or host.
PORTABLE=('workspace_name','youtube_channel_id','facebook_page_id','youtube_stream_title',
          'obs_profile','obs_collection','obs_scene','fb_target','camera_channel')

def export_backup(cfg):
    return {'format':'live-desk-settings','schema':1,'created_at':now_ist().isoformat(),
        'settings':{k:cfg.get(k,'') for k in PORTABLE},'schedule':get_schedule(cfg),
        'grace_minutes':cfg.get('grace_minutes',2),
        'note':'No passwords, tokens, browser sessions, executable paths, network addresses or run journal. Restore pauses automation; check connections afterwards.'}

def import_backup(data,cfg):
    if not isinstance(data,dict) or data.get('format')!='live-desk-settings' or data.get('schema')!=1:
        raise ValueError('Choose a Live Desk settings backup (schema 1).')
    values=data.get('settings')
    if not isinstance(values,dict) or set(values)-set(PORTABLE):raise ValueError('Backup contains unsupported settings.')
    if any(not isinstance(v,str) or len(v)>2048 for v in values.values()):raise ValueError('Invalid backup setting.')
    result={**deepcopy(cfg),**values,'armed':False,'schedule':validate_schedule(data.get('schedule'))}
    grace=data.get('grace_minutes',2)
    if type(grace)!=int or not 1<=grace<=15:raise ValueError('Invalid late-start allowance.')
    result['grace_minutes']=grace;validate_settings(result)
    return result

def run_history(journal,limit=100):
    rows=[]
    for key,rec in sorted(journal.data.items(),reverse=True)[:limit]:
        plan=rec.get('plan',{});yt=str(rec.get('yt_id',''));fb=str(rec.get('fb_id',''))
        rows.append({'key':key,'name':plan.get('name',key.split(':')[-1]),
            **{k:rec.get(k,'') for k in ('phase','stage','scheduled_at','confirmed_at','ended_at','last_error','reviewed_at')},
            'youtube_url':'https://studio.youtube.com/video/'+yt+'/livestreaming' if re.fullmatch(r'[A-Za-z0-9_-]{11}',yt) else '',
            'facebook_url':'https://www.facebook.com/'+fb if re.fullmatch(r'[0-9_]{5,70}',fb) else '',
            'guide':__import__('insights').recovery_guide(rec),'inspection':rec.get('inspection'), 'reviewed':rec.get('phase')=='reviewed'})
    return rows

def inspect_run(service,record):
    """No launches, preparation, binding changes, camera movement or write APIs."""
    from connections import SetupError
    service.obs.connect(launch=False);service.obs.check_profile()
    main=service.obs.call('GetStreamStatus')
    outputs=service.obs.call('GetOutputList').get('outputs',[])
    obs_active=bool(main.get('outputActive') or any(x.get('outputActive') for x in outputs))
    result={'checked_at':now_ist().isoformat(),'obs_active':obs_active,'youtube':'not recorded','facebook':'not recorded','youtube_id':record.get('yt_id',''),'facebook_id':record.get('fb_id','')}
    if record.get('yt_id'):
        service.yt.owned_channel();event=service.yt.event(record['yt_id'])
        result['youtube']=event['status']['lifeCycleStatus']
    if record.get('fb_id'):
        service.fb.identity()
        if not any(x['id']==record['fb_id'] for x in service.fb.recent()):raise SetupError('Recorded Facebook event is not in this Page’s recent events. Inspect it manually.')
        result['facebook']=service.fb.api('GET',record['fb_id'],{'fields':'status'}).get('status','unknown')
    # Unknown/deleted/unavailable resources do not count as verified inactive.
    result['can_review']=not obs_active and result['youtube'] in ('not recorded','created','ready','complete','revoked') and result['facebook'] in ('not recorded','UNPUBLISHED','SCHEDULED_UNPUBLISHED','VOD','PROCESSING')
    return result
