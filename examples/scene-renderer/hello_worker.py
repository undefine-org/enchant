#!/usr/bin/env python3
"""Captured BL display lists -> cached Cairo vectors + procedural GLES seed materials.
The UI is an explicitly labeled cinematic reconstruction, not screen capture.
"""
import argparse,array,ctypes as C,hashlib,importlib.util,json,math,os,subprocess,time,wave
from pathlib import Path

def module(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def numbers(v,n):return isinstance(v,list) and len(v)==n and all(type(x) in (int,float) and math.isfinite(x) and abs(x)<1e6 for x in v)
def validate(p):
 if p.get('version')!=1 or p.get('viewport')!=[1920,1080] or p.get('fps')!=[60,1] or p.get('duration')!=60:raise ValueError('Unsupported narrative plan')
 if not isinstance(p.get('assets'),dict) or not 1<=len(p['assets'])<=80 or not isinstance(p.get('frames'),list) or len(p['frames'])!=3600:raise ValueError('Narrative resource budget')
 for asset in p['assets'].values():
  if set(asset)!={'commands'} or not isinstance(asset['commands'],list) or len(asset['commands'])>20000:raise ValueError('Invalid outline asset')
  path_valid(asset['commands'])
 for k,f in enumerate(p['frames']):
  if f.get('frame')!=k or abs(f.get('time',-1)-k/60)>1e-8 or f.get('semantic-ids')!=[f'world/{i}' for i in range(24)]:raise ValueError('Invalid frame clock or semantic identities')
  items=f.get('items')
  if not isinstance(items,list) or not 1<=len(items)<=400 or len({v.get('id') for v in items})!=len(items):raise ValueError('Invalid display order/identity')
  for v in items:
   if not numbers(v.get('matrix'),6) or not numbers(v.get('clip'),4) or min(v['clip'][2:])<0 or v['matrix'][0]*v['matrix'][3]-v['matrix'][1]*v['matrix'][2]<=1e-12:raise ValueError('Invalid transform/clip')
   kind=v.get('kind')
   allowed={'id','kind','matrix','clip','fill','stroke','width','grain'}
   fields={'rect':{'box','radius'},'asset':{'asset'},'curve':{'points'},'path':{'commands'},'seed':{'center','radius','angle','material','seed','phase'}}
   if kind not in fields or set(v)-allowed-fields[kind]:raise ValueError('Unsupported display item')
   for paint in ['fill','stroke']:
    if paint in v:color(v[paint])
   if 'width' in v and (not numbers([v['width']],1) or not 0<v['width']<=20):raise ValueError('Invalid stroke')
   if kind=='rect' and (not numbers(v.get('box'),4) or min(v['box'][2:])<0 or not numbers([v.get('radius')],1) or v['radius']<0):raise ValueError('Invalid box')
   if kind=='curve' and not numbers(v.get('points'),8):raise ValueError('Invalid connector')
   if kind=='asset' and v.get('asset') not in p['assets']:raise ValueError('Missing glyph resource')
   if kind=='path':path_valid(v.get('commands'))
   if kind=='seed' and (not numbers(v.get('center'),2) or not numbers([v.get('radius'),v.get('angle'),v.get('phase'),v.get('seed')],4) or not 0<v['radius']<=200 or not numbers(v.get('material'),3) or min(v['material'])<0 or abs(sum(v['material'])-1)>1e-6):raise ValueError('Invalid material instance')
 audio=p.get('audio')
 if not isinstance(audio,list) or len(audio)>512:raise ValueError('Invalid audio resource budget')
 for e in audio:
  if set(e)!={'at','voice','duration','frequency','gain'} or e['voice'] not in ['bass','kick','chord','hat','tick','sweep'] or not numbers([e['at'],e['duration'],e['frequency'],e['gain']],4) or not 0<=e['at']<60 or not 0<e['duration']<=4 or not 20<=e['frequency']<=10000 or not 0<e['gain']<=1:raise ValueError('Invalid audio event')
 return p
def path_valid(commands):
 if not isinstance(commands,list) or len(commands)>20000:raise ValueError('Invalid path budget')
 for c in commands:
  n={'M':2,'L':2,'C':6,'Z':0}.get(c[0]) if isinstance(c,list) and c else None
  if n is None or not numbers(c[1:],n):raise ValueError('Invalid path command')
def color(v):
 import re
 if not isinstance(v,str) or not re.fullmatch('#[0-9a-fA-F]{6}',v):raise ValueError('Explicit RGB required')
 return tuple(int(v[j:j+2],16)/255 for j in [1,3,5])
class Matrix(C.Structure):_fields_=[(k,C.c_double) for k in ['xx','yx','xy','yy','x0','y0']]
class Painter:
 def __init__(self,helper,rsvg,w,h,assets):
  lib=helper.libraries(rsvg)['cairo'];self.b=lambda n,r,*a:helper.bind(lib,n,r,*a);p=C.c_void_p;d=C.c_double;i=C.c_int
  self.surface=self.b('cairo_image_surface_create',p,i,i,i)(0,w,h);self.cr=self.b('cairo_create',p,p)(self.surface)
  self.identity=self.b('cairo_identity_matrix',None,p);self.matrix=self.b('cairo_set_matrix',None,p,C.POINTER(Matrix))
  self.new=self.b('cairo_new_path',None,p);self.move=self.b('cairo_move_to',None,p,d,d);self.line=self.b('cairo_line_to',None,p,d,d);self.curve=self.b('cairo_curve_to',None,p,*([d]*6));self.closepath=self.b('cairo_close_path',None,p)
  self.rectangle=self.b('cairo_rectangle',None,p,d,d,d,d);self.arc=self.b('cairo_arc',None,p,d,d,d,d,d)
  self.rgb=self.b('cairo_set_source_rgb',None,p,d,d,d);self.fill=self.b('cairo_fill_preserve',None,p);self.stroke=self.b('cairo_stroke',None,p)
  self.width=self.b('cairo_set_line_width',None,p,d);self.save=self.b('cairo_save',None,p);self.restore=self.b('cairo_restore',None,p);self.clip=self.b('cairo_clip',None,p);self.paint=self.b('cairo_paint',None,p)
  self.flush=self.b('cairo_surface_flush',None,p);self.get=self.b('cairo_image_surface_get_data',p,p);self.stride=self.b('cairo_image_surface_get_stride',i,p)
  self.append=self.b('cairo_append_path',None,p,p);self.copy=self.b('cairo_copy_path',p,p);self.pathdestroy=self.b('cairo_path_destroy',None,p)
  self.paths={}
  for key,asset in assets.items():self.new(self.cr);self.emit(asset['commands']);self.paths[key]=self.copy(self.cr)
  self.status=self.b('cairo_status',i,p);self.surface_destroy=self.b('cairo_surface_destroy',None,p);self.destroy=self.b('cairo_destroy',None,p)
  self.w,self.h=w,h
 def emit(self,commands):
  for op,*v in commands:
   if op=='M':self.move(self.cr,*v)
   elif op=='L':self.line(self.cr,*v)
   elif op=='C':self.curve(self.cr,*v)
   else:self.closepath(self.cr)
 def roundrect(self,box,r):
  x,y,w,h=box;r=min(r,w/2,h/2)
  if r==0:self.rectangle(self.cr,x,y,w,h);return
  for cx,cy,a in [(x+w-r,y+r,-math.pi/2),(x+w-r,y+h-r,0),(x+r,y+h-r,math.pi/2),(x+r,y+r,math.pi)]:self.arc(self.cr,cx,cy,r,a,a+math.pi/2)
  self.closepath(self.cr)
 def frame(self,items):
  cr=self.cr;self.identity(cr);self.rgb(cr,*color('#f4f0e4'));self.paint(cr)
  for v in items:
   if v['kind']=='seed':continue
   self.save(cr);self.identity(cr);self.new(cr);self.rectangle(cr,*v['clip']);self.clip(cr)
   self.matrix(cr,C.byref(Matrix(*v['matrix'])));self.new(cr);kind=v['kind']
   if kind=='rect':self.roundrect(v['box'],v['radius'])
   elif kind=='asset':self.append(cr,self.paths[v['asset']])
   elif kind=='curve':self.move(cr,*v['points'][:2]);self.curve(cr,*v['points'][2:])
   else:self.emit(v['commands'])
   if v.get('fill'):self.rgb(cr,*color(v['fill']));self.fill(cr)
   if v.get('stroke'):self.rgb(cr,*color(v['stroke']));self.width(cr,v.get('width',1));self.stroke(cr)
   self.new(cr);self.restore(cr)
  if self.status(cr):raise ValueError('Cairo scene failed')
  self.flush(self.surface)
  if self.stride(self.surface)!=self.w*4:raise ValueError('Unexpected packed stride')
  return C.string_at(self.get(self.surface),self.w*self.h*4)
 def close(self):
  for p in self.paths.values():self.pathdestroy(p)
  self.destroy(self.cr);self.surface_destroy(self.surface)

def soundtrack(events,path):
 # Bounded original synthesis with event-local noise: event order does not change a voice.
 rate=48000;n=rate*60;mix=array.array('f',[0])*(n*2)
 for k,e in enumerate(events):
  if e['voice'] not in ['bass','kick','chord','hat','tick','sweep'] or not 0<=e['at']<60 or not 0<e['duration']<=4 or not 0<e['gain']<=1:raise ValueError('Invalid audio event')
  start=round(e['at']*rate);length=min(round(e['duration']*rate),n-start);seed=7331+k*631
  for j in range(length):
   t=j/rate;f=e['frequency'];seed=(1664525*seed+1013904223)&0xffffffff;noise=seed/2147483648-1
   if e['voice']=='kick':v=(math.sin(2*math.pi*(48*t+100*(1-math.exp(-t*42))/42))+.08*noise*math.exp(-t*100))*math.exp(-t*17)
   elif e['voice']=='bass':v=(math.sin(2*math.pi*f*t)+.16*math.sin(4*math.pi*f*t))*min(1,t*180)*math.exp(-t*6)
   elif e['voice']=='hat':v=noise*math.exp(-t*70)
   elif e['voice']=='tick':v=(math.sin(t*f*2*math.pi)+noise*.25)*math.exp(-t*90)
   elif e['voice']=='sweep':
    env=math.sin(math.pi*t/e['duration'])**2;v=(math.sin(2*math.pi*(f*t+f*t*t*1.4))*.3+noise*.2)*env
   else:v=sum(math.sin(2*math.pi*f*r*t+.2*math.sin(t*3)) for r in [1,1.25,1.5,2])/4*min(1,t*8)*math.exp(-t*1.1)
   at=(start+j)*2;value=v*e['gain'];pan=.08*math.sin(e['at']*.7);mix[at]+=value*(.9-pan);mix[at+1]+=value*(.9+pan)
 delay=round(rate*.173)*2
 for k in range(delay,len(mix)):mix[k]+=.18*mix[k-delay]
 pcm=array.array('h');peak=0
 for k,v in enumerate(mix):
  v=math.tanh(v*1.7)*.88*min(1,(n-k//2)/(rate*.9));peak=max(peak,abs(v));pcm.append(round(v*32767))
 with wave.open(str(path),'wb') as f:f.setnchannels(2);f.setsampwidth(2);f.setframerate(rate);f.writeframes(pcm.tobytes())
 return {'samples':n,'rate':rate,'channels':2,'peak':peak,'sha256':digest(path)}

def run(a):
 started=time.monotonic();folder=a.folder
 if (folder/'plan.json').stat().st_size>256*1024*1024:raise ValueError('Plan byte budget exceeded')
 plan=validate(json.loads((folder/'plan.json').read_text()));request=[int(k) for k in a.selected.split(',')]
 if any(not 0<=k<3600 for k in request):raise ValueError('Selected frame outside range')
 h=module(a.helper,'hello_text');native=module(a.gpu_worker,'hello_gpu');gpu=None;painter=None;encoder=None;temporary=folder/'.pending-hello-world.mp4';hashes={}
 try:
  gpu=native.GPU.__new__(native.GPU);gpu.__init__(a.egl,a.gles,1920,1080)
  painter=Painter(h,a.rsvg,1920,1080,plan['assets'])
  base=gpu.program((a.shaders/'flat.vert').read_text(),(a.shaders/'base.frag').read_text());seed=gpu.program((a.shaders/'seed.vert').read_text(),(a.shaders/'seed.frag').read_text())
  texture=gpu.texture(1920,1080,None);gpu.bindf(0x8d40,gpu.final)
  update=gpu.gb('glTexSubImage2D',None,C.c_uint,C.c_int,C.c_int,C.c_int,C.c_int,C.c_int,C.c_uint,C.c_uint,C.c_void_p)
  scissor=gpu.gb('glScissor',None,*([C.c_int]*4));audio=soundtrack(plan['audio'],folder/'soundtrack.wav') if a.film else None
  args=['ffmpeg','-v','error','-y','-f','rawvideo','-pixel_format','rgba','-video_size','1920x1080','-framerate','60','-i','pipe:0','-i',str(folder/'soundtrack.wav'),'-vf','vflip','-c:v','libx264','-crf','17','-preset','medium','-threads','2','-pix_fmt','yuv420p','-c:a','aac','-b:a','256k','-movflags','+faststart','-t','60',str(temporary)]
  with (folder/'encoder.log').open('wb') as log:
   if a.film:encoder=subprocess.Popen(args,stdin=subprocess.PIPE,stderr=log)
   for k in (range(3600) if a.film else request):
    f=plan['frames'][k];packed=painter.frame(f['items']);gpu.disable(0x0b71);gpu.disable(0x0be2);gpu.disable(0x0c11)
    gpu.bindtex(0x0de1,texture);update(0x0de1,0,0,0,1920,1080,0x1908,0x1401,packed)
    gpu.use(base);gpu.geometry(gpu.quad,2);gpu.draw(5,0,4)
    gpu.enable(0x0be2);gpu.gb('glBlendFunc',None,C.c_uint,C.c_uint)(1,0x0303);gpu.enable(0x0c11);gpu.use(seed);gpu.set(seed,'resolution',[1920,1080])
    for v in f['items']:
     if v['kind']!='seed':continue
     x,y,w,hh=v['clip'];x0=max(0,min(1920,math.floor(x)));x1=max(x0,min(1920,math.ceil(x+w)));y0=max(0,min(1080,math.floor(y)));y1=max(y0,min(1080,math.ceil(y+hh)))
     if x0==x1 or y0==y1:continue
     scissor(x0,1080-y1,x1-x0,y1-y0);aa,b,c,d,tx,ty=v['matrix']
     for name,value in [('linear',[aa,b,c,d]),('offset',[tx,ty]),('seed',v['center']+[v['radius'],v['angle']]),('material',v['material']),('detail',[v['phase'],v['seed']])]:gpu.set(seed,name,value)
     gpu.draw(5,0,4)
    gpu.disable(0x0c11);gpu.disable(0x0be2);gpu.read(0,0,1920,1080,0x1908,0x1401,gpu.pixels);gpu.check();pixels=bytes(gpu.pixels)
    if k in request:native.png(folder/f'{k}.png',pixels,1920,1080);hashes[str(k)]=digest(folder/f'{k}.png')
    if encoder:encoder.stdin.write(pixels)
    if k%120==0:
     progress={'frame':k,'frames':3600,'seconds':time.monotonic()-started};(folder/'progress.json').write_text(json.dumps(progress));print(json.dumps(progress),flush=True)
   if encoder:
    encoder.stdin.close()
    if encoder.wait():raise RuntimeError('Narrative encoder failed')
    temporary.replace(folder/'hello-world.mp4')
  media=None
  if a.film:
   media=json.loads(subprocess.check_output(['ffprobe','-v','error','-count_frames','-show_streams','-of','json',str(folder/'hello-world.mp4')]))
   video=next(s for s in media['streams'] if s['codec_type']=='video');au=next(s for s in media['streams'] if s['codec_type']=='audio')
   if video['nb_read_frames']!='3600' or video['r_frame_rate']!='60/1' or video['width']!=1920 or video['height']!=1080 or abs(float(video['duration'])-60)>.001 or abs(float(au['duration'])-60)>.03:raise ValueError('Encoded narrative clock mismatch')
  report={'seconds':time.monotonic()-started,'gpu':gpu.info,'media':media,'audio':audio,'frame_hashes':hashes,'plan_sha256':digest(folder/'plan.json'),'film_sha256':digest(folder/'hello-world.mp4') if a.film else None,'policy':'BL-authored measured layout, keyed transforms and explicit display order; cached native Cairo outlines + procedural GLES materials; reconstructed concept UI labeled; opaque RGBA / H264 + original stereo AAC'}
  (folder/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 finally:
  if encoder and encoder.poll() is None:encoder.kill();encoder.wait()
  temporary.unlink(missing_ok=True)
  if painter:painter.close()
  if gpu:gpu.close()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('folder',type=Path);p.add_argument('--gpu-worker',required=True,type=Path);p.add_argument('--helper',required=True,type=Path);p.add_argument('--shaders',required=True,type=Path);p.add_argument('--rsvg',required=True);p.add_argument('--egl',required=True);p.add_argument('--gles',required=True);p.add_argument('--film',action='store_true');p.add_argument('--selected',default='0,120,360,660,990,1260,1560,1800,1860,1980,2100,2430,2520,2610,2850,3150,3420,3599');run(p.parse_args())
