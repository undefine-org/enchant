#!/usr/bin/env python3
"""Camera graphics boundary: real tiny atlas, packed pixels, and encoder checks."""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
worker=load(ROOT/'examples/scene-renderer/camera_worker.py','test_scene_camera')
RSVG=os.environ.get('SCENE_RSVG','rsvg-convert')

def plan():
    return {'version':1,'viewport':[64,48],'world':[64,48],'density':2,'fps':[24,1],'duration':2/24,
            'frames':[{'frame':k,'time':k/24,'matrix':[1,0,0,1,-32*k,0]} for k in range(2)]}

class CameraTests(unittest.TestCase):
    def test_invalid_matrix_fails(self):
        value=plan();value['frames'][0]['matrix']=[0,0,0,0,0,0]
        with self.assertRaises(ValueError):worker.validate(value)
    def test_bad_clock_fails(self):
        value=plan();value['frames'][1]['time']=1
        with self.assertRaises(ValueError):worker.validate(value)
    def test_atlas_budget_fails(self):
        value=plan();value['world']=[20000,20000]
        with self.assertRaises(ValueError):worker.validate(value)
    def test_wrong_duration_fails(self):
        value=plan();value['duration']=3
        with self.assertRaises(ValueError):worker.validate(value)
    def test_invalid_frame_order_fails(self):
        value=plan();value['frames'].reverse()
        with self.assertRaises(ValueError):worker.validate(value)
    def test_real_packed_sampler_and_movie(self):
        with tempfile.TemporaryDirectory(prefix='bl-camera-check-') as name:
            folder=Path(name);(folder/'camera.json').write_text(json.dumps(plan()))
            (folder/'world.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="48"><rect width="32" height="48" fill="#ff0000"/><rect x="32" width="32" height="48" fill="#00ff00"/></svg>')
            args=argparse.Namespace(folder=folder,rsvg=RSVG,text_worker=ROOT/'priv/lib/scene/text_worker.py',
                raster_worker=ROOT/'examples/scene-renderer/raster.py',selected='0,1',width=None,film=True)
            worker.run(args)
            report=json.loads((folder/'camera-report.json').read_text())
            self.assertEqual(int(report['media']['nb_read_frames']),2)
            self.assertEqual(report['output'],[64,48])
            helper=load(args.text_worker,'test_scene_camera_text');painter=worker.Painter(helper,RSVG)
            try:
                painter.open(folder/'atlas.png',[64,48],2,64,48)
                painter.frame([1,0,0,1,0,0],2,1);original=painter.packed()
                pixel=lambda data,x,y:tuple(data[(y*64+x)*4:(y*64+x)*4+4])
                self.assertEqual(pixel(original,8,8),(0,0,255,255))
                self.assertEqual(pixel(original,56,8),(0,255,0,255))
                painter.frame([1,0,0,1,-32,0],2,1)
                self.assertEqual(pixel(painter.packed(),8,8),(0,255,0,255))
                painter.frame([1,0,0,1,0,0],2,1)
                self.assertEqual(painter.packed(),original)
                painter.save(folder/'again.png')
                self.assertEqual((folder/'again.png').read_bytes(),(folder/'0.png').read_bytes())
            finally:painter.close()

if __name__=='__main__':unittest.main()
