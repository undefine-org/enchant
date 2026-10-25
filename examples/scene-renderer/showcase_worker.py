#!/usr/bin/env python3
"""Bounded EGL/GLES executor for captured BL showcase plans. No timeline authoring.
All procedural geometry/shading is explicit captured GLSL. No third-party Python deps.
"""
import argparse,array,ctypes as C,hashlib,importlib.util,json,math,os,re,struct,subprocess,time,wave,zlib
from pathlib import Path

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def bind(lib,name,result,*args):
 f=getattr(lib,name);f.restype=result;f.argtypes=args;return f

def vector(v,n):return isinstance(v,list) and len(v)==n and all(type(x) in (int,float) and math.isfinite(x) and abs(x)<10000 for x in v)
def validate(p):
 if set(p)!={'version','viewport','fps','duration','frames','typography','audio'} or p['version']!=1 or p['viewport']!=[1920,1080] or p['fps']!=[60,1] or p['duration']!=30:raise ValueError('Unsupported showcase plan')
 if not isinstance(p['frames'],list) or len(p['frames'])!=1800:raise ValueError('Expected exactly 1800 frames')
 specs=p['typography']
 if not isinstance(specs,list) or len(specs)!=8 or len({s['id'] for s in specs})!=8:raise ValueError('Invalid typography resources')
 for s in specs:
  if not isinstance(s['id'],str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,47}',s['id']) or not vector(s.get('ink-bounds'),4) or not 0<s['ink-bounds'][2]<=4096 or not 0<s['ink-bounds'][3]<=1024 or not isinstance(s.get('path'),str) or len(s['path'])>2000000 or not re.fullmatch(r'[MLCQZ0-9eE+.,\s-]+',s['path']):raise ValueError('Invalid shaped typography')
 ids=[s['id'] for s in specs]
 sizes={'eye':3,'view-projection':16,'shape':4,'gesture':4,'placement':4,'material':4,'accent':3,'atmosphere':4,'finish':4}
 for k,f in enumerate(p['frames']):
  if set(f)!=set(sizes)|{'frame','time','types'} or f['frame']!=k or abs(f['time']-k/60)>1e-8:raise ValueError('Invalid frame clock or unsupported channel')
  if not all(vector(f.get(n),s) for n,s in sizes.items()):raise ValueError('Nonfinite/missing shader uniform')
  if min(f['shape'])<0 or abs(sum(f['shape'])-1)>1e-6 or not .03<f['gesture'][3]<.5:raise ValueError('Invalid geometric controls')
  if any(not 0<=v<=1 for v in f['material'][1:]+f['accent']+[f['atmosphere'][0]]):raise ValueError('Invalid material range')
  if not isinstance(f['types'],list) or [v.get('id') for v in f['types']]!=ids:raise ValueError('Typography must preserve ordered identities')
  for v in f['types']:
   if set(v)!={'id','rect','gesture','ink','plane'} or not vector(v['rect'],4) or min(v['rect'][2:])<=0 or not vector(v['gesture'],4) or not vector(v['ink'],3) or v['plane'] not in ['front','back']:raise ValueError('Invalid type transform')
 if not isinstance(p['audio'],list) or len(p['audio'])>512:raise ValueError('Invalid audio budget')
 for e in p['audio']:
  if set(e)!={'at','voice','duration','frequency','gain'} or e['voice'] not in ['kick','bass','hat','snare','chord'] or not vector([e['at'],e['duration'],e['frequency'],e['gain']],4) or not 0<=e['at']<30 or not 0<e['duration']<=4 or not 20<=e['frequency']<=10000 or not 0<e['gain']<=1:raise ValueError('Invalid sound event')
 return p

def png(path,data,w,h):
 def chunk(name,value):return struct.pack('!I',len(value))+name+value+struct.pack('!I',zlib.crc32(name+value)&0xffffffff)
 # GLES readback is bottom-up. Keep this convention through the packed encoder.
 raw=b''.join(b'\x00'+data[y*w*4:(y+1)*w*4] for y in range(h-1,-1,-1))
 path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',w,h,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(raw,4))+chunk(b'IEND',b''))

