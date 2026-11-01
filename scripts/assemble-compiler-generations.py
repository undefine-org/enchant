#!/usr/bin/env python3
"""Assemble already retained P/B/C products; qualification never recompiles."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def inventory(directory):
    result = {}
    for path in sorted(directory.iterdir()):
        if not path.is_file() or path.is_symlink():
            raise ValueError(f'Nonregular compiler artifact: {path}')
        result[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def assemble(products, output):
    output.mkdir()
    qualification = output / 'qualification'
    qualification.mkdir()
    generations = []
    original_inputs = None
    for label, product in zip('PBC', products):
        report = json.loads((product / 'result.json').read_text())
        stage = report.get('generation')
        if (report.get('kind') != 'artifact-generation-stage'
                or not isinstance(stage, dict) or stage.get('generation') != label
                or stage.get('produced') is not True or stage.get('fresh_boot_qualified') is not True
                or 'error' in report or inventory(product / label) != stage.get('files')):
            raise ValueError(f'Incomplete compiler generation {label}')
        inputs = json.loads((product / 'inputs.json').read_text())
        sources = {k: v for k, v in inputs.items() if not k.startswith('priv/bootstrap/seed/')}
        if original_inputs is None:
            original_inputs = sources
            initial = report
            shutil.copyfile(product / 'inputs.json', qualification / 'inputs.json')
        elif original_inputs != sources:
            raise ValueError('Compiler source inputs changed between retained generations')
        for suffix in ('bootstrap.json', 'producer.log', 'boot.log'):
            shutil.copyfile(product / f'{label}.{suffix}', qualification / f'{label}.{suffix}')
        generations.append(stage)
    if generations[1]['files'] != generations[2]['files']:
        raise ValueError('B and C byte inventories differ')
    report = {'version': 1, 'kind': 'artifact-generation-qualification',
              'initial_seed': initial['initial_seed'], 'initial_seed_files': initial['initial_seed_files'],
              'floor_installed': False, 'native_execution_admission': False,
              'preparation': generations[0], 'stages': generations[1:],
              'generation_products': dict(zip('PBC', map(str, products))),
              'self_reproduction_qualified': True, 'changed_files': []}
    (qualification / 'result.json').write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    shutil.copytree(products[2] / 'C', output / 'seed')
    (output / 'unit-store').symlink_to(products[2] / 'unit-store', target_is_directory=True)
    (output / 'generations').mkdir()
    for label, product in zip('PBC', products):
        (output / 'generations' / label).symlink_to(product, target_is_directory=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--products', nargs=3, type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    assemble(args.products, args.out)
