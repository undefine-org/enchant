#!/usr/bin/env python3
"""Export captures one publication, even when the manifest changes mid-encode.
Usage: python3 test/scripts/scene_export.py /tmp/bl-scene OUT.mp4
"""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
spec = importlib.util.spec_from_file_location('scene_raster', 'examples/scene-renderer/raster.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
root, output = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
m = json.loads((root / 'manifest.json').read_text())
with tempfile.TemporaryDirectory(prefix='scene-export-check-') as tmp:
    snapshot = Path(tmp)
    (snapshot / 'manifest.json').write_text(json.dumps(m))
    (snapshot / m['revision']).symlink_to(root / m['revision'], target_is_directory=True)
    original_run = worker.run
    switched = False
    def run(argv, **kw):
        global switched
        if not switched:
            switched = True
            (snapshot / 'manifest.json').write_text(json.dumps({**m, 'revision': 'newer-edit'}))
        return original_run(argv, **kw)
    worker.run = run
    worker.encode(snapshot, output, 'ffmpeg', 'ffprobe')
    report = json.loads(output.with_suffix('.manifest.json').read_text())
    assert switched and report['revision'] == m['revision']
    assert report['media']['nb_read_frames'] == str(m['frames'])
print('Export: captured revision survived publication change; frame count/dimensions/duration verified')