class GPU:
 def __init__(self,egl,gles,w,h):
  self.w,self.h=w,h;self.e=C.CDLL(egl);self.g=C.CDLL(gles);self.buffers=[];self.textures=[];self.fbos=[];self.rbos=[];self.programs=[];self.shaders=[]
  self.display=self.context=None
  p=C.c_void_p;i=C.c_int;u=C.c_uint
  self.eb=lambda n,r,*a:bind(self.e,n,r,*a)
  self.gb=lambda n,r,*a:bind(self.g,n,r,*a)
  get=self.eb('eglGetPlatformDisplay',p,u,p,C.POINTER(i));self.display=get(0x31dd,None,None)
  a,b=i(),i()
  if not self.eb('eglInitialize',u,p,C.POINTER(i),C.POINTER(i))(self.display,C.byref(a),C.byref(b)):raise RuntimeError('EGL initialize failed')
  attrs=(i*11)(0x3033,1,0x3040,0x40,0x3024,8,0x3023,8,0x3022,8,0x3038);config=p();n=i()
  if not self.eb('eglChooseConfig',u,p,C.POINTER(i),C.POINTER(p),i,C.POINTER(i))(self.display,attrs,C.byref(config),1,C.byref(n)) or n.value!=1:raise RuntimeError('EGL config failed')
  self.eb('eglBindAPI',u,u)(0x30a0)
  self.context=self.eb('eglCreateContext',p,p,p,p,C.POINTER(i))(self.display,config,None,(i*3)(0x3098,3,0x3038))
  if not self.context or not self.eb('eglMakeCurrent',u,p,p,p,p)(self.display,None,None,self.context):raise RuntimeError('EGL context failed')
  getstr=self.gb('glGetString',C.c_char_p,u)
  self.info={k:getstr(v).decode() for k,v in [('renderer',0x1f01),('version',0x1f02),('vendor',0x1f00)]}
  print(json.dumps(self.info),flush=True)
  self.enable=self.gb('glEnable',None,u);self.disable=self.gb('glDisable',None,u)
  self.bindf=self.gb('glBindFramebuffer',None,u,u);self.viewport=self.gb('glViewport',None,i,i,i,i)
  self.use=self.gb('glUseProgram',None,u);self.loc=self.gb('glGetUniformLocation',i,u,C.c_char_p)
  self.uniforms={}
  self.draw=self.gb('glDrawArrays',None,u,i,i)
  self.bindb=self.gb('glBindBuffer',None,u,u)
  self.attrib=self.gb('glVertexAttribPointer',None,u,i,u,C.c_ubyte,i,p)
  self.enableattr=self.gb('glEnableVertexAttribArray',None,u)
  self.bindtex=self.gb('glBindTexture',None,u,u)
  self.active=self.gb('glActiveTexture',None,u);self.active(0x84c0)
  self.clear=self.gb('glClear',None,u)
  self.read=self.gb('glReadPixels',None,i,i,i,i,u,u,p)
  self.error=self.gb('glGetError',u)
  self.pixels=(C.c_ubyte*(w*h*4))()
  self.viewport(0,0,w,h)
  self.hdr=self.texture(w,h,None,0x881a,0x140b)
  self.resolve=self.framebuffer(self.hdr,False)
  self.scene=self.multisample()
  self.finaltex=self.texture(w,h,None);self.final=self.framebuffer(self.finaltex,False)
  self.quad=self.buffer([-1,-1,1,-1,-1,1,1,1]);self.mesh=self.ribbon();self.particles=self.buffer(list(range(320)))
 def check(self):
  e=self.error()
  if e:raise RuntimeError(f'GLES error {e:#x}')
 def gen(self,name,owned):
  v=C.c_uint();self.gb(name,None,C.c_int,C.POINTER(C.c_uint))(1,C.byref(v));owned.append(v.value);return v.value
 def texture(self,w,h,data,internal=0x1908,kind=0x1401):
  tex=self.gen('glGenTextures',self.textures);self.bindtex(0x0de1,tex)
  self.gb('glTexImage2D',None,C.c_uint,C.c_int,C.c_int,C.c_int,C.c_int,C.c_int,C.c_uint,C.c_uint,C.c_void_p)(0x0de1,0,internal,w,h,0,0x1908,kind,data)
  for key,val in [(0x2801,0x2601),(0x2800,0x2601),(0x2802,0x812f),(0x2803,0x812f)]:self.gb('glTexParameteri',None,C.c_uint,C.c_uint,C.c_int)(0x0de1,key,val)
  return tex
 def framebuffer(self,texture,depth):
  f=self.gen('glGenFramebuffers',self.fbos);self.bindf(0x8d40,f)
  self.gb('glFramebufferTexture2D',None,*([C.c_uint]*5))(0x8d40,0x8ce0,0x0de1,texture,0)
  if depth:
   r=self.gen('glGenRenderbuffers',self.rbos)
   self.gb('glBindRenderbuffer',None,C.c_uint,C.c_uint)(0x8d41,r)
   self.gb('glRenderbufferStorage',None,C.c_uint,C.c_uint,C.c_int,C.c_int)(0x8d41,0x81a6,self.w,self.h)
   self.gb('glFramebufferRenderbuffer',None,*([C.c_uint]*4))(0x8d40,0x8d00,0x8d41,r)
  if self.gb('glCheckFramebufferStatus',C.c_uint,C.c_uint)(0x8d40)!=0x8cd5:raise RuntimeError('Incomplete framebuffer: HDR colour buffer support is required')
  return f
 def multisample(self):
  f=self.gen('glGenFramebuffers',self.fbos);self.bindf(0x8d40,f)
  for internal,attachment in [(0x881a,0x8ce0),(0x81a6,0x8d00)]:
   r=self.gen('glGenRenderbuffers',self.rbos)
   self.gb('glBindRenderbuffer',None,C.c_uint,C.c_uint)(0x8d41,r)
   self.gb('glRenderbufferStorageMultisample',None,C.c_uint,C.c_int,C.c_uint,C.c_int,C.c_int)(0x8d41,4,internal,self.w,self.h)
   self.gb('glFramebufferRenderbuffer',None,*([C.c_uint]*4))(0x8d40,attachment,0x8d41,r)
  if self.gb('glCheckFramebufferStatus',C.c_uint,C.c_uint)(0x8d40)!=0x8cd5:raise RuntimeError('Four-sample HDR framebuffer unsupported')
  return f
 def buffer(self,values):
  data=array.array('f',values);raw=data.tobytes();v=self.gen('glGenBuffers',self.buffers);self.bindb(0x8892,v)
  self.gb('glBufferData',None,C.c_uint,C.c_ssize_t,C.c_void_p,C.c_uint)(0x8892,len(raw),raw,0x88e4)
  return v
 def ribbon(self):
  values=[];n,m=384,12
  for band in range(5):
   for i in range(n):
    for j in range(m):
     for a,b in [(i,j),(i+1,j),(i,j+1),(i,j+1),(i+1,j),(i+1,j+1)]:values.extend([a/n,b/m*2-1,band])
  self.vertices=len(values)//3
  return self.buffer(values)
 def program(self,vertex,fragment):
  u=C.c_uint;i=C.c_int;p=C.c_void_p
  shaders=[]
  for kind,source in [(0x8b31,vertex),(0x8b30,fragment)]:
   s=self.gb('glCreateShader',u,u)(kind);self.shaders.append(s);raw=source.encode();text=C.c_char_p(raw)
   self.gb('glShaderSource',None,u,i,C.POINTER(C.c_char_p),p)(s,1,C.byref(text),None)
   self.gb('glCompileShader',None,u)(s);ok=i();self.gb('glGetShaderiv',None,u,u,C.POINTER(i))(s,0x8b81,C.byref(ok))
   if not ok.value:
    log=C.create_string_buffer(8192);self.gb('glGetShaderInfoLog',None,u,i,p,p)(s,8192,None,log);raise RuntimeError(log.value.decode())
   shaders.append(s)
  program=self.gb('glCreateProgram',u)();self.programs.append(program)
  for s in shaders:self.gb('glAttachShader',None,u,u)(program,s)
  self.gb('glLinkProgram',None,u)(program);ok=i();self.gb('glGetProgramiv',None,u,u,C.POINTER(i))(program,0x8b82,C.byref(ok))
  if not ok.value:
   log=C.create_string_buffer(8192);self.gb('glGetProgramInfoLog',None,u,i,p,p)(program,8192,None,log);raise RuntimeError(log.value.decode())
  return program
 def set(self,program,name,value):
  key=(program,name)
  if key not in self.uniforms:self.uniforms[key]=self.loc(program,name.encode())
  loc=self.uniforms[key]
  if loc<0:return
  n=len(value);data=(C.c_float*n)(*value)
  if n==16:self.gb('glUniformMatrix4fv',None,C.c_int,C.c_int,C.c_ubyte,C.c_void_p)(loc,1,False,data)
  else:self.gb(f'glUniform{n}fv',None,C.c_int,C.c_int,C.c_void_p)(loc,1,data)
 def geometry(self,buffer,n):
  self.bindb(0x8892,buffer);self.enableattr(0);self.attrib(0,n,0x1406,False,0,None)
 def close(self):
  if self.context:
   for name,items in [('glDeleteBuffers',self.buffers),('glDeleteTextures',self.textures),('glDeleteFramebuffers',self.fbos),('glDeleteRenderbuffers',self.rbos)]:
    if items:self.gb(name,None,C.c_int,C.c_void_p)(len(items),(C.c_uint*len(items))(*items))
   for v in self.programs:self.gb('glDeleteProgram',None,C.c_uint)(v)
   for v in self.shaders:self.gb('glDeleteShader',None,C.c_uint)(v)
   self.eb('eglMakeCurrent',C.c_uint,*([C.c_void_p]*4))(self.display,None,None,None)
   self.eb('eglDestroyContext',C.c_uint,C.c_void_p,C.c_void_p)(self.display,self.context)
  if self.display:self.eb('eglTerminate',C.c_uint,C.c_void_p)(self.display)

