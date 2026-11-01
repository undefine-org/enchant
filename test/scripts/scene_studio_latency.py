#!/usr/bin/env python3
"""Small named-host distributions for an owned studio; not a benchmark claim."""
import copy
import json
from pathlib import Path
import statistics
import time
import urllib.request
BASE='http://127.0.0.1:4048'
with urllib.request.urlopen(BASE+'/api/config') as r: base=json.load(r)
def render(config):
    start=time.perf_counter()
    req=urllib.request.Request(BASE+'/api/frame',data=json.dumps({'config':config,'frame':60}).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=30) as r: result=json.load(r)
    assert result['ok'],result
    return time.perf_counter()-start
render(base)
text=[]
for i in range(10):
    config=copy.deepcopy(base);config['cards'][0]['body']+=f' Edition {i}.'
    text.append(render(config))
cue=[]
for i in range(10):
    config['cue']=.6+i*.03
    cue.append(render(config))
def summary(v):return {'samples':v,'p50':statistics.median(v),'p95_nearest_rank':sorted(v)[-1],'n':len(v)}
report={'text_edit_seconds':summary(text),'cue_edit_seconds':summary(cue),'quality':'540px raster / 1080-unit layout','p95_method':'nearest rank; with 10 samples this is the maximum','environment':'local development host, sequential warm session; no comparison to other renderers'}
Path('/tmp/bl-postcard-latency.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
