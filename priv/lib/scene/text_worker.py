#!/usr/bin/env python3
"""Canonical text boundary: Pango metrics and Cairo outlines from one layout.
No Python packages, raster text, per-pixel values, or persistent worker process.
Shared libraries are taken from the selected rsvg-convert closure where possible.
"""
import argparse
import ctypes as C
import ctypes.util
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

SCALE = 1024
FAMILIES = {'Instrument Serif', 'DM Sans', 'Patrick Hand', 'Nunito'}

class Rectangle(C.Structure):
    _fields_ = [(k, C.c_int) for k in ['x', 'y', 'width', 'height']]
class Header(C.Structure):
    _fields_ = [('type', C.c_int), ('length', C.c_int)]
class Point(C.Structure):
    _fields_ = [('x', C.c_double), ('y', C.c_double)]
class Data(C.Union):
    _fields_ = [('header', Header), ('point', Point)]
class PathData(C.Structure):
    _fields_ = [('status', C.c_int), ('data', C.POINTER(Data)), ('num_data', C.c_int)]


def libraries(rsvg):
    resolved = shutil.which(rsvg) or rsvg
    found = {}
    if shutil.which('ldd') and Path(resolved).is_file():
        result = subprocess.run(['ldd', resolved], capture_output=True, text=True)
        found = dict(re.findall(r'(lib[^\s]+) => (/[^\s]+)', result.stdout))
    specs = {'cairo': ('libcairo.so.2', 'cairo'),
             'pango': ('libpango-1.0.so.0', 'pango-1.0'),
             'pangocairo': ('libpangocairo-1.0.so.0', 'pangocairo-1.0'),
             'gobject': ('libgobject-2.0.so.0', 'gobject-2.0')}
    result = {}
    for key, (soname, generic) in specs.items():
        location = os.environ.get('SCENE_' + key.upper() + '_LIBRARY') or found.get(soname) or C.util.find_library(generic)
        if not location:
            raise ValueError(f'Missing {generic} shared library; select SCENE_RSVG or SCENE_{key.upper()}_LIBRARY')
        result[key] = C.CDLL(location)
    return result


def bind(lib, name, result, *args):
    f = getattr(lib, name)
    f.restype = result
    f.argtypes = args
    return f


