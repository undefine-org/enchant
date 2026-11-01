#!/usr/bin/env python3
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('scene_motion',ROOT/'examples/scene-renderer/motion_worker.py')
worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
def plan():
    return {'version':1,'viewport':[1920,1080],'fps':[24,1],'duration':2/24,
      'assets':{'seed':{'commands':[['M',-20,-20],['L',20,-20],['L',20,20],['L',-20,20],['Z']],'fill':'#cc5544','stroke':'#223344','width':1,'hatch':True,'halo':'#eee7d3','halo-width':2}},
      'frames':[{'frame':k,'time':k/24,'matrix':[1,0,0,1,0,0],'edges':[],
                 'objects':[{'id':'seed','asset':'seed','matrix':[1,0,0,1,960+k*90,540]}]} for k in range(2)]}
class MotionTests(unittest.TestCase):
    def test_arrivals_are_rejected(self):
        value=plan();value['frames'][1]['objects'].append({'id':'new','asset':'seed','matrix':[1,0,0,1,0,0]})
        with self.assertRaises(ValueError):worker.validate(value)
    def test_implicit_opacity_is_rejected(self):
        value=plan();value['frames'][0]['objects'][0]['opacity']=0
        with self.assertRaises(ValueError):worker.validate(value)
    def test_missing_resource_is_rejected(self):
        value=plan();value['frames'][0]['objects'][0]['asset']='missing'
        with self.assertRaises(ValueError):worker.validate(value)
    def test_collapsed_geometry_is_rejected(self):
        value=plan();value['frames'][0]['objects'][0]['matrix']=[0,0,0,0,0,0]
        with self.assertRaises(ValueError):worker.validate(value)
    def test_unsupported_path_is_rejected(self):
        value=plan();value['assets']['seed']['commands']=[['UNKNOWN',1,2]]
        with self.assertRaises(ValueError):worker.validate(value)
    def test_real_vectors_and_encoder(self):
        with tempfile.TemporaryDirectory(prefix='bl-motion-test-') as name:
            value=plan();value['frames'][1]['objects'][0]['commands']=[['M',-20,0],['L',0,-25],['L',20,0],['L',0,25],['Z']]
            folder=Path(name);(folder/'motion.json').write_text(json.dumps(value))
            (folder/'paper.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512"><rect width="512" height="512" fill="#eee7d3"/></svg>')
            args=argparse.Namespace(folder=folder,rsvg=os.environ.get('SCENE_RSVG','rsvg-convert'),selected='0,1',film=True,
                camera_worker=ROOT/'examples/scene-renderer/camera_worker.py',text_worker=ROOT/'priv/lib/scene/text_worker.py',raster_worker=ROOT/'examples/scene-renderer/raster.py')
            worker.run(args);report=json.loads((folder/'motion-report.json').read_text())
            self.assertEqual(report['media']['nb_read_frames'],'2')
            self.assertNotEqual(report['frame_hashes']['0'],report['frame_hashes']['1'])
            expected=(folder/'1.png').read_bytes();args.film=False;args.selected='1';worker.run(args)
            self.assertEqual(expected,(folder/'1.png').read_bytes())
if __name__=='__main__':unittest.main()
