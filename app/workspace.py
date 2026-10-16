"""One local workspace per Windows user; legacy settings keep their credential service."""
import json, re, uuid
from config import DEFAULTS
from core import atomic_json

IDENTITY_FIELDS = ('youtube_channel_id', 'facebook_page_id', 'youtube_stream_title',
                   'obs_profile', 'obs_collection', 'obs_exe', 'obs_port', 'fb_target', 'camera_url', 'camera_channel')

def load_settings(path):
    exists = path.exists()
    saved = json.loads(path.read_text('utf-8')) if exists else {}
    if not isinstance(saved, dict): raise ValueError('Settings must be an object.')
    cfg = {**DEFAULTS, **saved}
    if 'workspace_schema' not in saved:
        cfg.update(workspace_schema=1, workspace_id=uuid.uuid4().hex, legacy_setup=exists)
        if exists:
            # Preserve the old account binding, schedule, armed preference and secrets.
            cfg.update(workspace_name='ISKCON Kolkata', facebook_page_id='113962385367196',
                       youtube_stream_title='YouTube Official Livestream', camera_channel='1',
                       credential_service='ISKCON-Live-Start')
            backup = path.with_name('settings.before-workspace-migration.json')
            if not backup.exists(): backup.write_bytes(path.read_bytes())
        else:
            cfg.update(schedule=[], armed=False, credential_service='Live-Desk-'+cfg['workspace_id'],
                       obs_collection='', camera_url='')
        atomic_json(path, cfg)
    if cfg.get('workspace_schema') != 1: raise ValueError('Unsupported workspace settings version.')
    if not re.fullmatch(r'(?:ISKCON-Live-Start|Live-Desk-[a-f0-9]{32})', cfg.get('credential_service','')):
        raise ValueError('Invalid credential workspace.')
    return cfg

def validate_settings(cfg):
    if not cfg.get('workspace_name') or len(cfg['workspace_name']) > 80:
        raise ValueError('Workspace name must be 1–80 characters.')
    channel = cfg.get('youtube_channel_id','')
    if channel and not re.fullmatch(r'UC[A-Za-z0-9_-]{22}', channel):
        raise ValueError('Enter the YouTube channel ID beginning with UC (24 characters).')
    page = cfg.get('facebook_page_id','')
    if page and not re.fullmatch(r'[0-9]{5,30}', page): raise ValueError('Enter the numeric Facebook Page ID.')
    if len(cfg.get('youtube_stream_title','')) > 100: raise ValueError('Stream key name must be at most 100 characters.')
    if not re.fullmatch(r'[1-9][0-9]?', cfg.get('camera_channel','')):
        raise ValueError('Camera channel must be 1–99.')

def setup_steps(cfg, checked=False):
    return [
        {'label':'Save your channel ID, Facebook Page ID and existing stream key name',
         'done':bool((cfg.get('youtube_channel_id') or cfg.get('legacy_setup')) and cfg.get('facebook_page_id') and cfg.get('youtube_stream_title'))},
        {'label':'Save OBS profile, scene collection and program scene',
         'done':all(bool(cfg.get(k)) for k in ('obs_exe','obs_profile','obs_collection','obs_scene','fb_target'))},
        {'label':'Add at least one enabled program in Schedule',
         'done':any(s.get('enabled',True) for s in cfg.get('schedule', [])) if 'schedule' in cfg else bool(cfg.get('legacy_setup'))},
        {'label':'Connect YouTube, save a Page token, then pass Check connections', 'done':bool(checked)},
    ]
