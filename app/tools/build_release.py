"""Build an updater-ready release and optionally its HTTPS feed. No publishing."""
import argparse,hashlib,json,sys
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from updater import APP_ID, https_url, version_key

def build(source,output,base_url=None,notes=''):
    source=Path(source).resolve();output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    version=json.loads((source/'version.json').read_text('utf-8'))['version'];version_key(version)
    allowed={'.py','.txt','.cmd','.ps1','.json','.css','.js','.svg','.html'}
    files={}
    for p in sorted(source.rglob('*')):
        rel=p.relative_to(source)
        if (not p.is_file() or '__pycache__' in p.parts or any(x.startswith('.') for x in rel.parts)
                or p.suffix not in allowed or str(rel)=='release.json'):continue
        if p.suffix=='.json' and rel.as_posix()!='version.json':continue
        if rel.parts[0] not in ('web','tests','tools') and len(rel.parts)>1:continue
        files[rel.as_posix()]=p.read_bytes()
    release={'app_id':APP_ID,'version':version,'update_format':1,
             'files':{name:hashlib.sha256(data).hexdigest() for name,data in files.items()}}
    archive=output/'ISKCON-Live-Desk.zip'
    with ZipFile(archive,'w',ZIP_DEFLATED) as z:
        for name,data in files.items():z.writestr('ISKCON-Live-Start/'+name,data)
        z.writestr('ISKCON-Live-Start/release.json',json.dumps(release,indent=2))
    if base_url:
        url=https_url(base_url.rstrip('/')+'/ISKCON-Live-Desk.zip')
        manifest={'app_id':APP_ID,'version':version,'update_format':1,'package_url':url,
                  'size':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'notes':notes}
        (output/'latest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return archive

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--base-url');p.add_argument('--notes',default='')
    a=p.parse_args();print(build(Path(__file__).resolve().parents[1],a.output,a.base_url,a.notes))
