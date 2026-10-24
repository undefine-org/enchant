#!/usr/bin/env python3
"""Graphics boundary only: SVG → packed PNG → optional silent H.264.
Scene evaluation, frame clock and publication belong to BL. One worker, one
rasterizer/encoder at a time; no pixel-sized Python or BEAM collections.
"""
import argparse
import base64
import xml.etree.ElementTree as ET
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import xml.sax.saxutils


def run(argv, **kw):
    return subprocess.run(list(map(str, argv)), check=True, **kw)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


SVG = 'http://www.w3.org/2000/svg'
ET.register_namespace('', SVG)


def lower_materials(source, folder, rsvg, env):
    """Resolve seeded static material filters once into packed texture tiles.
    Geometry and text remain vectors. The material cache is a backend lowering,
    not an alternate authoring model; no frame-dependent noise is introduced.
    """
    tree = ET.parse(source)
    root = tree.getroot()
    defs = root.find(f'{{{SVG}}}defs')
    if defs is None:
        return source
    changed = False
    for resource in list(defs):
        if resource.get('data-scene-material') != 'paper':
            continue
        key = hashlib.sha256(ET.tostring(resource) + b'paper-tile-512-v1').hexdigest()
        tile = folder / f'material-{key}.png'
        if not tile.exists():
            texture = ET.Element(f'{{{SVG}}}svg', {'width': '512', 'height': '512'})
            texture_defs = ET.SubElement(texture, f'{{{SVG}}}defs')
            texture_defs.append(ET.fromstring(ET.tostring(resource)))
            ET.SubElement(texture, f'{{{SVG}}}rect', {'width': '512', 'height': '512',
                          'fill': 'white', 'filter': f"url(#{resource.get('id')})"})
            run([rsvg, '-o', tile], input=ET.tostring(texture), env=env)
        pattern = ET.Element(f'{{{SVG}}}pattern', {'id': resource.get('id'),
                              'patternUnits': 'userSpaceOnUse', 'width': '512', 'height': '512'})
        ET.SubElement(pattern, f'{{{SVG}}}image', {'width': '512', 'height': '512',
                      'href': 'data:image/png;base64,' + base64.b64encode(tile.read_bytes()).decode()})
        defs.remove(resource)
        defs.append(pattern)
        for node in root.iter():
            if node.get('filter') == f"url(#{resource.get('id')})":
                del node.attrib['filter']
                node.set('fill', f"url(#{resource.get('id')})")
        changed = True
    if not changed:
        return source
    lowered = folder / f'{source.stem}.resolved.svg'
    tree.write(lowered, encoding='utf-8', xml_declaration=True)
    return lowered


def raster(folder, count, font, rsvg, font_dir=None, scale=1):
    # Use only the captured font. Browser preview displays these same PNGs.
    with tempfile.TemporaryDirectory(prefix='bl-scene-font-') as tmp:
        config = Path(tmp) / 'fonts.conf'
        config.write_text('<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd">'
                          '<fontconfig><dir>' + xml.sax.saxutils.escape(str((font_dir or font.parent).resolve()))
                          + '</dir><cachedir>' + tmp + '/cache</cachedir></fontconfig>')
        env = {**os.environ, 'FONTCONFIG_FILE': str(config)}
        for k in range(count):
            source = lower_materials(folder / f'{k}.svg', folder, rsvg, env)
            if scale == 1:
                run([rsvg, '-o', folder / f'{k}.png', source], env=env)
            else:
                run([rsvg, '--zoom', str(scale), '-o', folder / 'supersampled.png', source], env=env)
                run(['ffmpeg', '-v', 'error', '-y', '-i', folder / 'supersampled.png',
                     '-vf', f'scale=iw/{scale}:ih/{scale}:flags=lanczos',
                     '-frames:v', '1', folder / f'{k}.png'])
        if (folder / 'supersampled.png').exists():
            (folder / 'supersampled.png').unlink()
    (folder / 'pixels.json').write_text(json.dumps({str(k): digest(folder / f'{k}.png')
                                                  for k in range(count)}, indent=2) + '\n')


def encode(root, output, ffmpeg, ffprobe):
    # Capture publication once; source edits and later publications cannot change it.
    m = json.loads((root / 'manifest.json').read_text())
    folder = root / m['revision']
    n, d = m['fps']
    output = output.resolve()
    args = [ffmpeg, '-v', 'error', '-y', '-framerate', f'{n}/{d}', '-start_number', 0,
            '-i', str(folder / '%d.png'), '-frames:v', str(m['frames']), '-an',
            '-c:v', 'libx264', '-crf', '16', '-pix_fmt', 'yuv420p', '-threads', '1', str(output)]
    run(args)
    probe = json.loads(run([ffprobe, '-v', 'error', '-count_frames', '-select_streams', 'v:0',
                           '-show_entries', 'stream=nb_read_frames,width,height,duration,r_frame_rate',
                           '-of', 'json', output], capture_output=True, text=True).stdout)['streams'][0]
    assert int(probe['nb_read_frames']) == m['frames'], probe
    assert (probe['width'], probe['height']) == (m['width'], m['height']), probe
    assert abs(float(probe['duration']) - m['frames'] * d / n) < 0.001, probe
    report = {**m, 'encode_args': args, 'media': probe, 'output_sha256': digest(output),
              'frame_hashes': json.loads((folder / 'pixels.json').read_text()),
              'sources': json.loads((folder / 'provenance.json').read_text())}
    output.with_suffix('.manifest.json').write_text(json.dumps(report, indent=2) + '\n')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=['raster', 'export'])
    p.add_argument('folder', type=Path)
    p.add_argument('--count', type=int)
    p.add_argument('--font', type=Path)
    p.add_argument('--font-dir', type=Path)
    p.add_argument('--scale', type=int, choices=[1, 2, 3], default=1)
    p.add_argument('--rsvg', default=os.environ.get('SCENE_RSVG', 'rsvg-convert'))
    p.add_argument('--out', type=Path, default=Path('/tmp/scene-study.mp4'))
    p.add_argument('--ffmpeg', default='ffmpeg')
    p.add_argument('--ffprobe', default='ffprobe')
    a = p.parse_args()
    if a.mode == 'raster':
        raster(a.folder, a.count, a.font, a.rsvg, a.font_dir, a.scale)
    else:
        encode(a.folder, a.out, a.ffmpeg, a.ffprobe)

if __name__ == '__main__':
    main()
