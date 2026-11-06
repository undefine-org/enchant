"""Summarize matched real-producer controls without conflating cache layers."""
import argparse
import json
from pathlib import Path
import statistics

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--before', required=True, type=Path)
parser.add_argument('--after', required=True, type=Path)
parser.add_argument('--out', required=True, type=Path)
args = parser.parse_args()
before = json.loads(args.before.read_text())
after = json.loads(args.after.read_text())
assert before['status'] == after['status'] == 'passed'
assert before['tag'] == after['tag']
assert before['source_sha256'] == after['source_sha256']


def summarize(rows):
    assert rows
    return {'median': statistics.median(rows), 'min': min(rows), 'max': max(rows), 'samples': len(rows)}


def variant(report):
    assert report['source_restored'] and report['selection_restored']
    edits = [r for r in report['runs'] if r['stage'].startswith('edit-')]
    assert len(edits) >= 3
    units = []
    phases = {}
    for row in edits:
        unit = [r['value'] for r in row['phases'] if r['kind'] == 'SDK-UNIT-PHASES']
        assert len(unit) == 1
        unit = unit[0]
        assert unit['compiled'] > 0
        assert row['byte_identical_restored_units'] == unit['cached']
        assert unit['input-reads']['initial'] == unit['input-reads']['final']
        units.append({key: unit[key] for key in ('compiled', 'cached', 'jobs', 'input-reads')})
        phases.setdefault('units', []).append(unit['elapsed-us']/1e6)
        for key, value in unit['phases-us'].items():
            phases.setdefault('units/'+key, []).append(value/1e6)
        for phase in row['phases']:
            if phase['kind'] == 'SDK-PHASE':
                value = phase['value']
                phases.setdefault(value['stage'], []).append(value['elapsed-us']/1e6)
    assert all(unit == units[0] for unit in units)
    return {'edit_seconds': summarize([r['seconds'] for r in edits]),
            'phases_seconds': {key: summarize(values) for key, values in phases.items()},
            'units': units[0],
            'unchanged_seconds': summarize([r['seconds'] for r in report['runs']
                                          if r['stage'].startswith('unchanged')]),
            'restore_seconds': summarize([r['seconds'] for r in report['runs']
                                        if r['stage'].startswith('restore-')]),
            'client_rss_kib': summarize([r['client_max_rss_kib'] for r in edits]),
            'client_memory_scope': report['memory_scope'],
            'station_load_after': [r['load_after'] for r in edits],
            'available_before_kib': [r['available_before_kib'] for r in edits],
            'selections': [r['selection'] for r in edits]}


a, b = variant(before), variant(after)
assert a['units'] == b['units']
result = {'status': 'passed', 'tag': before['tag'], 'before': a, 'after': b,
          'interpretation': 'Shared-station median and range; compilation phases come from the corresponding producer log. Client RSS excludes independent compiler/coordinator/guest processes.'}
args.out.write_text(json.dumps(result, indent=2)+'\n')
