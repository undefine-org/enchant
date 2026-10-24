#!/usr/bin/env python3
"""Graphics only: captured static atlas + BL frame matrices -> packed frames.
No scene construction or camera interpolation occurs in this worker.
"""
import argparse
import ctypes as C
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def validate(plan):
    if plan.get('version') != 1:
        raise ValueError('Unsupported camera plan version')
    viewport, world, density, fps = (plan.get(k) for k in ['viewport','world','density','fps'])
    for size in [viewport, world]:
        if not isinstance(size,list) or len(size)!=2 or any(type(v) is not int or not 1<=v<=20000 for v in size):
            raise ValueError('Invalid camera dimensions')
    if viewport[0]%2 or viewport[1]%2 or viewport[0]>4096 or viewport[1]>4096:
        raise ValueError('Output must have even dimensions within 4096 pixels')
    if type(density) is not int or not 1<=density<=4 or world[0]*world[1]*density*density>80000000:
        raise ValueError('Atlas exceeds its pixel budget')
    if not isinstance(fps,list) or len(fps)!=2 or any(type(v) is not int or not 1<=v<=1000 for v in fps):
        raise ValueError('Invalid rational frame rate')
    frames=plan.get('frames')
    if not isinstance(frames,list) or not 1<=len(frames)<=10000:
        raise ValueError('Invalid frame count')
    for k,frame in enumerate(frames):
        matrix=frame.get('matrix')
        if frame.get('frame')!=k or not isinstance(matrix,list) or len(matrix)!=6 or any(type(v) not in [int,float] or not math.isfinite(v) or abs(v)>1e6 for v in matrix):
            raise ValueError('Invalid ordered frame matrix')
        a,b,c,d,_,_=matrix
        if a*d-b*c<=1e-8:
            raise ValueError('Camera matrix must preserve nondegenerate orientation')
        t=frame.get('time')
        if type(t) not in [int,float] or not math.isfinite(t) or abs(t-k*fps[1]/fps[0])>1e-8:
            raise ValueError('Frame time differs from rational clock')
    duration=plan.get('duration')
    if type(duration) not in [int,float] or not math.isfinite(duration) or abs(duration-len(frames)*fps[1]/fps[0])>1e-8:
        raise ValueError('Duration differs from exact frame range')
    return plan

class Matrix(C.Structure):
    _fields_=[(key,C.c_double) for key in ['xx','yx','xy','yy','x0','y0']]

class Painter:
    def __init__(self, helper, rsvg):
        lib=helper.libraries(rsvg)['cairo'];bind=helper.bind
        ptr,integer,dbl=C.c_void_p,C.c_int,C.c_double
        self.load=bind(lib,'cairo_image_surface_create_from_png',ptr,C.c_char_p)
        self.create_surface=bind(lib,'cairo_image_surface_create',ptr,integer,integer,integer)
        self.create=bind(lib,'cairo_create',ptr,ptr)
        self.identity=bind(lib,'cairo_identity_matrix',None,ptr)
        self.matrix=bind(lib,'cairo_set_matrix',None,ptr,C.POINTER(Matrix))
        self.rgb=bind(lib,'cairo_set_source_rgb',None,ptr,dbl,dbl,dbl)
        self.operator=bind(lib,'cairo_set_operator',None,ptr,integer)
        self.paint=bind(lib,'cairo_paint',None,ptr)
        self.source=bind(lib,'cairo_set_source_surface',None,ptr,ptr,dbl,dbl)
        self.get_source=bind(lib,'cairo_get_source',ptr,ptr)
        self.filter=bind(lib,'cairo_pattern_set_filter',None,ptr,integer)
        self.flush=bind(lib,'cairo_surface_flush',None,ptr)
        self.data=bind(lib,'cairo_image_surface_get_data',ptr,ptr)
        self.stride=bind(lib,'cairo_image_surface_get_stride',integer,ptr)
        self.width=bind(lib,'cairo_image_surface_get_width',integer,ptr)
        self.height=bind(lib,'cairo_image_surface_get_height',integer,ptr)
        self.surface_status=bind(lib,'cairo_surface_status',integer,ptr)
        self.status=bind(lib,'cairo_status',integer,ptr)
        self.png=bind(lib,'cairo_surface_write_to_png',integer,ptr,C.c_char_p)
        self.destroy=bind(lib,'cairo_destroy',None,ptr)
        self.destroy_surface=bind(lib,'cairo_surface_destroy',None,ptr)
        self.version=bind(lib,'cairo_version_string',C.c_char_p)().decode()
        self.library=lib._name
        self.atlas=self.surface=self.cr=None

    def open(self, atlas, world, density, width, height):
        self.atlas=self.load(os.fsencode(atlas))
        if self.surface_status(self.atlas) or [self.width(self.atlas),self.height(self.atlas)]!=[v*density for v in world]:
            raise ValueError('Atlas is invalid or its size differs from declared density')
        self.surface=self.create_surface(0,width,height) # native ARGB32
        if self.surface_status(self.surface):raise ValueError('Output surface allocation failed')
        self.cr=self.create(self.surface)
        if self.status(self.cr):raise ValueError('Cairo context allocation failed')
        self.bytes=self.stride(self.surface)*height
        if self.stride(self.surface)!=width*4:raise ValueError('Unsupported packed output stride')

    def frame(self, matrix, density, output_scale):
        self.identity(self.cr);self.operator(self.cr,1) # SOURCE
        self.rgb(self.cr,229/255,222/255,203/255);self.paint(self.cr)
        a,b,c,d,x,y=matrix;s=output_scale
        self.matrix(self.cr,C.byref(Matrix(a*s/density,b*s/density,c*s/density,d*s/density,x*s,y*s)))
        self.operator(self.cr,2) # OVER
        self.source(self.cr,self.atlas,0,0)
        self.filter(self.get_source(self.cr),2) # CAIRO_FILTER_BEST
        self.paint(self.cr)
        if self.status(self.cr):raise ValueError('Camera paint failed')
        self.flush(self.surface)

    def save(self,path):
        if self.png(self.surface,os.fsencode(path)):raise ValueError('Cannot write camera specimen')

    def packed(self):return C.string_at(self.data(self.surface),self.bytes)

    def close(self):
        if self.cr:self.destroy(self.cr)
        if self.surface:self.destroy_surface(self.surface)
        if self.atlas:self.destroy_surface(self.atlas)

