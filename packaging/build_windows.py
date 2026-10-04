"""Build a per-user Windows installer with a private, relocatable CPython runtime."""
import argparse,json,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def build(output,compiler):
    if os.name!='nt':raise SystemExit('Build on Windows with Python 3.12 and Inno Setup 6.')
    output=Path(output).resolve();stage=output/'stage';runtime=stage/'runtime';app=stage/'app'
    if stage.exists():shutil.rmtree(stage)
    stage.mkdir(parents=True);shutil.copytree(sys.base_prefix,runtime,ignore=shutil.ignore_patterns('__pycache__','*.pyc','Doc','Tools'))
    # A full installation includes Tk, SSL, Windows DLLs and the installed dependencies.
    # Keep the runtime beside app/ so in-app source upgrades never replace the running interpreter.
    shutil.copytree(ROOT/'app',app,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    code="import sys,ssl,tkinter,requests,websocket,keyring,win32api,google.auth,google_auth_oauthlib; from pathlib import Path; assert Path(sys.prefix).resolve()==Path(sys.executable).resolve().parent; r=tkinter.Tk(); r.withdraw(); r.destroy(); print(sys.version)"
    subprocess.run([str(runtime/'python.exe'),'-E','-s','-c',code],check=True,cwd=str(stage))
    # Record the actual wheel set in the artifact, for review/reproducibility.
    freeze=subprocess.check_output([str(runtime/'python.exe'),'-E','-s','-m','pip','freeze'],text=True)
    (stage/'runtime-dependencies.txt').write_text(freeze,encoding='utf-8')
    (stage/'RUNTIME-NOTICE.txt').write_text('This installer includes CPython and third-party dependencies. Their licenses are included in runtime/ and runtime/Lib/site-packages/*.dist-info/. Saved credentials and settings are outside this installation and are not removed by uninstall.\n',encoding='utf-8')
    version=json.loads((app/'version.json').read_text())['version']
    subprocess.run([compiler,'/DStage='+str(stage),'/DOutput='+str(output),'/DAppVersion='+version,str(ROOT/'packaging'/'LiveDesk.iss')],check=True)
    return output/('Live-Desk-'+version+'-Setup.exe')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--compiler',default=r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe');args=p.parse_args();print(build(args.output,args.compiler))
