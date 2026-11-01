#!/usr/bin/env python3
"""Check cached material pixel identity with real raster output.
Usage: python3 test/scripts/scene_materials.py FRAME.svg FONT_DIR RSVG
"""
import importlib.util
from pathlib import Path
import shutil
import sys
import tempfile
spec = importlib.util.spec_from_file_location('scene_raster', 'examples/scene-renderer/raster.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
source, font_dir, rsvg = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
with tempfile.TemporaryDirectory(prefix='scene-material-check-') as tmp:
    folder = Path(tmp)
    shutil.copyfile(source, folder / '0.svg')
    worker.raster(folder, 1, font_dir / 'InstrumentSerif-Regular.ttf', rsvg, font_dir, 2)
    before = (folder / '0.png').read_bytes()
    tiles = {p.name: p.stat().st_mtime_ns for p in folder.glob('material-*.png')}
    assert len(tiles) == 1
    worker.raster(folder, 1, font_dir / 'InstrumentSerif-Regular.ttf', rsvg, font_dir, 2)
    assert before == (folder / '0.png').read_bytes(), 'same material/time must give identical pixels'
    assert tiles == {p.name: p.stat().st_mtime_ns for p in folder.glob('material-*.png')}, 'immutable tile reused'
print('Materials: identical repeated pixels; seeded texture tile reused')
