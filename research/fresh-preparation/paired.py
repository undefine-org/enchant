"""Fresh-process preparation controls on an unchanged complete SDK catalog.

The candidate modules are development artifacts loaded after boot; results
qualify performance/output equivalence only. Native production qualification
must separately build and judge the candidate compiler through Source.
"""
import argparse,hashlib,json,os,pathlib,subprocess,time,statistics,resource,re
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--root',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True)
p.add_argument('--before-beams',type=pathlib.Path,required=True);p.add_argument('--after-beams',type=pathlib.Path,required=True)
a=p.parse_args();root=a.root.resolve();out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
r={'status':'running','scope':__doc__,'before_beams':str(a.before_beams),'after_beams':str(a.after_beams),'runs':[]}
def save():(out/'results.json').write_text(json.dumps(r,indent=2)+'\n')
def inventory(directory):return {str(p.relative_to(directory)):hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
reference=inventory(root/'.local/fresh-profile-snapshot');assert reference
try:
 for pair in range(3):
  for variant in (['before','after'] if pair%2==0 else ['after','before']):
   name=f'{pair}-{variant}';target=out/name;env=dict(os.environ,PERF_TRACE='0',PERF_COMPILED=str(getattr(a,variant+'_beams')),PERF_OUT=str(target))
   usage_before=resource.getrusage(resource.RUSAGE_CHILDREN)
   started=time.monotonic()
   with (out/(name+'.log')).open('w') as log:
    run=subprocess.run([str(root/'bin/bl'),'--cold','run','.local/probe.bl'],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180)
   rows=[json.loads(x.split(' ',1)[1]) for x in (out/(name+'.log')).read_text().splitlines() if x.startswith('PREPARATION ')]
   row={'pair':pair,'variant':variant,'exit':run.returncode,'wall_seconds':time.monotonic()-started,'units':rows,'prepare_seconds':sum(x['prepare-us'] for x in rows)/1e6,'emit_seconds':sum(x['emit-us'] for x in rows)/1e6}
   usage_after=resource.getrusage(resource.RUSAGE_CHILDREN)
   row['cpu_seconds']=usage_after.ru_utime-usage_before.ru_utime+usage_after.ru_stime-usage_before.ru_stime
   row['load_after']=pathlib.Path('/proc/loadavg').read_text().strip()
   memory=next(json.loads(line.split(' ',1)[1]) for line in (out/(name+'.log')).read_text().splitlines() if line.startswith('PREPARATION-MEMORY '))
   row['memory_kib']={key:int(value) for key,value in re.findall(r'(VmHWM|VmRSS|VmSwap):\s+(\d+)', '\n'.join(memory))}
   r['runs'].append(row);save();assert run.returncode==0
   assert len(rows)==6 and inventory(target)==reference
   row['byte_identical_files']=len(reference);print(json.dumps(row),flush=True);save()
 for v in ('before','after'):
  rows=[x for x in r['runs'] if x['variant']==v];r[v]={k:{'median':statistics.median([x[k] for x in rows]),'min':min(x[k] for x in rows),'max':max(x[k] for x in rows)} for k in ('wall_seconds','prepare_seconds','emit_seconds')}
 r['status']='passed'
finally:save()
