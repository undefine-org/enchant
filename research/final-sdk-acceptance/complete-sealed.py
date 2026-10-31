import hashlib,json,os,runpy,subprocess,tempfile,time
from pathlib import Path
root=Path.cwd();out=root/'.local/final-acceptance';prior=out/'sealed-3';image=prior/'image';dest=out/'sealed-completion-4';dest.mkdir()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
ref=lambda p:{'path':str(p.relative_to(root)),'sha256':sha(p)}
profiles=runpy.run_path(str(root/'scripts/sdk_sealed_profiles.py'))
qualifier=runpy.run_path(str(root/'scripts/qualify-candidate.py'))
plan=json.loads((prior/'sealed-plan.json').read_text());old=json.loads((prior/'result.json').read_text())
assert old['status']=='error' and old['error']=='contextual-consumer-isolated-1 failed with exit 1'
old_inputs=json.loads((prior/'inputs.json').read_text())
changes={p:{'before':digest,'after':sha(root/p)} for p,digest in old_inputs.items() if sha(root/p)!=digest}
assert set(changes)=={'scripts/demo-sdk-artifacts','test/scripts/sdk-selected-consumer.bl'}
frozen={p:sha(root/p) for p in old_inputs}
sdk_path,engine=(out/'selection.txt').read_text().split();sdk=Path(sdk_path);meta=json.loads((sdk/'artifact.json').read_text())
assert subprocess.check_output([str(root/'scripts/prepare-checkout-sdk'),'--fingerprint'],text=True).strip()==engine
floor=Path(meta['image'])/'lib/beam_lisp-0.1.0/priv/bootstrap/seed';floor_inputs={p.name:sha(p) for p in floor.iterdir() if p.is_file()}
artifacts=[*(image/'ebin').glob('*.beam'),image/'priv/sdk-code.term'];artifact_inputs={str(p):sha(p) for p in artifacts}
files=[r['path'] for g in plan['groups'] for r in g['tests']];groups=qualifier['process_groups'](files,json.loads((root/'scripts/test-isolation.json').read_text()))
warm=json.loads((prior/'contextual-consumer-part-0.json').read_text());warmplan=json.loads((prior/'sealed-plan-part-0.json').read_text());profiles['validate'](warmplan,warm)
assert [r['path'] for r in warm['files']]==groups[0]
report={'version':1,'scope':'sealed-SDK-independent-stage-completion','status':'running','sdk':sdk_path,'engine':engine,'sealed_plan':plan,'prior_failed_receipt':ref(prior/'result.json'),'warm_passed_receipt':ref(prior/'contextual-consumer-part-0.json'),'warm_path_unchanged':'The isolated predicate is false for the 120-file warm batch; its initialization and Ward path are unchanged.','harness_input_changes':changes,'sealed_source_consumers':old['sealed_source_consumers'],'sdk_initialization':old['sdk_initialization'],'producer':old['producer'],'seconds':{}}
parts=[warm]
base_env=dict(os.environ,BL_ROOT=str(image),BL_DAEMON='off',BL_SDK_ARTIFACT_OUT=str(dest),BL_TEST_TIMES='1',BL_TEST_SOURCE_ROOT=str(root),BL_SDK_CONTEXTUAL_ROOT=str(root),BL_SDK_ARTIFACT_SOURCE_FREE='yes',BL_SDK_ARTIFACT_EXPECTED='42',BL_SDK_EXPECT_Z3_SHA256=old['tool_inputs']['z3']['selected']['sha256'],ELIXIR_ERL_OPTIONS='+S 4:4 +SDcpu 2:2 +SDio 1:1')
base_cmd=[str(Path(meta['platform'])/'bin/elixir')]
for dep in sorted((sdk/'lib').glob('*/ebin')):
 if not dep.parent.name.startswith('beam_lisp-'):base_cmd+=['-pa',str(dep)]