class Shaper:
    def __init__(self, rsvg):
        libs = libraries(rsvg)
        c, p, pc, g = (libs[k] for k in ['cairo', 'pango', 'pangocairo', 'gobject'])
        ptr, integer, dbl, string = C.c_void_p, C.c_int, C.c_double, C.c_char_p
        self.surface_create = bind(c, 'cairo_image_surface_create', ptr, integer, integer, integer)
        self.surface_destroy = bind(c, 'cairo_surface_destroy', None, ptr)
        self.create = bind(c, 'cairo_create', ptr, ptr)
        self.destroy = bind(c, 'cairo_destroy', None, ptr)
        self.copy_path = bind(c, 'cairo_copy_path', C.POINTER(PathData), ptr)
        self.path_destroy = bind(c, 'cairo_path_destroy', None, C.POINTER(PathData))
        self.extents = bind(c, 'cairo_path_extents', None, ptr, *([C.POINTER(dbl)] * 4))
        self.move = bind(c, 'cairo_move_to', None, ptr, dbl, dbl)
        self.options = bind(c, 'cairo_font_options_create', ptr)
        self.options_destroy = bind(c, 'cairo_font_options_destroy', None, ptr)
        self.hint_metrics = bind(c, 'cairo_font_options_set_hint_metrics', None, ptr, integer)
        self.hint_style = bind(c, 'cairo_font_options_set_hint_style', None, ptr, integer)
        self.layout_create = bind(pc, 'pango_cairo_create_layout', ptr, ptr)
        self.layout_path = bind(pc, 'pango_cairo_layout_path', None, ptr, ptr)
        self.context_options = bind(pc, 'pango_cairo_context_set_font_options', None, ptr, ptr)
        self.context_resolution = bind(pc, 'pango_cairo_context_set_resolution', None, ptr, dbl)
        self.context = bind(p, 'pango_layout_get_context', ptr, ptr)
        self.changed = bind(p, 'pango_layout_context_changed', None, ptr)
        self.desc_create = bind(p, 'pango_font_description_new', ptr)
        self.desc_free = bind(p, 'pango_font_description_free', None, ptr)
        self.family = bind(p, 'pango_font_description_set_family', None, ptr, string)
        self.size = bind(p, 'pango_font_description_set_absolute_size', None, ptr, dbl)
        self.weight = bind(p, 'pango_font_description_set_weight', None, ptr, integer)
        self.style = bind(p, 'pango_font_description_set_style', None, ptr, integer)
        self.font = bind(p, 'pango_layout_set_font_description', None, ptr, ptr)
        self.text = bind(p, 'pango_layout_set_text', None, ptr, string, integer)
        self.width = bind(p, 'pango_layout_set_width', None, ptr, integer)
        self.wrap = bind(p, 'pango_layout_set_wrap', None, ptr, integer)
        self.spacing = bind(p, 'pango_layout_set_line_spacing', None, ptr, C.c_float)
        self.metrics = bind(p, 'pango_layout_get_extents', None, ptr, C.POINTER(Rectangle), C.POINTER(Rectangle))
        self.baseline = bind(p, 'pango_layout_get_baseline', integer, ptr)
        self.line_count = bind(p, 'pango_layout_get_line_count', integer, ptr)
        self.missing = bind(p, 'pango_layout_get_unknown_glyphs_count', integer, ptr)
        self.unref = bind(g, 'g_object_unref', None, ptr)
        self.versions = {key: bind(libs[key], name, string)().decode()
                         for key, name in [('cairo', 'cairo_version_string'), ('pango', 'pango_version_string')]}
        self.versions['libraries'] = {key: lib._name for key, lib in libs.items()}

    def shape(self, request):
        text = request['text']
        family = request.get('family', 'DM Sans')
        size = request.get('size', 20)
        width = request.get('width')
        spacing = request.get('line-height', 1.3)
        if not isinstance(text, str) or '\0' in text or len(text) > 10000:
            raise ValueError('Text must be a string of at most 10000 characters without NUL')
        if family not in FAMILIES:
            raise ValueError(f'Unsupported packaged font: {family}')
        for name, value, lower, upper in [('size', size, 1, 512), ('line-height', spacing, 1, 3)]:
            if not isinstance(value, (int, float)) or not math.isfinite(value) or not lower <= value <= upper:
                raise ValueError(f'Invalid {name}')
        if width is not None and (not isinstance(width, (int, float)) or not math.isfinite(width) or not 1 <= width <= 10000):
            raise ValueError('Invalid paragraph width')
        surface = self.surface_create(0, 1, 1)
        cr = self.create(surface)
        layout = self.layout_create(cr)
        desc = self.desc_create()
        options = self.options()
        path = None
        try:
            self.hint_metrics(options, 1)  # OFF: geometry must not depend on raster scale.
            self.hint_style(options, 1)    # NONE
            self.context_options(self.context(layout), options)
            self.context_resolution(self.context(layout), 96)
            self.changed(layout)
            self.family(desc, family.encode())
            self.size(desc, size * SCALE)
            self.weight(desc, request.get('weight', 400))
            self.style(desc, 2 if request.get('italic', False) else 0)
            self.font(layout, desc)
            data = text.encode('utf-8')
            self.text(layout, data, len(data))
            self.width(layout, round(width * SCALE) if width is not None else -1)
            self.wrap(layout, 2)  # word-char: keep long words within the admitted width.
            self.spacing(layout, spacing)
            if self.missing(layout):
                raise ValueError('Missing glyph in packaged font set')
            ink, logical = Rectangle(), Rectangle()
            self.metrics(layout, C.byref(ink), C.byref(logical))
            self.move(cr, 0, 0)
            self.layout_path(cr, layout)
            path = self.copy_path(cr)
            if path.contents.status:
                raise ValueError(f'Cairo outline failure: {path.contents.status}')
            commands = []
            i = 0
            while i < path.contents.num_data:
                item = path.contents.data[i]
                kind, length = item.header.type, item.header.length
                op = ['M', 'L', 'C', 'Z'][kind]
                points = [round(v, 5) for j in range(1, length)
                          for v in [path.contents.data[i+j].point.x, path.contents.data[i+j].point.y]]
                commands.append([op, *points])
                i += length
            bounds = [C.c_double() for _ in range(4)]
            self.extents(cr, *[C.byref(v) for v in bounds])
            x1, y1, x2, y2 = [v.value for v in bounds]
            rectangle = lambda r: [getattr(r, k) / SCALE for k in ['x', 'y', 'width', 'height']]
            return {'id': request.get('id'), 'logical': rectangle(logical), 'ink': rectangle(ink),
                    'baseline': self.baseline(layout) / SCALE, 'lines': self.line_count(layout),
                    'commands': commands, 'outline-bounds': [x1, y1, x2-x1, y2-y1]}
        finally:
            if path: self.path_destroy(path)
            self.options_destroy(options)
            self.desc_free(desc)
            self.unref(layout)
            self.destroy(cr)
            self.surface_destroy(surface)


def measure(requests, font_dir, rsvg):
    font_dir = Path(font_dir).resolve()
    required = ['DMSans.ttf', 'InstrumentSerif-Regular.ttf', 'InstrumentSerif-Italic.ttf', 'PatrickHand-Regular.ttf']
    if any(request.get('family') == 'Nunito' for request in requests):
        required.append('Nunito.ttf')
    hashes = {name: hashlib.sha256((font_dir / name).read_bytes()).hexdigest() for name in required}
    with tempfile.TemporaryDirectory(prefix='scene-shaping-') as scratch:
        config = Path(scratch) / 'fonts.conf'
        from xml.sax.saxutils import escape
        config.write_text('<fontconfig><dir>' + escape(str(font_dir)) + '</dir><cachedir>' + scratch + '/cache</cachedir></fontconfig>')
        previous = os.environ.get('FONTCONFIG_FILE')
        os.environ['FONTCONFIG_FILE'] = str(config)
        try:
            shaper = Shaper(rsvg)
            return {'version': 1, 'backend': shaper.versions, 'fonts': hashes,
                    'runs': [shaper.shape(request) for request in requests]}
        finally:
            if previous is None: os.environ.pop('FONTCONFIG_FILE', None)
            else: os.environ['FONTCONFIG_FILE'] = previous


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--font-dir', type=Path, required=True)
    p.add_argument('--requests-json', required=True)
    p.add_argument('--rsvg', default=os.environ.get('SCENE_RSVG', 'rsvg-convert'))
    a = p.parse_args()
    try:
        result = measure(json.loads(a.requests_json), a.font_dir, a.rsvg)
    except (ValueError, KeyError, OSError) as error:
        print(json.dumps({'error': str(error)}))
        raise SystemExit(1)
    print(json.dumps(result, separators=(',', ':')))

if __name__ == '__main__':
    main()
