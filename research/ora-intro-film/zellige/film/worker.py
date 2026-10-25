#!/usr/bin/env python3
"""Bounded EGL/GLES executor for the captured ORA Zellige film plan.
BL authors every frame value and every word. This worker validates, draws and encodes only.
Reuses the captured MAKE WORLDS GPU context and shaped-type texture helpers.
"""
import argparse,array,ctypes as C,hashlib,importlib.util,json,math,subprocess,time,wave
from pathlib import Path

FRAMES,SECONDS,W,H=2700,45,1920,1080
UNIFORMS={'eye':3,'right':3,'up':3,'forward':3,'clock':4,'build':4,'fit':4,'refine':4,'light':4,'finale':4,'grade':4,'finish':4}
VOICES=['guembri','qraqeb','clap','tbel','tap']
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def module(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def vector(v,n,bound=10000):return isinstance(v,list) and len(v)==n and all(type(x) in (int,float) and math.isfinite(x) and abs(x)<bound for x in v)

def validate(p):
 if set(p)!={'version','viewport','fps','duration','frames','typography','audio'} or p['version']!=1 or p['viewport']!=[W,H] or p['fps']!=[60,1] or p['duration']!=SECONDS:raise ValueError('Unsupported zellige plan')
 if not isinstance(p['frames'],list) or len(p['frames'])!=FRAMES:raise ValueError(f'Expected exactly {FRAMES} frames')
 specs=p['typography'];ids=[s.get('id') for s in specs]
 if not 1<=len(specs)<=16 or len(set(ids))!=len(ids):raise ValueError('Invalid typography resources')
 for s in specs:
  if not vector(s.get('ink-bounds'),4) or not 0<s['ink-bounds'][2]<=2000 or not isinstance(s.get('path'),str) or len(s['path'])>2000000:raise ValueError('Invalid shaped typography')
 for k,f in enumerate(p['frames']):
  if set(f)!=set(UNIFORMS)|{'frame','time','tan-half','types'} or f['frame']!=k or abs(f['time']-k/60)>1e-8:raise ValueError('Invalid frame clock or channel')
  if not all(vector(f[n],m) for n,m in UNIFORMS.items()) or not vector([f['tan-half']],1) or not 0<f['tan-half']<3:raise ValueError('Nonfinite frame uniform')
  if [t.get('id') for t in f['types']]!=ids:raise ValueError('Words must keep stable ordered identities')
  for t in f['types']:
   if set(t)!={'id','rect','opacity','ink'} or not vector(t['rect'],4) or min(t['rect'][2:])<=0 or not vector(t['ink'],3) or not vector([t['opacity']],1) or not 0<=t['opacity']<=1:raise ValueError('Invalid word placement')
 if not isinstance(p['audio'],list) or len(p['audio'])>2048:raise ValueError('Invalid audio budget')
 for e in p['audio']:
  if set(e)!={'at','voice','duration','frequency','gain'} or e['voice'] not in VOICES or not vector([e['at'],e['duration'],e['frequency'],e['gain']],4,20000) or not 0<=e['at']<SECONDS or not 0<e['duration']<=4 or not 20<=e['frequency']<=10000 or not 0<e['gain']<=1:raise ValueError('Invalid sound event')
 return p

def soundtrack(events,path):
 # Gnawa-inspired, acoustic-leaning synthesis: plucked-string guembri (Karplus-Strong) with a
 # thumb thump and a rattling buzz, iron qraqeb pairs, hand claps, tbel drum, ceramic taps.
 rate=48000;n=rate*SECONDS;mix=array.array('f',[0])*(n*2)
 pans={'guembri':.42,'tbel':.5,'tap':.55}
 for k,e in enumerate(events):
  start=round(e['at']*rate);length=min(round(e['duration']*rate),n-start);f=e['frequency'];g=e['gain'];voice=e['voice'];seed=9001+k*733
  pan=pans.get(voice,.5+.32*math.sin(e['at']*5.1+k*.7))
  def rnd():
   nonlocal seed;seed=(1664525*seed+1013904223)&0xffffffff;return seed/2147483648-1
  out=array.array('f',[0])*max(length,0)
  if voice=='guembri':
   # A dark, low excitation (smoothed ten times) keeps the energy in the low harmonics.
   N=max(2,int(rate/f));buf=[rnd() for _ in range(N)]
   for _ in range(10):buf=[(buf[i]+buf[i-1])*.5 for i in range(N)]
   peak=max(abs(x) for x in buf) or 1;buf=[x/peak for x in buf]
   for j in range(length):
    i=j%N;cur=buf[i];buf[i]=.4972*(cur+buf[(i+1)%N]);t=j/rate
    env=math.exp(-t*2.6)*min(1,(length-j)/(rate*.08))
    out[j]=(cur*.9+.06*rnd()*abs(cur)*math.exp(-t*6))*env+.55*math.sin(2*math.pi*f*t)*math.exp(-t*9)+.5*math.sin(2*math.pi*52*t)*math.exp(-t*30)+.08*rnd()*math.exp(-t*300)
  elif voice=='qraqeb':
   parts=((1,1),(1.583,.7),(2.204,.5),(3.12,.35))
   for j in range(length):
    t=j/rate;v=0
    for off,amp in ((0,1),(.027,.75)):
     u=t-off
     if u>=0:v+=amp*(sum(a*math.sin(2*math.pi*f*m*u) for m,a in parts)*.4*math.exp(-u*55)+rnd()*.5*math.exp(-u*130))
    out[j]=v
  elif voice=='clap':
   prev=0
   for j in range(length):
    t=j/rate;env=sum(math.exp(-max(0,t-o)*420)*(t>=o) for o in (0,.008,.017))+.35*math.exp(-t*26)
    x=rnd();out[j]=(x-prev)*env*.8;prev=x
  elif voice=='tbel':
   for j in range(length):
    t=j/rate;out[j]=math.sin(2*math.pi*(f*t+40*(1-math.exp(-t*25))/25))*math.exp(-t*8)+.3*rnd()*math.exp(-t*70)
  else:
   for j in range(length):
    t=j/rate;out[j]=(.6*math.sin(2*math.pi*f*t)+.3*math.sin(2*math.pi*f*1.67*t))*math.exp(-t*70)+.2*rnd()*math.exp(-t*220)
  for j in range(length):
   at=(start+j)*2;v=out[j]*g;mix[at]+=v*(1.2-pan*.8);mix[at+1]+=v*(.4+pan*.8)
 # A small room: a few early reflections and one short tail, nothing synthetic-sounding.
 for delay,gain,cross in ((.019,.16,1),(.031,.12,0),(.047,.09,1),(.083,.06,0),(.161,.05,1)):
  d=round(rate*delay)*2
  for k in range(len(mix)-1,d-1,-1):
   src=k-d+(1 if cross and k%2==0 else -1 if cross else 0)
   if 0<=src<len(mix):mix[k]+=gain*mix[src]
 pcm=array.array('h');peak=0
 for k,v in enumerate(mix):
  v=math.tanh(v*1.6)*.92*min(1,(n-k//2)/(rate*1.0));peak=max(peak,abs(v));pcm.append(round(v*32767))
 with wave.open(str(path),'wb') as w:w.setnchannels(2);w.setsampwidth(2);w.setframerate(rate);w.writeframes(pcm.tobytes())
 return {'rate':rate,'samples':n,'channels':2,'peak':peak,'events':len(events),'sha256':digest(path)}

def run(a):
 started=time.monotonic();folder=a.folder
 if (folder/'plan.json').stat().st_size>256*1024*1024:raise ValueError('Plan byte budget exceeded')
 plan=validate(json.loads((folder/'plan.json').read_text()));requested=[int(x) for x in a.selected.split(',')];selected=set(requested)
 if any(not 0<=x<FRAMES for x in selected):raise ValueError('Selected frame outside clock')
 native=module(a.gpu_worker,'ora_gpu');gpu=None;encoder=None;temporary=folder/'.pending-zellige.mp4';hashes={};timing=[]
 try:
  gpu=native.GPU.__new__(native.GPU);gpu.__init__(a.egl,a.gles,W,H)
  def program(v,f):return gpu.program((a.shaders/v).read_text(),(a.shaders/f).read_text())
  floor=program('flat.vert','zellige.frag');post=program('flat.vert','post.frag');typeprog=program('type.vert','type.frag')
  textures=native.type_textures(gpu,plan,folder,a.rsvg,a.text_worker)
  blend=gpu.gb('glBlendFunc',None,C.c_uint,C.c_uint);finish=gpu.gb('glFinish',None)
  audio=soundtrack(plan['audio'],folder/'soundtrack.wav') if a.film else None
  args=['ffmpeg','-v','error','-y','-f','rawvideo','-pixel_format','rgba','-video_size',f'{W}x{H}','-framerate','60','-i','pipe:0','-i',str(folder/'soundtrack.wav'),'-vf','vflip','-c:v','libx264','-crf','16','-preset','medium','-threads','2','-pix_fmt','yuv420p','-c:a','aac','-b:a','256k','-movflags','+faststart','-t',str(SECONDS),str(temporary)]
  with (folder/'encoder.log').open('wb') as log:
   if a.film:encoder=subprocess.Popen(args,stdin=subprocess.PIPE,stderr=log)
   for k in (range(FRAMES) if a.film else requested):
    f=plan['frames'][k];t0=time.monotonic()
    gpu.bindf(0x8d40,gpu.scene);gpu.disable(0x0b71);gpu.disable(0x0be2)
    gpu.use(floor);gpu.geometry(gpu.quad,2)
    gpu.set(floor,'resolution',[W,H]);gpu.set(floor,'tanHalf',[f['tan-half']])
    for name in ['eye','right','up','forward','clock','build','fit','refine','light','finale','grade']:gpu.set(floor,name,f[name])
    gpu.draw(5,0,4)
    gpu.bindf(0x8ca8,gpu.scene);gpu.bindf(0x8ca9,gpu.resolve)
    gpu.gb('glBlitFramebuffer',None,*([C.c_int]*8),C.c_uint,C.c_uint)(0,0,W,H,0,0,W,H,0x4000,0x2600)
    gpu.bindf(0x8d40,gpu.final);gpu.use(post);gpu.geometry(gpu.quad,2);gpu.bindtex(0x0de1,gpu.hdr)
    gpu.set(post,'resolution',[W,H]);gpu.set(post,'finish',f['finish']);gpu.draw(5,0,4)
    # Words sit on the graded picture, untouched by bloom or tone mapping.
    gpu.enable(0x0be2);blend(1,0x0303);gpu.use(typeprog);gpu.set(typeprog,'resolution',[W,H])
    for item in f['types']:
     if item['opacity']<=0:continue
     gpu.bindtex(0x0de1,textures[item['id']][0]);gpu.set(typeprog,'rect',item['rect']);gpu.set(typeprog,'ink',item['ink']+[item['opacity']]);gpu.draw(5,0,4)
    gpu.disable(0x0be2)
    gpu.read(0,0,W,H,0x1908,0x1401,gpu.pixels);gpu.check();packed=bytes(gpu.pixels);timing.append(time.monotonic()-t0)
    if k in selected:path=folder/f'{k}.png';native.png(path,packed,W,H);hashes[str(k)]=digest(path)
    if encoder:encoder.stdin.write(packed)
    if k%180==0:print(json.dumps({'frame':k,'of':FRAMES,'seconds':round(time.monotonic()-started,1)}),flush=True)
   if encoder:
    encoder.stdin.close()
    if encoder.wait()!=0:raise RuntimeError('Encoder failed; see encoder.log')
    temporary.replace(folder/'zellige.mp4')
  media=None
  if a.film:
   media=json.loads(subprocess.check_output(['ffprobe','-v','error','-count_frames','-show_streams','-of','json',str(folder/'zellige.mp4')]))
   v=next(s for s in media['streams'] if s['codec_type']=='video');au=next(s for s in media['streams'] if s['codec_type']=='audio')
   if v['nb_read_frames']!=str(FRAMES) or v['r_frame_rate']!='60/1' or v['width']!=W or v['height']!=H or abs(float(v['duration'])-SECONDS)>.001 or abs(float(au['duration'])-SECONDS)>.03:raise RuntimeError('Media clock verification failed')
  timing.sort()
  report={'seconds':time.monotonic()-started,'gpu':gpu.info,'media':media,'audio':audio,'plan_sha256':digest(folder/'plan.json'),'frame_hashes':hashes,
   'frame_ms':{'median':round(1000*timing[len(timing)//2],2),'max':round(1000*timing[-1],2)} if timing else None,
   'film_sha256':digest(folder/'zellige.mp4') if a.film else None,'shader_hashes':{p.name:digest(p) for p in sorted(a.shaders.iterdir()) if p.suffix in ['.vert','.frag']},
   'policy':'BL-evaluated camera/construction/fit/refinement/finale/words/sound; per-pixel ray-plane star-and-cross zellige with per-tile clocks; RGBA16F; bloom + ACES-like curve; shaped Schibsted Grotesk composited after grading; H.264 60 fps + original AAC stereo'}
  (folder/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 finally:
  if encoder and encoder.poll() is None:encoder.kill();encoder.wait()
  temporary.unlink(missing_ok=True)
  if gpu:gpu.close()

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('folder',type=Path);p.add_argument('--shaders',required=True,type=Path);p.add_argument('--gpu-worker',required=True,type=Path)
 p.add_argument('--rsvg',required=True);p.add_argument('--text-worker',required=True,type=Path)
 p.add_argument('--egl',required=True);p.add_argument('--gles',required=True);p.add_argument('--film',action='store_true')
 p.add_argument('--selected',default='0,96,180,420,660,800,900,1000,1110,1200,1290,1500,1650,1740,1860,2100,2220,2340,2420,2480,2520,2600,2699');run(p.parse_args())