def type_textures(gpu,plan,folder,rsvg,helper):
 spec=importlib.util.spec_from_file_location('showcase_text',helper);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 lib=module.libraries(rsvg)['cairo'];p=C.c_void_p;i=C.c_int
 load=bind(lib,'cairo_image_surface_create_from_png',p,C.c_char_p);destroy=bind(lib,'cairo_surface_destroy',None,p)
 get=bind(lib,'cairo_image_surface_get_data',p,p);stride=bind(lib,'cairo_image_surface_get_stride',i,p);flush=bind(lib,'cairo_surface_flush',None,p)
 status=bind(lib,'cairo_surface_status',i,p);result={}
 for s in plan['typography']:
  x,y,w,h=s['ink-bounds'];pad=8;width=min(2048,math.ceil(w+pad*2));height=math.ceil((h+pad*2)*width/(w+pad*2))
  svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="{x-pad} {y-pad} {w+pad*2} {h+pad*2}"><path fill="white" d="{s["path"]}"/></svg>'
  path=folder/f'type-{s["id"]}.svg';path.write_text(svg);image=path.with_suffix('.png')
  subprocess.run([rsvg,'-o',str(image),str(path)],check=True)
  surface=load(os.fsencode(image))
  try:
   if status(surface):raise ValueError('Invalid text surface')
   flush(surface);step=stride(surface);raw=C.string_at(get(surface),step*height)
   packed=b''.join(raw[y*step:y*step+width*4] for y in range(height));rgba=bytearray(packed)
   rgba[0::4]=packed[2::4];rgba[2::4]=packed[0::4]
   result[s['id']]=(gpu.texture(width,height,bytes(rgba)),width/height)
  finally:destroy(surface)
 return result

