#!/usr/bin/env python3
"""Execute BL-authored persistent vector instances and attachment curves.
Native paths are cached; matrices/relationships are never planned here.
"""
import argparse
import ctypes as C
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time

def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def numbers(values,count):
    return isinstance(values,list) and len(values)==count and all(type(v) in [int,float] and math.isfinite(v) and abs(v)<1e7 for v in values)
def color(value):
    if value is None:return None
    if not isinstance(value,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',value):raise ValueError('Only explicit RGB colors are admitted')
    return tuple(int(value[i:i+2],16)/255 for i in [1,3,5])
def commands_valid(commands):
    if not isinstance(commands,list) or not commands or len(commands)>20000:return False
    for command in commands:
        required={'M':2,'L':2,'C':6,'Z':0}.get(command[0]) if isinstance(command,list) and command else None
        if required is None or not numbers(command[1:],required):return False
    return True
def validate(plan):
    if plan.get('version')!=1 or plan.get('viewport')!=[1920,1080] or plan.get('fps')!=[24,1]:raise ValueError('Unsupported vector plan')
    frames=plan.get('frames');assets=plan.get('assets')
    if not isinstance(frames,list) or not 1<=len(frames)<=5000 or not isinstance(assets,dict) or not 1<=len(assets)<=128:raise ValueError('Vector resource budget exceeded')
    for asset in assets.values():
        if set(asset)-{'commands','fill','stroke','width','hatch','dash','halo','halo-width'}:raise ValueError('Unsupported vector resource property')
        if 'hatch' in asset and type(asset['hatch']) is not bool:raise ValueError('Hatch must be explicit boolean')
        if not asset.get('fill') and not asset.get('stroke'):raise ValueError('Vector resource needs paint')
        commands=asset.get('commands')
        if not commands_valid(commands):raise ValueError('Unsupported path resource')
        color(asset.get('fill'));color(asset.get('stroke'))
        color(asset.get('halo'))
        if 'halo' in asset and (type(asset.get('halo-width')) not in [int,float] or not 0<asset['halo-width']<=20):raise ValueError('Invalid label halo')
        width=asset.get('width',1)
        if type(width) not in [int,float] or not math.isfinite(width) or not 0<width<=100:raise ValueError('Invalid stroke width')
        if 'dash' in asset and (not isinstance(asset['dash'],list) or not asset['dash'] or not all(type(x) in [int,float] and math.isfinite(x) and x>0 for x in asset['dash'])):raise ValueError('Invalid dash pattern')
    ids=None;edge_ids=None
    for k,frame in enumerate(frames):
        if frame.get('frame')!=k or abs(frame.get('time',-1)-k/24)>1e-8 or not numbers(frame.get('matrix'),6):raise ValueError('Invalid frame clock or camera')
        current=[o.get('id') for o in frame.get('objects',[])]
        current_edges=[o.get('id') for o in frame.get('edges',[])]
        if any(not isinstance(v,str) or not v for v in current+current_edges):raise ValueError('Stable string identities are required')
        if not current or len(current)>256 or len(current_edges)>256 or len(set(current))!=len(current) or len(set(current_edges))!=len(current_edges):raise ValueError('Invalid persistent identities')
        if k==0:ids=current;edge_ids=current_edges
        if ids!=current or edge_ids!=current_edges:raise ValueError('Objects/edges cannot enter or exit this film')
        for obj in frame['objects']:
            if set(obj)-{'id','asset','matrix','commands'}:raise ValueError('Unsupported instance property; no implicit visibility channels')
            if 'commands' in obj and not commands_valid(obj['commands']):raise ValueError('Invalid path deformation')
            if obj.get('asset') not in assets or not numbers(obj.get('matrix'),6):raise ValueError('Invalid vector instance')
            a,b,c,d,_,_=obj['matrix']
            if a*d-b*c<=1e-10:raise ValueError('Instance cannot collapse or flip')
        for edge in frame['edges']:
            if not numbers(edge.get('curve'),8):raise ValueError('Invalid attachment curve')
            color(edge.get('stroke'))
            if type(edge.get('width')) not in [int,float] or not 0<edge['width']<=100:raise ValueError('Invalid attachment stroke')
    if abs(plan.get('duration',-1)-len(frames)/24)>1e-8:raise ValueError('Duration differs from frame range')
    return plan

def run(args):
    started=time.monotonic();folder=args.folder
    if (folder/'motion.json').stat().st_size>256*1024*1024:raise ValueError('Motion plan exceeds its byte budget')
    plan=validate(json.loads((folder/'motion.json').read_text()))
    selected={int(v) for v in args.selected.split(',')}
    if any(not 0<=k<len(plan['frames']) for k in selected):raise ValueError('Invalid selected frames')
    if sys.byteorder!='little':raise ValueError('Packed encoder requires little-endian BGRA')
    camera=module(args.camera_worker,'motion_camera');helper=module(args.text_worker,'motion_text');raster=module(args.raster_worker,'motion_raster')
    paper=folder/'paper.png'
    if not paper.exists():
        source=raster.lower_materials(folder/'paper.svg',folder,args.rsvg,os.environ.copy())
        subprocess.run([args.rsvg,'-o',str(paper),str(source)],check=True)
    painter=camera.Painter(helper,args.rsvg);lib=helper.libraries(args.rsvg)['cairo'];bind=helper.bind;ptr=C.c_void_p;dbl=C.c_double
    new=bind(lib,'cairo_new_path',None,ptr);move=bind(lib,'cairo_move_to',None,ptr,dbl,dbl)
    line=bind(lib,'cairo_line_to',None,ptr,dbl,dbl);curve=bind(lib,'cairo_curve_to',None,ptr,*([dbl]*6))
    close=bind(lib,'cairo_close_path',None,ptr);copy=bind(lib,'cairo_copy_path',ptr,ptr)
    append=bind(lib,'cairo_append_path',None,ptr,ptr);destroy=bind(lib,'cairo_path_destroy',None,ptr)
    fill=bind(lib,'cairo_fill_preserve',None,ptr);stroke=bind(lib,'cairo_stroke',None,ptr)
    stroke_preserve=bind(lib,'cairo_stroke_preserve',None,ptr)
    width=bind(lib,'cairo_set_line_width',None,ptr,dbl);cap=bind(lib,'cairo_set_line_cap',None,ptr,C.c_int)
    save=bind(lib,'cairo_save',None,ptr);restore=bind(lib,'cairo_restore',None,ptr);clip=bind(lib,'cairo_clip',None,ptr)
    extend=bind(lib,'cairo_pattern_set_extend',None,ptr,C.c_int);dash=bind(lib,'cairo_set_dash',None,ptr,C.POINTER(dbl),C.c_int,dbl)
    paths={};encoder=None;temporary=folder/'.pending-experience.mp4';output=folder/'experience.mp4';hashes={}
    try:
        painter.open(paper,[512,512],1,1920,1080);cr=painter.cr;cap(cr,1)
        def emit(commands):
            for command in commands:
                op,*v=command
                if op=='M':move(cr,*v)
                elif op=='L':line(cr,*v)
                elif op=='C':curve(cr,*v)
                else:close(cr)
        for name,asset in plan['assets'].items():
            new(cr)
            emit(asset['commands'])
            paths[name]=copy(cr)
        encoder_args=['ffmpeg','-v','error','-y','-f','rawvideo','-pixel_format','bgra','-video_size','1920x1080',
            '-framerate','24/1','-i','pipe:0','-an','-c:v','libx264','-crf','17','-preset','medium','-pix_fmt','yuv420p',
            '-threads','1','-movflags','+faststart','-f','mp4',str(temporary)]
        with (folder/'encoder.log').open('wb') as log:
            if args.film:encoder=subprocess.Popen(encoder_args,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=log)
            for k,frame in enumerate(plan['frames']):
                if not args.film and k not in selected:continue
                painter.matrix(cr,C.byref(camera.Matrix(*frame['matrix'])));painter.operator(cr,1)
                painter.source(cr,painter.atlas,0,0);extend(painter.get_source(cr),1);painter.filter(painter.get_source(cr),2);painter.paint(cr);painter.operator(cr,2)
                for edge in frame['edges']:
                    new(cr);move(cr,*edge['curve'][:2]);curve(cr,*edge['curve'][2:]);painter.rgb(cr,*color(edge['stroke']));width(cr,edge['width']);stroke(cr)
                for obj in frame['objects']:
                    asset=plan['assets'][obj['asset']];save(cr);painter.matrix(cr,C.byref(camera.Matrix(*obj['matrix'])));new(cr)
                    if 'commands' in obj:emit(obj['commands'])
                    else:append(cr,paths[obj['asset']])
                    if asset.get('halo'):
                        painter.rgb(cr,*color(asset['halo']));width(cr,asset['halo-width']);stroke_preserve(cr)
                    if asset.get('fill'):
                        painter.rgb(cr,*color(asset['fill']));fill(cr)
                    if asset.get('hatch'):
                        save(cr);clip(cr);new(cr)
                        for x in range(-120,121,7):move(cr,x,-80);line(cr,x+160,80)
                        painter.rgb(cr,*color('#607161'));width(cr,.45);stroke(cr);restore(cr)
                        new(cr)
                        if 'commands' in obj:emit(obj['commands'])
                        else:append(cr,paths[obj['asset']])
                    if asset.get('stroke'):
                        painter.rgb(cr,*color(asset['stroke']));width(cr,asset.get('width',1))
                        if asset.get('dash'):
                            values=asset['dash'];dash(cr,(dbl*len(values))(*values),len(values),0)
                        stroke(cr)
                    new(cr);restore(cr)
                if painter.status(cr):raise ValueError('Native vector frame failed')
                painter.flush(painter.surface)
                if k in selected:
                    image=folder/f'{k}.png';painter.save(image);hashes[str(k)]=digest(image)
                if encoder:encoder.stdin.write(painter.packed())
                if k%48==0:
                    (folder/'progress.json.tmp').write_text(json.dumps({'frame':k,'frames':len(plan['frames'])}));(folder/'progress.json.tmp').replace(folder/'progress.json')
            if encoder:
                encoder.stdin.close()
                if encoder.wait()!=0:raise ValueError('Encoder failed; see encoder.log')
                temporary.replace(output)
        probe=None
        if args.film:
            probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-count_frames','-select_streams','v:0',
                '-show_entries','stream=width,height,nb_read_frames,r_frame_rate,duration','-of','json',str(output)]))['streams'][0]
            if int(probe['nb_read_frames'])!=len(plan['frames']) or probe['width']!=1920 or probe['height']!=1080 or probe['r_frame_rate']!='24/1' or abs(float(probe['duration'])-plan['duration'])>=.001:raise ValueError('Encoded experience differs from its admitted clock')
        (folder/'motion-report.json').write_text(json.dumps({'seconds':time.monotonic()-started,'cairo':painter.version,'cairo_library':painter.library,
            'media':probe,'encode_args':encoder_args if args.film else None,'frame_hashes':hashes,'mp4_sha256':digest(output) if args.film else None,
            'plan_sha256':digest(folder/'motion.json'),'paper_sha256':digest(paper),'policy':'cached native vector paths; BL-authored matrices/curves; repeating world-local paper; opaque packed BGRA'},indent=2)+'\n')
    finally:
        if encoder and encoder.poll() is None:encoder.kill();encoder.wait()
        temporary.unlink(missing_ok=True)
        for path in paths.values():destroy(path)
        painter.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);p.add_argument('--rsvg',required=True)
    p.add_argument('--camera-worker',required=True,type=Path);p.add_argument('--text-worker',required=True,type=Path);p.add_argument('--raster-worker',required=True,type=Path)
    p.add_argument('--film',action='store_true');p.add_argument('--selected',default='0,168,360,552,720,864,1128');run(p.parse_args())
