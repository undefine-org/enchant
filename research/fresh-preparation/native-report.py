"""Collect the two actual Source-worker controls; reject unequal target output.

Run on Build after worker-profile.py controls finish. Logs belong to these new
images, not an unchanged invocation that merely returned a historical log.
Only the diagnostic producer subtree is excluded from target equivalence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--root', type=Path, required=True)
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
a.out.mkdir(parents=True, exist_ok=False)
report = {'status': 'running', 'scope': 'Same final native compiler; forced fresh complete SDK; optional reader cache off/on',
          'variants': {}}
inventories = {}
for mode in ('off', 'on'):
    selection = Path((a.root / f'.local/sdk-{mode}.txt').read_text().strip().splitlines()[-1])
    metadata = json.loads((selection / 'artifact.json').read_text())
    image = Path(metadata['image'])
    drv = subprocess.check_output(['nix-store', '-q', '--deriver', image], text=True).strip()
    log = subprocess.check_output(['nix-store', '-l', drv], text=True)
    (a.out / f'{mode}.image.log').write_text(log)
    seen, phases, preparations = set(), [], []
    for line in log.splitlines():
        if line in seen:
            continue
        seen.add(line)
        if line.startswith(('SDK-UNIT-PHASES ', 'SDK-PHASE ', 'SDK-SHELL-PHASE ', 'SDK-PARTS-RESULT ', 'FULL-PREPARATION ')):
            kind, value = line.split(' ', 1)
            phases.append({'kind': kind, 'value': json.loads(value)})
        elif line.startswith('FULL-PREPARE '):
            preparations.append(json.loads(line.split(' ', 1)[1]))
    total = [x['value'] for x in phases if x['kind'] == 'FULL-PREPARATION']
    units = [x['value'] for x in phases if x['kind'] == 'SDK-UNIT-PHASES']
    assert len(total) == len(units) == 1, (mode, total, units)
    index = json.loads((image / 'unit-store/unit-index.json').read_text())
    assert total[0]['units'] == len(preparations) == units[0]['compiled'] == len(index['units'])
    assert units[0]['cached'] == 0
    directory = image / 'unit-store'
    inventory = {str(f.relative_to(directory)): hashlib.sha256(f.read_bytes()).hexdigest()
                 for f in directory.rglob('*') if f.is_file()
                 and f.relative_to(directory).parts[0] != 'producer'}
    assert inventory
    inventories[mode] = inventory
    (a.out / f'{mode}.inventory.json').write_text(json.dumps(inventory, sort_keys=True, indent=2) + '\n')
    report['variants'][mode] = {'selection': str(selection), 'metadata': metadata,
                                'phases': phases, 'preparations': preparations,
                                'target_files': len(inventory)}
assert inventories['off'] == inventories['on'], 'target SDK output differs'
assert report['variants']['off']['metadata']['compiler'] == report['variants']['on']['metadata']['compiler']
report.update(status='passed', byte_identical_target_files=len(inventories['off']),
              target_inventory_sha256=hashlib.sha256(json.dumps(inventories['off'], sort_keys=True).encode()).hexdigest(),
              memory_scope='See six-unit paired pilot RSS; this comparison does not measure compiler-child peak RSS inside the Source worker VM.')
(a.out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: v for k, v in report.items() if k != 'variants'}))
