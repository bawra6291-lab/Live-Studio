"""Sign a tested aligned APK locally with the saved private maintainer key.
Never uploads keys or updates a release feed. Password is supplied through env.
"""
import argparse,hashlib,os,re,subprocess
from pathlib import Path

EXPECTED='a4cedc315f39eb7d3093880ab037ea82f83bb0f140722f2b971a21c7f92807f9'
parser=argparse.ArgumentParser()
parser.add_argument('--apksigner-jar',type=Path,required=True)
parser.add_argument('--aligned-apk',type=Path,required=True)
parser.add_argument('--keystore',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
if not os.environ.get('LIVE_DESK_STORE_PASS'):parser.error('Provide LIVE_DESK_STORE_PASS in the environment, not in arguments.')
args.output.parent.mkdir(parents=True,exist_ok=True)
subprocess.run(['java','-jar',str(args.apksigner_jar),'sign','--ks',str(args.keystore),'--ks-key-alias','livedeskmobile','--ks-pass','env:LIVE_DESK_STORE_PASS','--out',str(args.output),str(args.aligned_apk)],check=True)
result=subprocess.check_output(['java','-jar',str(args.apksigner_jar),'verify','--verbose','--print-certs',str(args.output)],text=True)
match=re.search(r'Signer #1 certificate SHA-256 digest: ([a-f0-9]+)',result)
if not match or match[1]!=EXPECTED:
    args.output.unlink(missing_ok=True);raise SystemExit('Unexpected signer; APK removed. Use the privately backed-up key.')
args.output.with_name('signature.txt').write_text(result)
args.output.with_name('SHA256SUMS').write_text(hashlib.sha256(args.output.read_bytes()).hexdigest()+'  '+args.output.name+'\n')
print('Verified signed APK: '+str(args.output))
