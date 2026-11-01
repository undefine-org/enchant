from pathlib import Path
import json,time,urllib.request
base='http://127.0.0.1:4048/'
def get(path):
    with urllib.request.urlopen(base+path,timeout=3) as r:return json.load(r)
def wait_for(predicate):
    start=time.monotonic()
    while time.monotonic()-start<40:
        try:
            if predicate():return round(time.monotonic()-start,3)
        except Exception:pass
        time.sleep(.25)
    raise AssertionError('timed out')
p=Path('examples/scene-renderer/scene_demo/film.bl');original=p.read_text();bad=original+'\n(\n'
old=get('manifest.json')['revision']
try:
    p.write_text(bad)
    t=wait_for(lambda:not get('status.json')['ok'])
    assert get('manifest.json')['revision']==old
    print('invalid edit retained previous revision:',t,'s',flush=True)
finally:
    if p.read_text()==bad:p.write_text(original)
wait_for(lambda:get('status.json')['ok'])
print('recovered original revision',flush=True)
valid=original+'\n; live-refresh acceptance check\n'
try:
    p.write_text(valid)
    t=wait_for(lambda:get('manifest.json')['revision']!=old)
    print('valid edit published new revision:',t,'s',flush=True)
finally:
    if p.read_text()==valid:p.write_text(original)
wait_for(lambda:get('manifest.json')['revision']==old)
print('restored source and revision',flush=True)