def run(args):
    started=time.monotonic();folder=args.folder
    plan=validate(json.loads((folder/'camera.json').read_text()))
    selected={int(v) for v in args.selected.split(',') if v}
    if not selected or any(not 0<=k<len(plan['frames']) for k in selected):raise ValueError('Invalid selected frames')
    width=args.width or plan['viewport'][0]
    if type(width) is not int or not 2<=width<=4096 or width%2:raise ValueError('Invalid output width')
    scale=width/plan['viewport'][0];height=round(plan['viewport'][1]*scale)
    if height%2:raise ValueError('Output height must be even')
    if args.film and sys.byteorder!='little':raise ValueError('BGRA stream requires a little-endian host')
    helper=module(args.text_worker,'scene_camera_text')
    raster=module(args.raster_worker,'scene_camera_raster')
    atlas=folder/'atlas.png'
    if not atlas.exists():
        source=raster.lower_materials(folder/'world.svg',folder,args.rsvg,os.environ.copy())
        subprocess.run([args.rsvg,'--zoom',str(plan['density']),'-o',str(atlas),str(source)],check=True)
    painter=Painter(helper,args.rsvg);encoder=None
    temporary=folder/'.pending-film.mp4';output=folder/'presentation.mp4'
    hashes={};encoder_args=None
    try:
        painter.open(atlas,plan['world'],plan['density'],width,height)
        with (folder/'encoder.log').open('wb') as log:
            if args.film:
                n,d=plan['fps']
                encoder_args=['ffmpeg','-v','error','-y','-f','rawvideo','-pixel_format','bgra',
                    '-video_size',f'{width}x{height}','-framerate',f'{n}/{d}','-i','pipe:0','-an',
                    '-c:v','libx264','-crf','17','-preset','medium','-pix_fmt','yuv420p','-threads','1',
                    '-movflags','+faststart','-f','mp4',str(temporary)]
                encoder=subprocess.Popen(encoder_args,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=log)
            for k,frame in enumerate(plan['frames']):
                if not args.film and k not in selected:continue
                painter.frame(frame['matrix'],plan['density'],scale)
                if k in selected:
                    png=folder/f'{k}.png';painter.save(png);hashes[str(k)]=digest(png)
                if encoder:encoder.stdin.write(painter.packed())
                if k%48==0:
                    (folder/'progress.json.tmp').write_text(json.dumps({'frame':k,'frames':len(plan['frames'])}))
                    (folder/'progress.json.tmp').replace(folder/'progress.json')
            if encoder:
                encoder.stdin.close()
                if encoder.wait()!=0:raise ValueError('Encoder failed; see encoder.log')
                temporary.replace(output)
        probe=None
        if args.film:
            probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-count_frames','-select_streams','v:0',
                '-show_entries','stream=nb_read_frames,width,height,duration,r_frame_rate','-of','json',str(output)]))['streams'][0]
            if int(probe['nb_read_frames'])!=len(plan['frames']) or [probe['width'],probe['height']]!=[width,height] or abs(float(probe['duration'])-plan['duration'])>=.001:
                raise ValueError('Encoded film differs from the admitted frame range')
        report={'version':1,'atlas_sha256':digest(atlas),'camera_plan_sha256':digest(folder/'camera.json'),
                'atlas_density':plan['density'],'filter':'CAIRO_FILTER_BEST','output':[width,height],
                'pixel_policy':'native premultiplied ARGB32, opaque background; little-endian BGRA stream; sRGB encoded composition',
                'cairo':painter.version,'cairo_library':painter.library,'selected_frame_hashes':hashes,
                'encode_args':encoder_args,'media':probe,'mp4_sha256':digest(output) if args.film else None,
                'seconds':time.monotonic()-started}
        (folder/'camera-report.json').write_text(json.dumps(report,indent=2)+'\n')
    finally:
        if encoder and encoder.poll() is None:
            encoder.kill();encoder.wait()
        temporary.unlink(missing_ok=True)
        painter.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path)
    p.add_argument('--rsvg',required=True);p.add_argument('--text-worker',required=True,type=Path)
    p.add_argument('--raster-worker',required=True,type=Path);p.add_argument('--film',action='store_true')
    p.add_argument('--selected',default='72,283,518,754,989,1248');p.add_argument('--width',type=int)
    run(p.parse_args())
