#!/usr/bin/env python3
"""Real canonical-shaping checks; no BEAM or preview service required."""
import importlib.util
from pathlib import Path
import os
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
            {'id': 'spaces', 'text': 'word\nnext line', 'family': 'DM Sans', 'size': 20, 'width': 240}], FONT, RSVG)
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
    def test_invalid_geometry(self):
        for width in [0,-1,float('nan')]:
            with self.assertRaisesRegex(ValueError,'width'):
                worker.measure([{'text':'hello','width':width}],FONT,RSVG)

if __name__ == '__main__': unittest.main()
