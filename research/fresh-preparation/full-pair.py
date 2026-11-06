"""Compare complete fresh SDK unit production; no restoration or packaging.

Runs the same SDK's actual build/produce! entry and ownership checks for all
533 sources, under both development compilers. Full Source compiler/SDK
qualification is separate; these products never replace an SDK selection.
"""
import argparse,pathlib,os,json,subprocess,time,resource,hashlib
p=argparse.ArgumentParser(description=__doc__)
for n in ('root','out','before_beams','after_beams'):p.add_argument('--'+n.replace('_','-'),required=True,type=pathlib.Path)
a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=False);root=a.root.resolve()
r={'status':'running','scope':__doc__,'runs':[]}
def save():(out/'results.json').write_text(json.dumps(r,indent=2)+'\n')
def inventory(d):return {str(p.relative_to(d)):hashlib.sha256(p.read_bytes()).hexdigest() for p in d.rglob('*') if p.is_file()}
try:
 for v in ('before','after'):
  target=out/v;env=dict(os.environ,PERF_COMPILED=str(getattr(a,v+'_beams')),PERF_OUT=str(target),PERF_EXPECT_UNITS='533',PERF_FULL_TRACE_START=str(root/'.local/full-trace-start.exs'),PERF_FULL_TRACE_FINISH=str(root/'.local/full-trace-finish.exs'))
  started=time.monotonic();cpu=resource.getrusage(resource.RUSAGE_CHILDREN)
  with (out/(v+'.log')).open('w') as log:
   done=subprocess.run([str(root/'bin/bl'),'--cold','run','.local/full.bl'],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=2400)
  usage=resource.getrusage(resource.RUSAGE_CHILDREN)
  row={'variant':v,'exit':done.returncode,'wall_seconds':time.monotonic()-started,'cpu_seconds':usage.ru_utime-cpu.ru_utime+usage.ru_stime-cpu.ru_stime,'observations':{}}
  r['runs'].append(row);save();assert done.returncode==0
  for line in (out/(v+'.log')).read_text().splitlines():
   if line.startswith(('FULL-PREPARATION ','FULL-PRODUCTION ','SDK-UNIT-PHASES ','PREPARATION-MEMORY ')):
    key,value=line.split(' ',1);row['observations'][key]=json.loads(value)
  assert row['observations']['FULL-PRODUCTION']['compiled']==533 and row['observations']['FULL-PRODUCTION']['cached']==0
  files=inventory(target);row['files']=len(files);row['inventory_sha256']=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
  if v=='before':reference=files
  else:assert files==reference, [p for p in files.keys()|reference.keys() if files.get(p)!=reference.get(p)]
  save();print(json.dumps(row),flush=True)
 r['status']='passed'
finally:save()
