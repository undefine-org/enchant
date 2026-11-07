#!/usr/bin/env python3
"""Measure a five-colour palette from each mood-board photo (k-means on a 128x96 nearest-neighbour sample, so each sample is one real glaze)."""
from pathlib import Path
import json,subprocess
ROOT=Path(__file__).resolve().parent
rows=json.loads((ROOT/'sources.json').read_text())
def palette(path,k=6):
 raw=subprocess.run(['ffmpeg','-v','error','-i',str(path),'-vf','scale=128:96:flags=neighbor','-f','rawvideo','-pix_fmt','rgb24','-'],check=True,capture_output=True).stdout
 px=[tuple(raw[i:i+3]) for i in range(0,len(raw),3)]
 px_sorted=sorted(px,key=lambda c:sum(c));centres=[px_sorted[int((j+.5)*len(px)/k)] for j in range(k)]
 for _ in range(12):
  groups=[[] for _ in centres]
  for c in px:groups[min(range(len(centres)),key=lambda j:sum((a-b)**2 for a,b in zip(c,centres[j])))].append(c)
  centres=[tuple(sum(v[i] for v in g)//len(g) for i in range(3)) if g else centres[j] for j,g in enumerate(groups)]
 share=[len(g)/len(px) for g in groups]
 order=sorted(range(len(centres)),key=lambda j:-share[j])
 return [{'hex':'#%02x%02x%02x'%centres[j],'share':round(share[j],3)} for j in order]
for r in rows:r['palette']=palette(ROOT/'photos'/r['file'])
(ROOT/'sources.json').write_text(json.dumps(rows,indent=1)+'\n')
print('\n'.join(f"{r['file']} "+' '.join(p['hex'] for p in r['palette']) for r in rows))
