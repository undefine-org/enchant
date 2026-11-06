"""Profile the same real edit as a completed uninstrumented benchmark.

The actual baseline is selected before changing the driver. Every target
library file must match the corresponding plain edit; the retained producer
floor is a separate component whose dependency closure changes with the driver.
"""
import argparse
import base64
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root', type=Path, required=True)
parser.add_argument('--benchmark', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
parser.add_argument('--replay', type=Path, help='Recheck an existing immutable diagnostic product without rebuilding')
args = parser.parse_args()
root, out = args.root.resolve(), args.out.resolve()
out.mkdir(parents=True, exist_ok=False)
benchmark = json.loads(args.benchmark.read_text())
assert benchmark['status'] == 'passed'
plain = next(row for row in benchmark['runs'] if row['stage'] == 'edit-0')
source, driver = root/'priv/std/errors.bl', root/'scripts/produce-sdk.bl'
original_source, original_driver = source.read_bytes(), driver.read_bytes()
assert hashlib.sha256(original_source).hexdigest() == benchmark['source_sha256']
report = {'status': 'running', 'plain_selection': plain['selection'],
          'memory_scope': 'instrumented actual library child; includes sampler overhead'}


def save():
    (out/'results.json').write_text(json.dumps(report, indent=2)+'\n')


def prepare(label):
    with (out/(label+'.log')).open('w') as log:
        result = subprocess.run([str(root/'scripts/prepare-checkout-sdk')], cwd=root,
                                text=True, stdout=subprocess.PIPE, stderr=log, timeout=2400)
    assert result.returncode == 0, label
    return Path(result.stdout.strip())


def image(sdk):
    return Path(json.loads((sdk/'artifact.json').read_text())['image'])


def inventory(directory):
    files = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in directory.rglob('*') if p.is_file()
             and p.relative_to(directory).parts[0] != 'producer'}
    assert files
    return files


replay = json.loads((args.replay/'results.json').read_text()) if args.replay else None
baseline = Path(replay['baseline']) if replay else prepare('prime')
assert str(baseline) == benchmark['runs'][0]['selection']
report['baseline'] = str(baseline)
try:
    if replay:
        sampled = Path(replay['sample_selection'])
    else:
        generated = out/'produce-profile.bl'
        subprocess.run([sys.executable, str(Path(__file__).with_name('profile.py')),
                        '--root', str(root), '--out', str(generated)], check=True)
        shutil.copyfile(generated, driver)
        source.write_bytes(original_source+f'\n; SDK latency control {benchmark["tag"]} 0\n'.encode())
        sampled = prepare('sample')
    report['sample_selection'] = str(sampled)
    sampled_image = image(sampled)
    drv = subprocess.check_output(['nix-store', '-q', '--deriver', str(sampled_image)], text=True).strip()
    log = subprocess.check_output(['nix-store', '-l', drv], text=True)
    (out/'image.log').write_text(log)
    rows = list(dict.fromkeys(log.splitlines()))  # worker debug replay
    valid, interrupted = [], []
    for line in rows:
        if line.startswith(('CHILD-', 'SDK-UNIT-PHASES ')):
            try:
                json.loads(line.split(' ', 1)[1])
            except json.JSONDecodeError:
                marker = re.search(r'\[\s*\d+\.\d+\] reboot: Power down', line)
                assert marker, line
                interrupted.append(line[:marker.start()])
                continue
        valid.append(line)
    # A shutdown fragment can match several frames with identical encoded
    # prefixes. Retain the intact rows and report the ambiguity explicitly;
    # these diagnostic stacks are not compiler or artifact validation evidence.
    for prefix in interrupted:
        assert any(line.startswith(prefix) for line in valid), prefix
    rows = valid
    report['interrupted_console_fragments'] = len(interrupted)
    report['stack_capture_complete'] = not interrupted
    summaries = [json.loads(line.split(' ', 1)[1]) for line in rows if line.startswith('CHILD-SAMPLES ')]
    phases = [json.loads(line.split(' ', 1)[1]) for line in rows if line.startswith('SDK-UNIT-PHASES ')]
    assert len(summaries) == len(phases) == 1
    expected = next(row['value'] for row in plain['phases'] if row['kind'] == 'SDK-UNIT-PHASES')
    for key in ('compiled', 'cached', 'jobs', 'input-reads'):
        assert phases[0][key] == expected[key], (key, phases[0], expected)
    stacks = {row['id']: row for row in (json.loads(line.split(' ', 1)[1])
              for line in rows if line.startswith('CHILD-STACK '))}
    frames = {}
    for line in rows:
        if line.startswith('CHILD-FRAME '):
            frame = json.loads(line.split(' ', 1)[1])
            frames.setdefault((frame['id'], frame['index']), {})[frame['part']] = frame
    for (stack, index), parts in frames.items():
        assert set(parts) == set(range(parts[0]['last']+1))
        encoded = ''.join(parts[i]['data'] for i in sorted(parts))
        stacks[stack].setdefault('frames', {})[index] = json.loads(base64.b64decode(encoded, validate=True))
    samples = []
    for stack in stacks.values():
        assert set(stack['frames']) == set(range(len(stack['frames'])))
        stack['frames'] = [frame for _, frame in sorted(stack['frames'].items())]
        samples.append(stack)
    calls = [json.loads(line.split(' ', 1)[1]) for line in rows if line.startswith('CHILD-CALL ')]
    assert len(samples) == summaries[0]['distinct']
    assert sum(row['samples'] for row in samples) == summaries[0]['observations']
    actual, expected = inventory(sampled_image/'unit-store'), inventory(image(Path(plain['selection']))/'unit-store')
    assert actual == expected
    assert not list(sampled_image.glob('**/*ProfileSelfbuild*'))
    report.update(status='passed', summary=summaries[0], phases=phases[0], samples=samples, calls=calls,
                  target_files=len(actual), target_inventory_sha256=hashlib.sha256(
                      json.dumps(actual, sort_keys=True).encode()).hexdigest())
except BaseException as error:
    report.update(status='failed', error=repr(error))
    raise
finally:
    if not replay:
        driver.write_bytes(original_driver)
        source.write_bytes(original_source)
        selection = root/'.bl/sdks/current-sdk'
        temporary = selection.with_name('sample-selection.tmp')
        temporary.symlink_to(baseline)
        temporary.replace(selection)
    report['source_restored'] = source.read_bytes() == original_source and driver.read_bytes() == original_driver
    try:
        if not replay:
            assert prepare('restore') == baseline
    finally:
        save()
