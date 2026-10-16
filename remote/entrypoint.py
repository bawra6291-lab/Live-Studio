"""Prepare a fresh mounted volume, then permanently drop container privileges."""
import os
from pathlib import Path
root=Path(os.environ.get('LIVE_DESK_DB','/data/relay.db')).parent
root.mkdir(parents=True,exist_ok=True)
if os.geteuid()==0:
    os.chown(root,10001,10001);os.chmod(root,0o700)
    os.setgroups([]);os.setgid(10001);os.setuid(10001)
os.execvp('python',['python','server.py','serve','--host','0.0.0.0'])
