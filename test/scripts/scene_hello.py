#!/usr/bin/env python3
import importlib.util,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('hello',Path(__file__).resolve().parents[2]/'examples/scene-renderer/hello_worker.py');worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
def plan():
 item={'id':'paper','kind':'rect','box':[0,0,1920,1080],'radius':0,'fill':'#f4f0e4','matrix':[1,0,0,1,0,0],'clip':[0,0,1920,1080]}
 frame={'items':[item],'semantic-ids':[f'world/{i}' for i in range(24)]}
 return {'version':1,'viewport':[1920,1080],'fps':[60,1],'duration':60,'assets':{'title':{'commands':[['M',0,0],['L',1,0],['L',1,1],['Z']]}},'audio':[{'at':0,'voice':'chord','duration':2,'frequency':220,'gain':.2}], 'frames':[dict(frame,frame=k,time=k/60) for k in range(3600)]}
class Admission(unittest.TestCase):
 def setUp(self):self.p=plan()
 def reject(self):
  with self.assertRaises(ValueError):worker.validate(self.p)
 def test_clock(self):
  worker.validate(self.p);self.p['frames'][100]['time']=9;self.reject()
 def test_nan(self):
  self.p['frames'][0]['items']=[dict(self.p['frames'][0]['items'][0],matrix=[float('nan')]*6)];self.reject()
 def test_degenerate_transform(self):
  self.p['frames'][0]['items']=[dict(self.p['frames'][0]['items'][0],matrix=[0]*6)];self.reject()
 def test_visibility_channel(self):
  self.p['frames'][0]['items']=[dict(self.p['frames'][0]['items'][0],opacity=.5)];self.reject()
 def test_clip(self):
  self.p['frames'][0]['items']=[dict(self.p['frames'][0]['items'][0],clip=[0,0,-1,5])];self.reject()
 def test_missing_glyph_resource(self):
  self.p['frames'][0]['items']=[{'id':'text','kind':'asset','asset':'missing','fill':'#233d36','matrix':[1,0,0,1,0,0],'clip':[0,0,1920,1080]}];self.reject()
 def test_identity(self):
  self.p['frames'][5]['semantic-ids']=['world/0'];self.reject()
 def test_shader_weights(self):
  self.p['frames'][0]['items']=[{'id':'seed','kind':'seed','center':[0,0],'radius':80,'angle':0,'phase':0,'seed':0,'material':[1,1,0],'matrix':[1,0,0,1,0,0],'clip':[0,0,1920,1080]}];self.reject()
 def test_audio_before_gpu(self):
  self.p['audio'][0]['duration']=float('inf');self.reject()
 def test_sparse_review_preserves_all_display_checks(self):
  self.p.update(version=2,selection=[0,990,3599],frames=[self.p['frames'][k] for k in [0,990,3599]])
  worker.validate(self.p)
  self.p['frames'][1]['items']=[dict(self.p['frames'][1]['items'][0],matrix=[float('nan')]*6)];self.reject()
if __name__=='__main__':unittest.main()
