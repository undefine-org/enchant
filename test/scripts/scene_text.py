#!/usr/bin/env python3
"""Real canonical-shaping checks; no BEAM or preview service required."""
import importlib.util
from pathlib import Path
import os
import json
import struct
import sys
import tempfile
import unittest
spec = importlib.util.spec_from_file_location('text_worker', 'priv/lib/scene/text_worker.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
FONT = Path('examples/scene-renderer/assets/fonts')
RSVG = os.environ.get('SCENE_RSVG', 'rsvg-convert')

class TextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = worker.measure([
            {'id': 'short', 'text': 'A little world', 'family': 'Instrument Serif', 'size': 44, 'width': 360},
            {'id': 'long', 'text': 'A little world with a much longer story to tell', 'family': 'Instrument Serif', 'size': 44, 'width': 240},
            {'id': 'italic', 'text': 'flying together', 'family': 'Instrument Serif', 'size': 44, 'italic': True, 'width': 360},
            {'id': 'spaces', 'text': 'word\nnext line', 'family': 'DM Sans', 'size': 20, 'width': 240},
            {'id':'friendly','text':'Hello, world.','family':'Nunito','size':44,'weight':650}], FONT, RSVG)
    def test_wrap_changes_measured_height(self):
        a,b = self.result['runs'][:2]
        self.assertGreater(b['lines'], a['lines'])
        self.assertGreater(b['logical'][3], a['logical'][3])
        self.assertLessEqual(b['logical'][2],240)
    def test_outline_agrees_with_same_shaped_ink(self):
        for run in self.result['runs']:
            x,y,w,h=run['ink']; a,b,c,d=run['outline-bounds']
            self.assertGreaterEqual(a,x-.05); self.assertGreaterEqual(b,y-.05)
            self.assertLessEqual(a+c,x+w+.05); self.assertLessEqual(b+d,y+h+.05)
            self.assertTrue(run['commands'])
            self.assertGreater(run['baseline'],0)
    def test_explicit_break(self):
        self.assertEqual(self.result['runs'][3]['lines'],2)
    def test_missing_font_diagnosed(self):
        with self.assertRaisesRegex(ValueError,'Unsupported packaged font'):
            worker.measure([{'text':'hello','family':'Not installed'}],FONT,RSVG)
    def test_missing_glyph_diagnosed(self):
        with self.assertRaisesRegex(ValueError,'Missing glyph'):
            worker.measure([{'text':'hello \U0010ffff'}],FONT,RSVG)
    def test_selected_raster_does_not_require_frame_zero(self):
        spec = importlib.util.spec_from_file_location('raster_worker', 'examples/scene-renderer/raster.py')
        raster = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(raster)
        with tempfile.TemporaryDirectory(prefix='scene-selected-check-') as tmp:
            folder=Path(tmp)
            (folder/'60.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100" height="100" fill="red"/></svg>')
            raster.raster(folder,1,FONT/'DMSans.ttf',RSVG,FONT,start=60,pixel_width=20)
            self.assertFalse((folder/'0.png').exists())
            self.assertEqual(list(json.loads((folder/'pixels.json').read_text())),['60'])
            self.assertEqual(struct.unpack('>II',(folder/'60.png').read_bytes()[16:24]),(20,20))
    def test_nunito_is_captured_and_shaped(self):
        import hashlib
        self.assertEqual(self.result['fonts']['Nunito.ttf'],hashlib.sha256((FONT/'Nunito.ttf').read_bytes()).hexdigest())
        self.assertTrue(self.result['runs'][4]['commands'])
    def test_nunito_cannot_fall_back_when_packaged_file_missing(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)
            for name in ['DMSans.ttf','InstrumentSerif-Regular.ttf','InstrumentSerif-Italic.ttf','PatrickHand-Regular.ttf']:
                (target/name).symlink_to((FONT/name).resolve())
            with self.assertRaises(FileNotFoundError):
                worker.measure([{'text':'Hello','family':'Nunito'}],target,RSVG)
    def test_invalid_geometry(self):
        for width in [0,-1,float('nan')]:
            with self.assertRaisesRegex(ValueError,'width'):
                worker.measure([{'text':'hello','width':width}],FONT,RSVG)

if __name__ == '__main__': unittest.main()
