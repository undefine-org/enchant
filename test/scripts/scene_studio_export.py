#!/usr/bin/env python3
"""Real studio export acceptance; uses one configured running studio.
The deliberately edited content must survive later UI changes during export.
"""
import copy
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.request

BASE = 'http://127.0.0.1:4048'

def request(path, value=None):
    data = None if value is None else json.dumps(value).encode()
    req = urllib.request.Request(BASE + path, data=data, headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)

config = request('/api/config')
config['title'] = 'A world worth making.'
config['cards'][0]['body'] = 'This exact sentence belongs to the captured film.'
config['cue'] = 0.4
preview = request('/api/frame', {'config':config, 'frame':60})
assert preview['ok'], preview
revision = preview['revision']
bad = request('/api/export', {'config':config, 'revision':'wrong'})
assert not bad['ok'], bad
started = time.monotonic()
admitted = request('/api/export', {'config':config, 'revision':revision})
assert admitted['ok'] and admitted['job']['revision'] == revision, admitted
# Another edit stays interactive and cannot mutate the admitted film.
later = copy.deepcopy(config)
later['title'] = 'A different world.'
changed = request('/api/frame', {'config':later, 'frame':72})
assert changed['ok'] and changed['revision'] != revision, changed
busy = request('/api/export', {'config':later, 'revision':changed['revision']})
assert not busy['ok'] and busy.get('busy'), busy
while time.monotonic() - started < 600:
    result = request('/api/export?revision=' + revision)
    job = result['job']
    if job['state'] == 'ready':
        break
    assert job['state'] != 'failed', job
    time.sleep(2)
else:
    raise AssertionError('Export did not finish within ten minutes')
with urllib.request.urlopen(BASE + job['url'], timeout=30) as response:
    assert response.headers['Content-Type'].startswith('video/mp4')
    video = response.read()
assert len(video) > 10000
Path('/tmp/bl-studio-ui-export.mp4').write_bytes(video)
if len(sys.argv) > 1:
    manifest = json.loads((Path(sys.argv[1]) / 'exports' / revision / 'living-postcard.manifest.json').read_text())
    assert manifest['sources']['config'] == config, 'export captured a different config'
    assert manifest['frames'] == 144 and manifest['fps'] == [24, 1]
report = {'revision':revision, 'seconds':time.monotonic()-started,
          'mp4_sha256':hashlib.sha256(video).hexdigest(),
          'checks':['mismatched revision rejected', 'exact edited revision admitted',
                    'preview edits remain interactive during export',
                    'second physical export rejected while busy', 'captured MP4 downloads']}
Path('/tmp/bl-studio-export-checks.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))
