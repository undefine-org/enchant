"""Measure real SDK preparation and verify every unaffected unit after edits.

Run serially, under a resource cap, on the configured build station. Each edit
starts from the same SDK selection and uses new bytes to avoid a retained Nix
result masquerading as compilation. Image registration time guards against
accidentally reused tags. This script restores Source and selection
even on failure. Client RSS is explicitly separate from compiler-child RSS.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root', type=Path, default=Path.cwd())
parser.add_argument('--out', type=Path, required=True)
parser.add_argument('--runs', type=int, default=3)
parser.add_argument('--tag', required=True, help='Unique experiment identifier; retain it with results')
args = parser.parse_args()
assert args.runs >= 1
root = args.root.resolve()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=False)
source = root/'priv/std/errors.bl'
selection = root/'.bl/sdks/current-sdk'
original = source.read_bytes()
original_selection = os.readlink(selection)
report = {'status': 'running', 'tag': args.tag, 'runs': [], 'root': str(root),
          'source_sha256': hashlib.sha256(original).hexdigest(),
          'memory_scope': 'client RSS excludes the independent coordinator and Nix workers'}


def save():
    (out/'results.json').write_text(json.dumps(report, indent=2)+'\n')


def select(sdk):
    temporary = selection.with_name('benchmark-selection.tmp')
    temporary.symlink_to(sdk)
    temporary.replace(selection)


def prepare(label):
    before = Path('/proc/meminfo').read_text()
    started_epoch = int(time.time())
    started = time.monotonic()
    with (out/(label+'.stdout')).open('w') as stdout, (out/(label+'.log')).open('w') as stderr:
        result = subprocess.run(['time', '-v', str(root/'scripts/prepare-checkout-sdk')],
                                cwd=root, stdout=stdout, stderr=stderr, timeout=2400)
    row = {'stage': label, 'seconds': time.monotonic()-started, 'exit': result.returncode,
           'started_epoch': started_epoch,
           'load_after': Path('/proc/loadavg').read_text().strip(),
           'available_before_kib': int(re.search(r'MemAvailable:\s+(\d+)', before)[1])}
    report['runs'].append(row)
    save()
    assert result.returncode == 0, label
    sdk = Path((out/(label+'.stdout')).read_text().strip())
    row['selection'] = str(sdk)
    metadata = json.loads((sdk/'artifact.json').read_text())
    row['artifacts'] = metadata
    if label.startswith('edit-'):
        info = json.loads(subprocess.check_output(
            ['nix', 'path-info', '--json', '--json-format', '1', metadata['image']], text=True))
        row['image_registered_epoch'] = info[metadata['image']]['registrationTime']
        save()
        assert row['image_registered_epoch'] >= started_epoch, (
            'edit reused an existing image; use a fresh experiment tag', label)
    drv = subprocess.check_output(['nix-store', '-q', '--deriver', metadata['image']], text=True).strip()
    log = subprocess.check_output(['nix-store', '-l', drv], text=True)
    (out/(label+'.image.log')).write_text(log)
    # A cache hit returns this image's historical build log. Never attribute
    # those historical phases to the wall time of an unchanged command.
    row['phase_scope'] = 'retained image producer log, separate from command wall time'
    row['phases'] = []
    seen = set()
    row['duplicate_phase_lines'] = 0
    for line in log.splitlines():
        if label.startswith(('prime', 'edit-')) and re.match(r'^SDK-(?:UNIT-PHASES|PHASE|SHELL-PHASE|PARTS-RESULT) ', line):
            if line in seen:
                row['duplicate_phase_lines'] += 1
                continue
            seen.add(line)
            kind, value = line.split(' ', 1)
            row['phases'].append({'kind': kind, 'value': json.loads(value)})
    rss = re.search(r'Maximum resident set size \(kbytes\): (\d+)', (out/(label+'.log')).read_text())
    row['client_max_rss_kib'] = int(rss[1]) if rss else None
    save()
    return sdk, row


def unit_store(sdk):
    metadata = json.loads((sdk/'artifact.json').read_text())
    image = Path(metadata['image'])
    index = image/'unit-store/unit-index.json'
    return index.parent, json.loads(index.read_text())


def inventory(directory):
    assert directory.is_dir(), directory
    files = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in directory.rglob('*') if p.is_file()}
    assert files, directory
    return files


try:
    baseline, _ = prepare('prime')
    base_dir, base = unit_store(baseline)
    for label in ['unchanged', 'unchanged-repeat']:
        sdk, _ = prepare(label)
        assert sdk == baseline
    for repeat in range(args.runs):
        select(baseline)
        source.write_bytes(original+f'\n; SDK latency control {args.tag} {repeat}\n'.encode())
        changed, row = prepare(f'edit-{repeat}')
        changed_dir, index = unit_store(changed)
        assert changed != baseline
        assert index['compiler'] == base['compiler'] and index['runtime'] == base['runtime']
        assert index['units'].keys() == base['units'].keys()
        unchanged = [name for name in base['units'] if base['units'][name] == index['units'][name]]
        for name in unchanged:
            assert inventory(base_dir/'.units'/name) == inventory(changed_dir/'.units'/name), name
        counts = [phase['value'] for phase in row['phases'] if phase['kind'] == 'SDK-UNIT-PHASES']
        assert len(counts) == 1 and counts[0]['compiled'] > 0, counts
        assert counts[0]['cached'] == len(unchanged)
        row['byte_identical_restored_units'] = len(unchanged)
        source.write_bytes(original)
        select(baseline)
        sdk, _ = prepare(f'restore-{repeat}')
        assert sdk == baseline
        save()
    edits = [row['seconds'] for row in report['runs'] if row['stage'].startswith('edit-')]
    report.update(status='passed', edit_seconds={'median': statistics.median(edits),
                  'min': min(edits), 'max': max(edits), 'samples': len(edits)})
except BaseException as error:
    report.update(status='failed', error=repr(error))
    raise
finally:
    source.write_bytes(original)
    select(original_selection)
    report['source_restored'] = source.read_bytes() == original
    report['selection_restored'] = os.readlink(selection) == original_selection
    save()
