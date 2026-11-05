#!/usr/bin/env python3
"""CI-only edit control; use an isolated checkout on Build under a cap."""
import argparse,json,os,pathlib,subprocess,time
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root',required=True,type=pathlib.Path)
parser.add_argument('--out',required=True,type=pathlib.Path)
parser.add_argument('--launcher',required=True,type=pathlib.Path)
parser.add_argument('--reference-sdk',required=True,type=pathlib.Path)
args=parser.parse_args()
root=args.root.resolve(strict=True);p=args.out.resolve();p.mkdir(parents=True,exist_ok=False)
native=args.launcher.resolve(strict=True);previous=args.reference_sdk.resolve(strict=True)
os.chdir(root)
r={'status':'running','stages':[]}
def save():(p/'ci-edit.json').write_text(json.dumps(r,indent=2)+'\n')
def run(label,cmd,timeout=300):
 start=time.monotonic()
 result=subprocess.run([str(v) for v in cmd],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
 (p/(label+'.log')).write_text(result.stdout+result.stderr)
 r['stages'].append({'name':label,'seconds':time.monotonic()-start,'exit':result.returncode});save()
 assert result.returncode==0,(label,result)
 return result.stdout.strip()
def hashes():
 a=subprocess.check_output(['python3','scripts/sdk-inputs','--root',str(root)],text=True).strip()
 b=subprocess.check_output([str(native),'--engine-inputs',str(root)],text=True).strip()
 assert a==b,(a,b)
 return a
fixture=root/'nix/datom-crash-check.nix';production=root/'priv/std/errors.bl';original=fixture.read_bytes();code=production.read_bytes()
try:
 platform=run('policy-platform-prime',['scripts/prepare-checkout-platform'])
 sdk=run('policy-sdk-prime',['scripts/prepare-checkout-sdk'],timeout=600)
 a=json.loads((previous/'artifact.json').read_text());b=json.loads((pathlib.Path(sdk)/'artifact.json').read_text())
 assert a['image']==b['image'] and a['compiler']==b['compiler']
 r.update(sdk=sdk,platform=platform,identical_image=b['image'],identical_compiler=b['compiler'],fingerprint=hashes())
 frozen=root/'.bl/sdks'/r['fingerprint']/'source-engine';assert not (frozen/'nix/datom-crash-check.nix').exists()
 run('ci-sdk-unchanged',['scripts/prepare-checkout-sdk'])
 fixture.write_bytes(original+b'\n# CI-only latency counterfactual\n')
 assert hashes()==r['fingerprint']
 assert run('ci-platform-edit',['scripts/prepare-checkout-platform'])==platform
 assert run('ci-sdk-edit',['scripts/prepare-checkout-sdk'])==sdk
 # Independent actual recipe evaluation must agree with the cached platform.
 assert run('ci-platform-independent',['nix-build','nix/prepare-checkout.nix','--argstr','root',str(root),'--no-out-link'],timeout=180).splitlines()[-1]==platform
 production.write_bytes(code+b'\n; production invalidation counterfactual\n')
 assert hashes()!=r['fingerprint'];r['production_edit_invalidates']=True
 production.write_bytes(code);assert hashes()==r['fingerprint']
 r['status']='passed'
except BaseException as error:
 r.update(status='failed',error=str(error));raise
finally:
 fixture.write_bytes(original);production.write_bytes(code);save()
