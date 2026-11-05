import json,pathlib,shutil,subprocess,time
root=pathlib.Path.cwd();out=root/'.local/fixed-cost';platform=pathlib.Path('/nix/store/k3kjhjksg5lsc9srlsfz64rn1w351jpc-beam-lisp-checkout-platform/artifact-platform')
copy=out/'shared-platform-2';shutil.copytree(platform/'nix',copy/'nix');shutil.copy2(platform/'flake.lock',copy/'flake.lock')
for file in copy.rglob('*'):file.chmod(file.stat().st_mode | 0o200)
# First experiment: share one exact package set across snapshot, selection and
# the unchanged request's recursive constructor. Runtime/build bodies unchanged.
p=copy/'nix/project-snapshot.nix';s=p.read_text().replace('{ source, rootsJson, excludedJson ? "[]" }:', '{ source, rootsJson, excludedJson ? "[]", pkgs ? null }:').replace('  pkgs = import ', '  packages = if pkgs != null then pkgs else import ').replace('in pkgs.runCommand','in packages.runCommand');p.write_text(s)
p=copy/'nix/application-artifact.nix';s=p.read_text().replace('{ requestJson ? null, requestPath ? null, sdk }:', '{ requestJson ? null, requestPath ? null, sdk, packages ? null }:').replace('  pkgs = import ', '  pkgs = if packages != null then packages else import ').replace('if unchanged then import ./application-artifact.nix {\n  inherit sdk;', 'if unchanged then import ./application-artifact.nix {\n  inherit sdk;\n  packages = pkgs;');p.write_text(s)
p=copy/'nix/application-selection.nix';s=p.read_text().replace('let\n','''let
  lock = builtins.fromJSON (builtins.readFile ../flake.lock);
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
''',1).replace('inherit source rootsJson excludedJson;', 'inherit source rootsJson excludedJson pkgs;').replace('inherit sdk; requestJson', 'inherit sdk; packages = pkgs; requestJson');p.write_text(s)
project=root/'.local/fixed-cost/commands-before/before-project';product=(project/'build/.nix-product').resolve();request=json.loads((product/'production-request.json').read_text());request['base']=str(product)
args=['--argstr','source',str(project),'--argstr','rootsJson',json.dumps(['src','env.bl']),'--argstr','excludedJson',json.dumps(['build','priv/native']),'--argstr','sdk','/nix/store/w4aa6066zjkx78b591r21xn3fdg4fra0-beam-lisp-sdk-selection','--argstr','requestJson',json.dumps(request),'--option','allow-import-from-derivation','false','--option','max-jobs','0','--extra-experimental-features','nix-command flakes']
report={'runs':[]};expected=None
for repeat in range(3):
 for label,recipe in [('before',platform/'nix/application-selection.nix'),('shared',copy/'nix/application-selection.nix')]:
  started=time.monotonic();r=subprocess.run(['nix-instantiate','--eval','--strict','--json',str(recipe),*args],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  assert r.returncode==0,(label,r.stderr)
  value=json.loads(r.stdout)
  if expected is None:expected=value
  assert value==expected,(value,expected)
  row={'variant':label,'repeat':repeat,'seconds':time.monotonic()-started,'selection':value};report['runs'].append(row);print(json.dumps(row),flush=True)
  (out/'nix-sharing.json').write_text(json.dumps(report,indent=2)+'\n')
