#!/usr/bin/env python3
"""Admission checks exercise the actual renderer gate before GPU allocation."""
import copy,importlib.util,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('showcase',Path(__file__).resolve().parents[2]/'examples/scene-renderer/showcase_worker.py');worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
def fixture():
 ids=['make','rules','move','worlds','brand','tagline','signature','edition']
 specs=[{'id':i,'ink-bounds':[0,0,100,100],'path':'M 0 0 L 100 0 L 100 100 Z'} for i in ids]
 frame={'eye':[0,0,10],'view-projection':[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1],'shape':[1,0,0,0],'gesture':[0,0,1,.2],'placement':[0,0,0,0],'material':[0,0,1,0],'accent':[1,0,0],'atmosphere':[0,0,0,0],'finish':[.3,0,0,0],'types':[{'id':i,'rect':[0,0,2,1],'gesture':[0,0,0,0],'ink':[1,1,1],'plane':'back'} for i in ids]}
 return {'version':1,'viewport':[1920,1080],'fps':[60,1],'duration':30,'frames':[dict(frame,frame=k,time=k/60) for k in range(1800)],'typography':specs,'audio':[{'at':0,'voice':'kick','duration':.3,'frequency':54,'gain':.7}]}
class Admission(unittest.TestCase):
 def setUp(self):self.plan=fixture()
 def rejects(self):
  with self.assertRaises(ValueError):worker.validate(self.plan)
 def test_exact_clock(self):
  worker.validate(self.plan);self.plan['frames'][300]['time']=5.1;self.rejects()
 def test_shader_channel(self):
  self.plan['frames'][5]['opacity']=.5;self.rejects()
 def test_identity(self):
  self.plan['frames'][7]['types']=self.plan['frames'][7]['types'][:-1];self.rejects()
 def test_finite_matrix(self):
  self.plan['frames'][8]['view-projection']=[float('nan')]*16;self.rejects()
 def test_texture_path(self):
  self.plan['typography'][0]['id']='../../escape';self.rejects()
 def test_svg_injection(self):
  self.plan['typography'][0]['path']='M 0 0"/><image href="http://example.com"/>';self.rejects()
 def test_unbounded_texture(self):
  self.plan['typography'][0]['ink-bounds']=[0,0,4000,10000];self.rejects()
 def test_audio_voice(self):
  self.plan['audio'][0]['voice']='external';self.rejects()
 def test_geometry(self):
  self.plan['frames'][9]['gesture']=[0,0,0,0];self.rejects()
if __name__=='__main__':unittest.main()
