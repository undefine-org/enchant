#!/usr/bin/env python3
"""Bounded EGL/GLES executor for the captured ORA layers proof plan.
BL authors every frame value. This worker validates, draws and encodes only.
It reuses the captured MAKE WORLDS GPU context helper; no third-party Python deps.
"""
import argparse,array,ctypes as C,hashlib,importlib.util,json,math,subprocess,time,wave
from pathlib import Path

FRAMES,SECONDS=900,15
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def module(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def vector(v,n,bound=1000):return isinstance(v,list) and len(v)==n and all(type(x) in (int,float) and math.isfinite(x) and abs(x)<bound for x in v)

def validate(p):
 if set(p)!={'version','viewport','fps','duration','frames','audio'} or p['version']!=1 or p['viewport']!=[1920,1080] or p['fps']!=[60,1] or p['duration']!=SECONDS:raise ValueError('Unsupported layers plan')
 if not isinstance(p['frames'],list) or len(p['frames'])!=FRAMES:raise ValueError(f'Expected exactly {FRAMES} frames')
 ids=None
 for k,f in enumerate(p['frames']):
  if set(f)!={'frame','time','eye','view-projection','boxes','floor','motes','finish'} or f['frame']!=k or abs(f['time']-k/60)>1e-8:raise ValueError('Invalid frame clock or channel')
  if not (vector(f['eye'],3) and vector(f['view-projection'],16) and vector(f['floor'],4) and vector(f['motes'],4) and vector(f['finish'],4)):raise ValueError('Nonfinite frame uniform')
  boxes=f['boxes'];order=[b.get('id') for b in boxes] if isinstance(boxes,list) else None
  if not order or len(order)>64 or len(set(order))!=len(order) or (ids is not None and order!=ids):raise ValueError('Boxes must keep stable ordered identities')
  ids=order
  for b in boxes:
   if set(b)!={'id','center','size','material','glow','visible'} or not vector(b['center'],3) or not vector(b['size'],3) or min(b['size'])<=0:raise ValueError('Invalid box geometry')
   if b['material'] not in range(6) or b['visible'] not in (0,1) or not vector([b['glow']],1,10) or b['glow']<0:raise ValueError('Invalid box material')
 if not isinstance(p['audio'],list) or len(p['audio'])>256:raise ValueError('Invalid audio budget')
 for e in p['audio']:
  if set(e)!={'at','voice','duration','frequency','gain'} or e['voice'] not in ['thud','swell','chord','tick','hat','bass'] or not vector([e['at'],e['duration'],e['frequency'],e['gain']],4,20000) or not 0<=e['at']<SECONDS or not 0<e['duration']<=4 or not 20<=e['frequency']<=10000 or not 0<e['gain']<=1:raise ValueError('Invalid sound event')
 return p

def cube():
 values=[]
 for axis in range(3):
  for sign in (-1,1):
   n=[0,0,0];n[axis]=sign;u=(axis+1)%3;v=(axis+2)%3
   corners=[]
   for a,b in [(-1,-1),(1,-1),(1,1),(-1,1)]:
    p=[0,0,0];p[axis]=sign*.5;p[u]=a*.5;p[v]=b*.5;corners.append(p)
   if sign<0:corners.reverse()
   for i in [0,1,2,0,2,3]:values.extend(corners[i]+n)
 return values

def soundtrack(events,path):
 rate=48000;n=rate*SECONDS;mix=array.array('f',[0])*(n*2)
 for k,e in enumerate(events):
  start=round(e['at']*rate);length=min(round(e['duration']*rate),n-start);f=e['frequency'];seed=4099+k*977;pan=.5+.2*math.sin(e['at']*2.3)
  for j in range(length):
   t=j/rate;seed=(1664525*seed+1013904223)&0xffffffff;noise=seed/2147483648-1;voice=e['voice']
   if voice=='thud':v=(math.sin(2*math.pi*(f*t+70*(1-math.exp(-t*30))/30))*1.1+noise*.25*math.exp(-t*60))*math.exp(-t*7)
   elif voice=='swell':env=(t/e['duration'])**2.2;v=(sum(math.sin(2*math.pi*f*r*t) for r in (1,1.5,2.01))/3*.6+noise*.25)*env
   elif voice=='chord':v=sum(math.sin(2*math.pi*f*r*t+.25*math.sin(t*2.7)) for r in (1,1.2599,1.4983,2))/4*min(1,t*6)*math.exp(-t*.9)
   elif voice=='tick':v=(math.sin(2*math.pi*f*t)+.3*math.sin(4*math.pi*f*t))*math.exp(-t*38)
   elif voice=='hat':v=noise*math.exp(-t*80)
   else:v=(math.sin(2*math.pi*f*t)+.2*math.sin(4*math.pi*f*t))*min(1,t*150)*math.exp(-t*5)
   at=(start+j)*2;value=v*e['gain'];mix[at]+=value*(1.1-pan*.4);mix[at+1]+=value*(.7+pan*.4)
 delay=round(rate*.143)*2
 for k in range(delay,len(mix)):mix[k]+=.16*mix[k-delay]
 pcm=array.array('h');peak=0
 for k,v in enumerate(mix):
  v=math.tanh(v*1.4)*.9*min(1,(n-k//2)/(rate*.6));peak=max(peak,abs(v));pcm.append(round(v*32767))
 with wave.open(str(path),'wb') as w:w.setnchannels(2);w.setsampwidth(2);w.setframerate(rate);w.writeframes(pcm.tobytes())
 return {'rate':rate,'samples':n,'channels':2,'peak':peak,'events':len(events),'sha256':digest(path)}

def run(a):
 started=time.monotonic();folder=a.folder
 if (folder/'plan.json').stat().st_size>96*1024*1024:raise ValueError('Plan byte budget exceeded')
 plan=validate(json.loads((folder/'plan.json').read_text()));requested=[int(x) for x in a.selected.split(',')];selected=set(requested)
 if any(not 0<=x<FRAMES for x in selected):raise ValueError('Selected frame outside clock')
 native=module(a.gpu_worker,'ora_gpu');w,h=1920,1080
 gpu=None;encoder=None;temporary=folder/'.pending-layers.mp4';hashes={}
 try:
  gpu=native.GPU.__new__(native.GPU);gpu.__init__(a.egl,a.gles,w,h)
  def program(v,f):return gpu.program((a.shaders/v).read_text(),(a.shaders/f).read_text())
  floor=program('floor.vert','floor.frag');boxes=program('box.vert','box.frag');motes=program('mote.vert','mote.frag');post=program('flat.vert','post.frag')
  mesh=gpu.buffer(cube());clear=gpu.gb('glClearColor',None,*([C.c_float]*4));mask=gpu.gb('glDepthMask',None,C.c_ubyte)
  blend=gpu.gb('glBlendFunc',None,C.c_uint,C.c_uint);noattr=gpu.gb('glDisableVertexAttribArray',None,C.c_uint)
  audio=soundtrack(plan['audio'],folder/'soundtrack.wav') if a.film else None
  args=['ffmpeg','-v','error','-y','-f','rawvideo','-pixel_format','rgba','-video_size',f'{w}x{h}','-framerate','60','-i','pipe:0','-i',str(folder/'soundtrack.wav'),'-vf','vflip','-c:v','libx264','-crf','16','-preset','medium','-threads','2','-pix_fmt','yuv420p','-c:a','aac','-b:a','256k','-movflags','+faststart','-t',str(SECONDS),str(temporary)]
  with (folder/'encoder.log').open('wb') as log:
   if a.film:encoder=subprocess.Popen(args,stdin=subprocess.PIPE,stderr=log)
   for k in (range(FRAMES) if a.film else requested):
    f=plan['frames'][k]
    gpu.bindf(0x8d40,gpu.scene);clear(.0063,.0116,.0296,1);gpu.enable(0x0b71);mask(1);gpu.disable(0x0be2);gpu.clear(0x4100)
    gpu.use(floor);gpu.geometry(gpu.quad,2)
    for name,value in [('viewProjection',f['view-projection']),('eye',f['eye']),('floorState',f['floor'])]:gpu.set(floor,name,value)
    gpu.draw(5,0,4)
    gpu.use(boxes);gpu.bindb(0x8892,mesh);gpu.enableattr(0);gpu.attrib(0,3,0x1406,False,24,None);gpu.enableattr(1);gpu.attrib(1,3,0x1406,False,24,C.c_void_p(12))
    gpu.set(boxes,'viewProjection',f['view-projection']);gpu.set(boxes,'eye',f['eye'])
    for b in f['boxes']:
     if not b['visible']:continue
     gpu.set(boxes,'center',b['center']);gpu.set(boxes,'size',b['size']);gpu.set(boxes,'look',[b['material'],b['glow'],f['time'],0])
     gpu.draw(4,0,36)
    noattr(1)
    gpu.use(motes);gpu.geometry(gpu.particles,1);gpu.enable(0x0be2);blend(1,1);mask(0)
    gpu.set(motes,'viewProjection',f['view-projection']);gpu.set(motes,'motes',f['motes']);gpu.draw(0,0,320)
    mask(1);gpu.disable(0x0be2)
    gpu.bindf(0x8ca8,gpu.scene);gpu.bindf(0x8ca9,gpu.resolve)
    gpu.gb('glBlitFramebuffer',None,*([C.c_int]*8),C.c_uint,C.c_uint)(0,0,w,h,0,0,w,h,0x4000,0x2600)
    gpu.bindf(0x8d40,gpu.final);gpu.disable(0x0b71);gpu.use(post);gpu.geometry(gpu.quad,2);gpu.bindtex(0x0de1,gpu.hdr)
    gpu.set(post,'resolution',[w,h]);gpu.set(post,'finish',f['finish']);gpu.draw(5,0,4)
    gpu.read(0,0,w,h,0x1908,0x1401,gpu.pixels);gpu.check();packed=bytes(gpu.pixels)
    if k in selected:path=folder/f'{k}.png';native.png(path,packed,w,h);hashes[str(k)]=digest(path)
    if encoder:encoder.stdin.write(packed)
    if k%60==0:print(json.dumps({'frame':k,'of':FRAMES,'seconds':round(time.monotonic()-started,2)}),flush=True)
   if encoder:
    encoder.stdin.close()
    if encoder.wait()!=0:raise RuntimeError('Encoder failed; see encoder.log')
    temporary.replace(folder/'layers.mp4')
  media=None
  if a.film:
   media=json.loads(subprocess.check_output(['ffprobe','-v','error','-count_frames','-show_streams','-of','json',str(folder/'layers.mp4')]))
   v=next(s for s in media['streams'] if s['codec_type']=='video');au=next(s for s in media['streams'] if s['codec_type']=='audio')
   if v['nb_read_frames']!=str(FRAMES) or v['r_frame_rate']!='60/1' or v['width']!=w or v['height']!=h or abs(float(v['duration'])-SECONDS)>.001 or abs(float(au['duration'])-SECONDS)>.03:raise RuntimeError('Media clock verification failed')
  report={'seconds':time.monotonic()-started,'gpu':gpu.info,'media':media,'audio':audio,'plan_sha256':digest(folder/'plan.json'),'frame_hashes':hashes,
   'film_sha256':digest(folder/'layers.mp4') if a.film else None,'shader_hashes':{p.name:digest(p) for p in sorted(a.shaders.iterdir()) if p.suffix in ['.vert','.frag']},
   'policy':'BL-evaluated boxes/camera/floor/mote controls; RGBA16F / 4x MSAA / depth24; analytic studio light; procedural engraved materials; additive motes; bloom + ACES-like curve; H.264 60 fps + original AAC stereo'}
  (folder/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 finally:
  if encoder and encoder.poll() is None:encoder.kill();encoder.wait()
  temporary.unlink(missing_ok=True)
  if gpu:gpu.close()

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('folder',type=Path);p.add_argument('--shaders',required=True,type=Path);p.add_argument('--gpu-worker',required=True,type=Path)
 p.add_argument('--egl',required=True);p.add_argument('--gles',required=True);p.add_argument('--film',action='store_true')
 p.add_argument('--selected',default='0,90,180,250,282,300,340,420,480,540,600,690,780,840,899');run(p.parse_args())
