#!/usr/bin/env python3
"""Pack a completed revision into a browser-openable preview with no server."""
import base64
import json
from pathlib import Path
import sys

root, output = map(Path, sys.argv[1:])
m = json.loads((root / 'manifest.json').read_text())
folder = root / m['revision']
frames = ['data:image/png;base64,' + base64.b64encode((folder / f'{k}.png').read_bytes()).decode()
          for k in range(m['frames'])]
html = (root / 'index.html').read_text()
html = html.replace('image.src=`${m.revision}/${k}.png`', 'image.src=window.SCENE_FRAMES[k]')
# Local file fetches are forbidden by browsers. The immutable bundle supplies
# the same publication and successful build status directly, without a server.
bootstrap = ('<script>window.SCENE_FRAMES=' + json.dumps(frames)
             + ';const publication=' + json.dumps(m)
             + ';window.fetch=async p=>({ok:true,json:async()=>'
             + "p==='manifest.json'?publication:{ok:true,diagnostic:''}});</script>")
html = html.replace('<script>', bootstrap + '<script>', 1)
# Inspector data is also captured so this link works from file://.
scene = base64.b64encode((folder / 'scene.json').read_bytes()).decode()
html = html.replace('`${m.revision}/scene.json`', json.dumps('data:application/json;base64,' + scene))
output.write_text(html)
print(output)
