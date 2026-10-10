"""Shared paths: updates keep the existing Windows settings and credential names."""
import os
from pathlib import Path
BASE = Path(os.environ['LIVE_DESK_DATA_DIR']) if os.environ.get('LIVE_DESK_DATA_DIR') else Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'ISKCON-Live-Start'
CONFIG = BASE / 'settings.json'
DEFAULTS = {
    'obs_exe': r'C:\Program Files\obs-studio\bin\64bit\obs64.exe',
    'obs_port': '4455', 'obs_profile': 'Untitled', 'obs_collection': 'Temple Live',
    'obs_scene': 'Main', 'fb_target': 'FB Live', 'graph_version': 'v23.0',
    'obs_preserve_layout': True,
    'workspace_name':'My Live Desk', 'youtube_channel_id':'', 'facebook_page_id':'',
 'youtube_stream_title':'', 'camera_channel':'1',
 'google_client_file': '', 'camera_url': 'http://192.168.29.10',
    'camera_user': 'admin', 'armed': False,
}
