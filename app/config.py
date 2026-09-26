"""Shared paths: updates keep the existing Windows settings and credential names."""
import os
from pathlib import Path
BASE = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'ISKCON-Live-Start'
CONFIG = BASE / 'settings.json'
DEFAULTS = {
    'obs_exe': r'C:\Program Files\obs-studio\bin\64bit\obs64.exe',
    'obs_port': '4455', 'obs_profile': 'Untitled', 'obs_collection': 'Temple Live',
    'obs_scene': 'Main', 'fb_target': 'FB Live', 'graph_version': 'v23.0',
    'google_client_file': '', 'camera_url': 'http://192.168.29.10',
    'camera_user': 'admin', 'armed': False,
}
