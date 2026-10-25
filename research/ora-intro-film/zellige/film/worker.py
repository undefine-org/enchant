#!/usr/bin/env python3
"""Bounded EGL/GLES executor for the captured ORA Zellige film plan.
BL authors every frame value and every word. This worker validates, draws and encodes only.
Reuses the captured MAKE WORLDS GPU context and shaped-type texture helpers.
"""
import argparse,array,ctypes as C,hashlib,importlib.util,json,math,subprocess,time,wave
from pathlib import Path

FRAMES,SECONDS,W,H=2700,45,1920,1080
UNIFORMS={'eye':3,'right':3,'up':3,'forward':3,'clock':4,'build':4,'fit':4,'refine':4,'light':4,'finale':4,'grade':4,'finish':4}
VOICES=['pluck','drone','chime','swell','clack','bass','hat','chord']
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
 if not isinstance(p['audio'],list) or len(p['audio'])>1024:raise ValueError('Invalid audio budget')
 for e in p['audio']:
  if set(e)!={'at','voice','duration','frequency','gain'} or e['voice'] not in VOICES or not vector([e['at'],e['duration'],e['frequency'],e['gain']],4,20000) or not 0<=e['at']<SECONDS or not 0<e['duration']<=4 or not 20<=e['frequency']<=10000 or not 0<e['gain']<=1:raise ValueError('Invalid sound event')
 return p

def soundtrack(events,path):
 rate=48000;n=rate*SECONDS;mix=array.array('f',[0])*(n*2)
 for k,e in enumerate(events):
  start=round(e['at']*rate);length=min(round(e['duration']*rate),n-start);f=e['frequency'];seed=9001+k*733;pan=.5+.3*math.sin(e['at']*1.7+k)
  voice=e['voice']
  for j in range(length):
   t=j/rate;seed=(1664525*seed+1013904223)&0xffffffff;noise=seed/2147483648-1
   if voice=='pluck':v=sum(math.sin(2*math.pi*f*m*t)/m**1.3 for m in (1,2,3,4))*math.exp(-t*(5+f/180))*min(1,t*400)
   elif voice=='drone':v=(math.sin(2*math.pi*f*t)+.5*math.sin(2*math.pi*f*1.5*t+.3*math.sin(t*.7)))*min(1,t*.8)*min(1,(e['duration']-t)*.8)*.6
   elif voice=='chime':v=sum(math.sin(2*math.pi*f*m*t)*a for m,a in ((1,1),(2.76,.4),(5.4,.2)))*math.exp(-t*2.2)*min(1,t*300)
   elif voice=='swell':env=(t/e['duration'])**2;v=(sum(math.sin(2*math.pi*f*m*t) for m in (1,1.5,2))/3*.7+noise*.2)*env
   elif voice=='clack':v=(noise*.6+math.sin(2*math.pi*f*t)*.7+math.sin(2*math.pi*f*2.3*t)*.3)*math.exp(-t*55)
   elif voice=='bass':v=(math.sin(2*math.pi*f*t)+.25*math.sin(4*math.pi*f*t))*min(1,t*150)*math.exp(-t*3.5)
   elif voice=='hat':v=noise*math.exp(-t*85)
   else:v=sum(math.sin(2*math.pi*f*r*t+.2*math.sin(t*2.3)) for r in (1,1.189,1.498,2))/4*min(1,t*5)*math.exp(-t*.8)
   at=(start+j)*2;value=v*e['gain'];mix[at]+=value*(1.15-pan*.5);mix[at+1]+=value*(.65+pan*.5)
 for delay,g in ((round(rate*.131)*2,.18),(round(rate*.257)*2,.1)):
  for k in range(len(mix)-1,delay-1,-1):mix[k]+=g*mix[k-delay]
 pcm=array.array('h');peak=0
 for k,v in enumerate(mix):
  v=math.tanh(v*2.1)*.9*min(1,(n-k//2)/(rate*1.2));peak=max(peak,abs(v));pcm.append(round(v*32767))
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
