"""Alternate actual SDK edit controls after both variants are qualified.

Each pair uses identical edit bytes, new for that pair, and each variant's own
fixed predecessor. AB/BA order limits shared-station drift. Raw reports retain
every unchanged/edit/restore command and complete reuse verification.
"""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--before-root', required=True, type=Path)
parser.add_argument('--after-root', required=True, type=Path)
parser.add_argument('--out', required=True, type=Path)
parser.add_argument('--tag', required=True)
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=False)
report = {'status': 'running', 'tag': args.tag, 'pairs': []}
aggregates = {}


def save():
    (out/'results.json').write_text(json.dumps(report, indent=2)+'\n')


try:
    for pair in range(3):
        order = ['before', 'after'] if pair % 2 == 0 else ['after', 'before']
        row = {'pair': pair, 'order': order, 'variants': {}}
        report['pairs'].append(row)
        save()
        for variant in order:
            root = getattr(args, variant+'_root').resolve()
            destination = out/f'pair-{pair}-{variant}'
            with (out/f'pair-{pair}-{variant}.log').open('w') as log:
                subprocess.run([sys.executable, str(Path(__file__).with_name('benchmark.py')),
                                '--root', str(root), '--out', str(destination), '--runs', '1',
                                '--tag', f'{args.tag}-{pair}'], stdout=log, stderr=subprocess.STDOUT, check=True)
            result = json.loads((destination/'results.json').read_text())
            assert result['status'] == 'passed'
            assert result['source_restored'] and result['selection_restored']
            edit = next(run for run in result['runs'] if run['stage'] == 'edit-0')
            row['variants'][variant] = edit
            aggregate = aggregates.setdefault(variant, dict(status='running', tag=args.tag,
                source_sha256=result['source_sha256'], source_restored=True, selection_restored=True,
                memory_scope=result['memory_scope'], runs=[]))
            assert aggregate['source_sha256'] == result['source_sha256']
            for run in result['runs']:
                run = copy.deepcopy(run)
                if run['stage'].startswith(('edit-', 'restore-')):
                    run['stage'] = run['stage'].split('-')[0]+f'-{pair}'
                run['pair'] = pair
                run['counterfactual_tag'] = result['tag']
                aggregate['runs'].append(run)
            save()
        assert aggregates['before']['source_sha256'] == aggregates['after']['source_sha256']
    for variant, result in aggregates.items():
        result['status'] = 'passed'
        (out/f'{variant}.json').write_text(json.dumps(result, indent=2)+'\n')
    subprocess.run([sys.executable, str(Path(__file__).with_name('compare.py')),
                    '--before', str(out/'before.json'), '--after', str(out/'after.json'),
                    '--out', str(out/'comparison.json')], check=True)
    report['status'] = 'passed'
except BaseException as error:
    report.update(status='failed', error=repr(error))
    raise
finally:
    save()