base_cmd+=['-pa',str(image/'.bl/lib/beam_lisp-0.1.0/ebin')]
def check_inputs():
 assert frozen=={p:sha(root/p) for p in frozen},'Source/test harness changed during completion'
 assert floor_inputs=={p.name:sha(p) for p in floor.iterdir() if p.is_file()},'selected floor changed'
def run(name,driver,application=False,extra=None):
 check_inputs();started=time.monotonic()
 env={**base_env,**(extra or {}), 'BL_ARTIFACT_DRIVER':str(driver),'XDG_CACHE_HOME':str(image/('completion-cache-'+name))}
 boot=image/('consumer-boot.exs' if application else 'boot.exs')
 with (dest/(name+'.log')).open('w') as log:
  done=subprocess.run([*base_cmd,str(boot)],cwd=image,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300)
 report['seconds'][name]=round(time.monotonic()-started,3)
 print(name,'exit',done.returncode,flush=True)
 if done.returncode:raise RuntimeError(name+' failed; see retained log')
 check_inputs()
try:
 with tempfile.TemporaryDirectory(prefix='bl-sealed-completion-',dir=os.environ.get('XDG_RUNTIME_DIR')) as runtime:
  base_env=qualifier['runtime_environment'](base_env);base_env['XDG_RUNTIME_DIR']=runtime
  try:
   for index,paths in enumerate(groups[1:],1):
    part=dict(plan,pipeline=False,isolated=True)
    part['groups']=[dict(g,tests=[r for r in g['tests'] if r['path'] in paths]) for g in plan['groups']]
    part['groups']=[g for g in part['groups'] if g['tests']]
    part['assertions']=sum(r['assertions'] for g in part['groups'] for r in g['tests'])
    partpath=dest/('plan-'+str(index)+'.json');partpath.write_text(json.dumps(part,indent=2)+'\n')
    run('isolated-'+str(index),root/'test/scripts/sdk-selected-consumer.bl',True,{'BL_SDK_SEALED_PLAN':str(partpath)})
    receipt=json.loads((dest/'contextual-consumer.json').read_text());profiles['validate'](part,receipt)
    (dest/'contextual-consumer.json').rename(dest/('consumer-part-'+str(index)+'.json'));parts.append(receipt)
   by_path={r['path']:r for part in parts for r in part['files']}
   consumer=dict(warm,files=[by_path[p] for p in files],assertions=sum(p['assertions'] for p in parts))
   profiles['validate'](plan,consumer);profiles['validate_initialization'](plan,report['sdk_initialization'])
   report['contextual_consumer']=consumer
   run('consumer',root/'test/scripts/sdk-artifact-consumer.bl')
   report['consumer']=json.loads((dest/'consumer.json').read_text())
   victim=image/'ebin/Elixir.BeamLisp.Ns.Sdk.Artifact.Consumer.beam';original=victim.read_bytes()
   try:
    victim.write_bytes(b'changed sealed artifact');run('tamper',root/'test/scripts/sdk-artifact-consumer.bl',extra={'BL_SDK_ARTIFACT_TAMPER':'yes'})
   finally:victim.write_bytes(original)
   index=image/'priv/sdk-code.term';original=index.read_bytes()
   try:run('missing-unit',root/'test/scripts/sdk-artifact-consumer.bl',extra={'BL_SDK_ARTIFACT_MISSING':'yes'})
   finally:index.write_bytes(original)
  finally:qualifier['stop_children'](runtime)
 assert artifact_inputs=={p:sha(Path(p)) for p in artifact_inputs},'sealed artifacts changed'
 report.update(status='passed',source_free_sdk=True,tampering_refused_before_initialization=True,missing_unit_refused_before_initialization=True,frozen_inputs_unchanged=True,sealed_artifacts_unchanged=True)
 profiles['validate_universal'](report)
except Exception as error:
 report.update(status='error',error=str(error));raise
finally:(dest/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print('All 126 sealed files and universal controls qualified; earlier aggregate remains failed',flush=True)