def soundtrack(events,path):
 rate=48000;n=rate*30;mix=array.array('f',[0])*(n*2);seed=7331
 for e in events:
  start=round(e['at']*rate);length=min(round(e['duration']*rate),n-start);voice=e['voice'];freq=e['frequency'];gain=e['gain'];pan=.5+.23*math.sin(e['at']*3.7)
  for j in range(length):
   t=j/rate;seed=(1664525*seed+1013904223)&0xffffffff;noise=seed/2147483648-1
   if voice=='kick':v=math.sin(2*math.pi*(48*t+102*(1-math.exp(-t*45))/45))*math.exp(-t*17)+noise*.13*math.exp(-t*180)
   elif voice=='bass':v=(math.sin(2*math.pi*freq*t)+.24*math.sin(2*math.pi*freq*2*t))*min(1,t*150)*math.exp(-t*5)
   elif voice=='hat':v=noise*math.exp(-t*65)*(.5+.5*math.sin(t*freq*2*math.pi))
   elif voice=='snare':v=(noise*.8+math.sin(t*freq*2*math.pi)*.4)*math.exp(-t*24)
   else:v=sum(math.sin(t*freq*r*2*math.pi+.2*math.sin(t*4)) for r in [1,1.25,1.5,2])/4*min(1,t*15)*math.exp(-t*1.7)
   at=(start+j)*2;value=v*gain;mix[at]+=value*(1-pan*.35);mix[at+1]+=value*(.65+pan*.35)
 # Deterministic short stereo reflections; a controlled tail, not clipped ending.
 delay=round(rate*.117)*2
 for k in range(delay,len(mix)):mix[k]+=.12*mix[k-delay]
 peak=max(abs(v) for v in mix);pcm=array.array('h')
 for k,v in enumerate(mix):
  fade=min(1,(n-k//2)/(rate*.35));pcm.append(round(math.tanh(v*1.25)*.88*32767*fade))
 with wave.open(str(path),'wb') as f:f.setnchannels(2);f.setsampwidth(2);f.setframerate(rate);f.writeframes(pcm.tobytes())
 return {'sample_rate':rate,'samples':n,'channels':2,'peak_before_soft_limit':peak,'sha256':digest(path),'score_events':len(events)}

def run(args):
 started=time.monotonic();folder=args.folder
 if (folder/'plan.json').stat().st_size>32*1024*1024:raise ValueError('Plan byte budget exceeded')
 plan=validate(json.loads((folder/'plan.json').read_text()));requested=[int(x) for x in args.selected.split(',')];selected=set(requested)
 if any(not 0<=x<1800 for x in selected):raise ValueError('Selected frame outside clock')
 w,h=args.width,args.height
 if w<320 or w>1920 or h<180 or h>1080 or w*9!=h*16:raise ValueError('Unsupported bounded review size')
 if args.film and (w,h)!=(1920,1080):raise ValueError('Canonical film must be 1080p')
 gpu=None;encoder=None;temporary=folder/'.pending-showcase.mp4';hashes={}
 try:
  gpu=GPU.__new__(GPU);gpu.__init__(args.egl,args.gles,w,h)
  shaders=args.shaders
  def program(a,b):return gpu.program((shaders/a).read_text(),(shaders/b).read_text())
  bg=program('flat.vert','background.frag');surface=program('surface.vert','surface.frag');typeprog=program('type.vert','type.frag');post=program('flat.vert','post.frag');particles=program('particle.vert','particle.frag')
  textures=type_textures(gpu,plan,folder,args.rsvg,args.text_worker)
  audio=soundtrack(plan['audio'],folder/'soundtrack.wav') if args.film else None
  encoder_args=['ffmpeg','-v','error','-y','-f','rawvideo','-pixel_format','rgba','-video_size',f'{w}x{h}','-framerate','60','-i','pipe:0','-i',str(folder/'soundtrack.wav'),'-vf','vflip','-c:v','libx264','-crf','17','-preset','medium','-threads','2','-pix_fmt','yuv420p','-c:a','aac','-b:a','256k','-movflags','+faststart','-t','30',str(temporary)]
  with (folder/'encoder.log').open('wb') as log:
   if args.film:encoder=subprocess.Popen(encoder_args,stdin=subprocess.PIPE,stderr=log)
   for k in (range(1800) if args.film else requested):
    f=plan['frames'][k]
    gpu.bindf(0x8d40,gpu.scene);gpu.disable(0x0b71);gpu.disable(0x0be2);gpu.clear(0x4100)
    gpu.use(bg);gpu.geometry(gpu.quad,2)
    for name,value in [('resolution',[w,h]),('atmosphere',f['atmosphere']),('accent',f['accent'])]:gpu.set(bg,name,value)
    gpu.draw(5,0,4)
    gpu.enable(0x0be2);gpu.gb('glBlendFunc',None,C.c_uint,C.c_uint)(1,0x0303)
    gpu.use(typeprog)
    for instance in [v for v in f['types'] if v['plane']=='back']:
     texture,aspect=textures[instance['id']];gpu.bindtex(0x0de1,texture);rect=instance['rect'].copy();rect[3]=rect[2]/aspect
     for name,value in [('rect',rect),('typeGesture',instance['gesture']),('ink',instance['ink'])]:gpu.set(typeprog,name,value)
     gpu.draw(5,0,4)
    gpu.disable(0x0be2);gpu.enable(0x0b71);gpu.use(surface);gpu.geometry(gpu.mesh,3)
    for name,key in [('viewProjection','view-projection'),('eye','eye'),('shape','shape'),('gesture','gesture'),('placement','placement'),('material','material'),('accent','accent')]:gpu.set(surface,name,f[key])
    gpu.draw(4,0,gpu.vertices)
    gpu.use(particles);gpu.geometry(gpu.particles,1)
    for name,key in [('viewProjection','view-projection'),('gesture','gesture'),('placement','placement'),('accent','accent'),('atmosphere','atmosphere')]:gpu.set(particles,name,f[key])
    gpu.draw(0,0,320)
    gpu.disable(0x0b71);gpu.enable(0x0be2);gpu.use(typeprog);gpu.geometry(gpu.quad,2)
    for instance in [v for v in f['types'] if v['plane']=='front']:
     texture,aspect=textures[instance['id']];gpu.bindtex(0x0de1,texture);rect=instance['rect'].copy();rect[3]=rect[2]/aspect
     for name,value in [('rect',rect),('typeGesture',instance['gesture']),('ink',instance['ink'])]:gpu.set(typeprog,name,value)
     gpu.draw(5,0,4)
    gpu.disable(0x0be2)
    gpu.bindf(0x8ca8,gpu.scene);gpu.bindf(0x8ca9,gpu.resolve)
    gpu.gb('glBlitFramebuffer',None,*([C.c_int]*8),C.c_uint,C.c_uint)(0,0,w,h,0,0,w,h,0x4000,0x2600)
    gpu.bindf(0x8d40,gpu.final);gpu.disable(0x0b71);gpu.use(post);gpu.geometry(gpu.quad,2);gpu.bindtex(0x0de1,gpu.hdr)
    gpu.set(post,'resolution',[w,h]);gpu.set(post,'finish',f['finish']);gpu.draw(5,0,4)
    gpu.read(0,0,w,h,0x1908,0x1401,gpu.pixels);gpu.check();packed=bytes(gpu.pixels)
    if k in selected:
     path=folder/f'{k}.png';png(path,packed,w,h);hashes[str(k)]=digest(path)
    if encoder:encoder.stdin.write(packed)
    if k%60==0:
     (folder/'progress.json').write_text(json.dumps({'frame':k,'of':1800,'seconds':time.monotonic()-started}));print(f'frame {k}/1800',flush=True)
   if encoder:
    encoder.stdin.close()
    if encoder.wait()!=0:raise RuntimeError('Encoder failed; see encoder.log')
    temporary.replace(folder/'showcase.mp4')
  media=None
  if args.film:
   media=json.loads(subprocess.check_output(['ffprobe','-v','error','-count_frames','-show_streams','-of','json',str(folder/'showcase.mp4')]))
   v=next(s for s in media['streams'] if s['codec_type']=='video');a=next(s for s in media['streams'] if s['codec_type']=='audio')
   if v['nb_read_frames']!='1800' or v['r_frame_rate']!='60/1' or v['width']!=1920 or v['height']!=1080 or abs(float(v['duration'])-30)>.001 or a['sample_rate']!='48000' or abs(float(a['duration'])-30)>.03:raise RuntimeError('Media clock verification failed')
  report={'seconds':time.monotonic()-started,'gpu':gpu.info,'viewport':[w,h],'media':media,'audio':audio,'plan_sha256':digest(folder/'plan.json'),'frame_hashes':hashes,'film_sha256':digest(folder/'showcase.mp4') if args.film else None,'shader_hashes':{p.name:digest(p) for p in sorted(shaders.iterdir()) if p.suffix in ['.vert','.frag']},'policy':'RGBA16F scene / 4x MSAA / depth24 / analytic studio lighting / UV-locked materials / ACES-like tone curve / opaque RGBA8 readback / H.264 60fps + original synthesized AAC stereo','encode_args':encoder_args if args.film else None}
  (folder/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 finally:
  if encoder and encoder.poll() is None:encoder.kill();encoder.wait()
  temporary.unlink(missing_ok=True)
  if gpu:gpu.close()

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('folder',type=Path);p.add_argument('--shaders',required=True,type=Path);p.add_argument('--rsvg',required=True);p.add_argument('--text-worker',required=True,type=Path)
 p.add_argument('--egl',required=True);p.add_argument('--gles',required=True);p.add_argument('--film',action='store_true');p.add_argument('--width',type=int,default=1920);p.add_argument('--height',type=int,default=1080);p.add_argument('--selected',default='0,120,300,480,660,840,1020,1200,1440,1680,1799');run(p.parse_args())
