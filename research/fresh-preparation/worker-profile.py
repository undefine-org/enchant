"""Force fresh unit production in the actual Source SDK worker.

Both controls use the same qualified compiler. Private copies of the existing
build/unit-store helpers differ only by deleting the optional reader-cache
field at the start of the already existing Source snapshot. All ownership,
input checks, target selection, emission, verification and assembly remain.
Never use these diagnostic SDKs as release inputs: their retained producer
subtrees include a different profiling dependency closure.
"""
import argparse,json,pathlib
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=pathlib.Path,required=True);p.add_argument('--mode',choices=['off','on'],required=True);a=p.parse_args();root=a.root.resolve();here=pathlib.Path(__file__).resolve().parent
assert (root/'priv/build/unit-store.bl').read_text().count('(fn [] (mapv (fn [path]') == 1
assert (root/'priv/build/build.bl').read_text().count('(ns build\n') == 1
source=(root/'priv/build/selfbuild.bl').read_text();patches=[('(ns selfbuild\n','(ns profile-selfbuild\n')]
setup_lines=['us = File.read!(Path.join(stage,"build/unit-store.bl"))',
             'us = String.replace(us, '+json.dumps('(ns unit-store ')+', '+json.dumps('(ns profile-unit-store ')+')']
if a.mode=='off':
 setup_lines.append('us = String.replace(us, '+json.dumps('(fn [] (mapv (fn [path]')+', '+json.dumps('(fn [] (Process/delete :bl_constructor_reader_cache) (mapv (fn [path]')+')')
setup_lines += ['BeamLisp.eval(us)', 'bs = File.read!(Path.join(stage,"build/build.bl"))']
for old,new in [('(ns build\n','(ns profile-build\n'),
                ('(BeamLisp.Loader/ensure_loaded "unit-store")',':ok'),
                ('(BeamLisp.Env/fetch! "unit-store" "produce!")','(BeamLisp.Env/fetch! "profile-unit-store" "produce!")')]:
 setup_lines.append('bs = String.replace(bs, '+json.dumps(old)+', '+json.dumps(new)+')')
setup_lines += ['BeamLisp.eval(bs)', 'run = BeamLisp.Env.fetch!("profile-build","produce!")']
setup='\n'.join(setup_lines)+'\n'

for line in source.splitlines():
 stripped=line.strip()
 if not stripped.startswith('"'):continue
 try:code=json.loads(stripped)
 except json.JSONDecodeError:continue
 if code=='run = BeamLisp.Env.fetch!("build", "produce!")':patches.append((line,'          '+json.dumps(setup)))
 if code.startswith('r = timed.("child-produce",'):
  code=code.replace(':"sdk-artifacts?" => true', ':"sdk-artifacts?" => true, :"force?" => true')
  assert ':"force?" => true' in code
  start=(here/'full-trace-start.exs').read_text()
  finish=(here/'full-trace-finish.exs').read_text().replace('expected=String.to_integer(System.fetch_env!("PERF_EXPECT_UNITS"))','expected=length(sources)')
  patches.append((line,'          '+json.dumps(start)+'\n          '+json.dumps(code)+'\n          '+json.dumps(finish)))
assert len(patches)==3,len(patches)
bindings=['source (File/read! "priv/build/selfbuild.bl")']
for old,new in patches:
 assert source.count(old)==1,old
 source=source.replace(old,new)
 bindings.append('source (String/replace source '+json.dumps(old)+' '+json.dumps(new)+')')
driver=(root/'scripts/produce-sdk.bl').read_text();marker='(let [_ (selfbuild/timed';assert driver.count(marker)==1
header,body=driver.split(marker)
profile=header+'\n(let ['+'\n       '.join(bindings)+'] (BeamLisp/eval source))\n(ns tooling.profile-produce-sdk (:require [profile-selfbuild :as selfbuild] [seed :as seed] [drop :as drop]))\n'+marker+body
(root/'scripts/produce-sdk.bl').write_text(profile)
(root/'profile-selfbuild.expected.bl').write_text(source)
