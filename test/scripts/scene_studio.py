#!/usr/bin/env python3
"""Acceptance checks against an owned running postcard studio on 4048."""
import copy
import base64
import json
from pathlib import Path
import statistics
import time
import urllib.request

BASE='http://127.0.0.1:4048'
with urllib.request.urlopen(BASE+'/api/config') as r: config=json.load(r)
def request(config,frame=60):
    started=time.perf_counter()
    req=urllib.request.Request(BASE+'/api/frame',data=json.dumps({'config':config,'frame':frame}).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=30) as r:value=json.load(r)
    return value,time.perf_counter()-started
first,elapsed=request(config)
assert first['ok'],first
original=first['revision']; ids=set(first['objects'])
artifacts=Path('/tmp/bl-postcard-acceptance');artifacts.mkdir(exist_ok=True)
def retain(name,result):
    (artifacts/(name+'.png')).write_bytes(base64.b64decode(result['image'].split(',',1)[1]))
    (artifacts/(name+'.json')).write_text(json.dumps({k:v for k,v in result.items() if k!='image'},indent=2)+'\n')
retain('warm',first)
assert 'postcard/cards/compose/title' in ids
long=copy.deepcopy(config)
long['cards'][0]['body']='A thought becomes a small set of values. Give each one a name. '+('This longer story needs another line. '*6)
second,edit=request(long)
assert second['ok'],second
assert second['objects']['postcard/cards/compose']['logical'][3]>first['objects']['postcard/cards/compose']['logical'][3]
assert second['objects']['postcard/cards/evaluate']['logical'][1]>first['objects']['postcard/cards/evaluate']['logical'][1]
assert second['revision']!=original
retain('long',second)
reorder=copy.deepcopy(config);reorder['cards'].reverse()
third,_=request(reorder)
assert third['ok'] and set(third['objects'])==ids
blue=copy.deepcopy(config);blue['theme']='blueprint'
fourth,_=request(blue)
retain('blueprint',fourth)
assert fourth['ok'] and fourth['objects']['postcard/heading']['properties']['color']!=first['objects']['postcard/heading']['properties']['color']
bad=copy.deepcopy(config);bad['cards'][1]['id']=bad['cards'][0]['id']
invalid,_=request(bad)
assert not invalid['ok'] and invalid['revision']==fourth['revision']
restored,_=request(config)
assert restored['ok'] and restored['revision']==original
seek=[]
for k in [0,36,100,72,60]:
    v,t=request(config,k);assert v['ok'],v;seek.append(t)
assert v['image']==first['image'],'same revision/time must preserve pixels'
result={'first_frame_seconds':elapsed,'text_edit_seconds':edit,'seek_seconds':seek,'seek_median':statistics.median(seek),'revision':original,'checks':['wrapped text grows and reflows following cards','stable identities under reorder','theme changes coherently','invalid edit retains valid revision','arbitrary seeks reproduce exact PNG bytes']}
Path('/tmp/bl-postcard-studio-checks.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
