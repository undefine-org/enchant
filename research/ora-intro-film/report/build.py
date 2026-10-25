#!/usr/bin/env python3
"""Collect measured data and thumbnails for the ORA work report.
Everything charted is read back from retained artifacts: the evaluated plan and the encoded film.
"""
from pathlib import Path
import array,gzip,json,math,subprocess
ROOT=Path(__file__).resolve().parent;FILM=ROOT.parent;PROOF=FILM/'proof'/'evidence'
MEDIA=ROOT/'media';MEDIA.mkdir(exist_ok=True)
plan=json.loads(gzip.decompress((PROOF/'plan.json.gz').read_bytes()))
frames=plan['frames']
def ident(b):return b['id']
ids=[b['id'] for b in frames[0]['boxes']]
# Impact: first frame within the rebound band (< 6 cm) of rest; lines grow rather than land.
landings={}
for j,i in enumerate(ids):
 if i.startswith('line'):continue
 ys=[f['boxes'][j]['center'][1] for f in frames];final=ys[-1]
 landings[i]=round(next(k for k,y in enumerate(ys) if y-final<0.06)/60,3)
# Line arrivals: first frame each vertical line reaches full height.
arrivals={}
for j,i in enumerate(ids):
 if i.startswith('line/up/'):
  hs=[f['boxes'][j]['size'][1] for f in frames];top=max(hs)
  arrivals[i]=round(next(k for k,h in enumerate(hs) if h>=top-1e-3)/60,3)
core=ids.index('playbooks')
glow=[round(f['boxes'][core]['glow'],4) for f in frames]
distance=[round(math.sqrt(sum(v*v for v in f['eye'])),3) for f in frames]
order=[round(f['motes'][0],4) for f in frames]
# Loudness: decode the encoded film's audio to mono 48 kHz and take RMS per video frame.
raw=subprocess.run(['ffmpeg','-v','error','-i',str(PROOF/'layers.mp4'),'-ac','1','-ar','48000','-f','s16le','-'],check=True,capture_output=True).stdout
pcm=array.array('h');pcm.frombytes(raw);step=800;loud=[]
for k in range(900):
 seg=pcm[k*step:(k+1)*step];rms=math.sqrt(sum(x*x for x in seg)/max(1,len(seg)))/32768 if seg else 0
 loud.append(round(20*math.log10(rms) if rms>1e-5 else -100,2))
# Thumbnails from the encoded film (what a viewer actually receives), plus a poster for each earlier film.
times=[0.5,1.6,2.9,4.0,4.75,5.6,6.6,7.8,8.9,10.0,12.0,14.9]
for k,t in enumerate(times):
 subprocess.run(['ffmpeg','-v','error','-y','-ss',str(t),'-i',str(PROOF/'layers.mp4'),'-frames:v','1','-vf','scale=640:-2','-q:v','3',str(MEDIA/f'proof-{k:02}.jpg')],check=True)
subprocess.run(['ffmpeg','-v','error','-y','-ss','14','-i',str(PROOF/'layers.mp4'),'-frames:v','1','-q:v','2',str(MEDIA/'proof-hero.jpg')],check=True)
data={'landings':landings,'arrivals':arrivals,'glow':glow,'distance':distance,'order':order,'loudness':loud,'thumbs':[{'t':t,'src':f'media/proof-{k:02}.jpg'} for k,t in enumerate(times)],
 'beat':60/128,'fps':60,'frames':900}
(ROOT/'data.json').write_text(json.dumps(data))
print(json.dumps({'landings':landings,'arrivals':arrivals,'peak_glow':max(glow),'loud_max':max(loud)},indent=1))

# Zellige: one thumbnail per scripted line, from the delivered film.
ZF=FILM/'zellige'/'film'/'evidence'/'zellige.mp4'
script=[(1.2,4.8,'You already work with agents.'),(6.0,10.8,'But they only know you.'),(13.0,17.6,'Your way of working becomes the pattern.'),(19.6,24.8,'Now the whole company shares it.'),
 (27.0,31.2,'Every lesson is kept and passed on.'),(33.2,37.8,'Built to last. Yours to keep.'),(41.0,45.0,'ORA Ventures · From personal agents to a company brain.')]
zel=[]
for k,(a,b2,line) in enumerate(script):
 t=min(44.5,(a+b2)/2+(.8 if k==6 else 0))
 subprocess.run(['ffmpeg','-v','error','-y','-ss',str(t),'-i',str(ZF),'-frames:v','1','-vf','scale=640:-2','-q:v','3',str(MEDIA/f'zellige-{k}.jpg')],check=True)
 zel.append({'in':a,'out':b2,'line':line,'src':f'media/zellige-{k}.jpg'})
data['zellige']=zel
(ROOT/'data.json').write_text(json.dumps(data))
