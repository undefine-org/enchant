#!/usr/bin/env python3
"""Bind reviewed historical closures to exact immutable execution receipts.

This starts no VM and builds no SDK. --apply updates the case manifest only
after checking every selected regression, mutation anchor and relevant input.
Old receipts and their historical_case_closed flags remain untouched.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import runpy


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def key(row):
    return tuple(row[name] for name in ('path', 'namespace', 'test'))


def reference(path):
    return {'path': str(path.resolve()), 'sha256': digest(path)}


def load_execution(root, directory):
    result = json.loads((directory / 'result.json').read_text())
    assert result['status'] in ('passed', 'regressions-passed'), directory
    assert result['frozen_inputs_unchanged'] is True, directory
    inputs = json.loads((directory / 'inputs.json').read_text())
    hashes = inputs.get('inputs', inputs)
    execution = json.loads((directory / 'execution.json').read_text())
    sdk = Path(result['sdk'])
    sdk_hash = result.get('sdk_metadata_sha256', inputs.get('sdk', {}).get('metadata'))
    assert digest(sdk / 'artifact.json') == sdk_hash
    assert Path(execution['image']['priv-root']).resolve() == (sdk / 'image/priv').resolve()
    floor = sdk / 'image/priv/bootstrap/seed/manifest.term'
    assert execution['image']['manifest-sha256'] == digest(floor)
    tests = {}
    for file in execution['files']:
        assert file['status'] == 'passed' and file['tests'], file
        for test in file['tests']:
            assert test['pass'] > 0 and test['fail'] == test['error'] == 0, test
            tests[key(dict(test, path=file['path']))] = test
    return {'directory': directory, 'sdk': sdk, 'sdk_sha256': sdk_hash,
            'hashes': hashes, 'tests': tests, 'image': execution['image'],
            'references': {name: reference(directory / name)
                           for name in ('result.json', 'inputs.json', 'execution.json')}}


def validate_supporting_counter(root, baseline, sdk):
    """The wrong-MFA negative is a genuine failed six-phase run, not a test pass."""
    positive, negative = (Path(baseline[name]).resolve()
                          for name in ('positive_directory', 'negative_directory'))
    receipts = [json.loads((path / 'result.json').read_text()) for path in (positive, negative)]
    assert [row['status'] for row in receipts] == ['passed', 'failed']
    assert all(row['frozen_inputs_unchanged'] and Path(row['sdk']) == sdk for row in receipts)
    assert all(row['sdk_metadata_sha256'] == digest(sdk / 'artifact.json') for row in receipts)
    producer = baseline['producer']
    current = (root / producer).read_text()
    assert current.count(baseline['before']) == 1
    mutant = current.replace(baseline['before'], baseline['after'])
    positive_inputs, negative_inputs = (json.loads((path / 'inputs.json').read_text())
                                       for path in (positive, negative))
    assert positive_inputs[producer] == digest(root / producer)
    assert negative_inputs[producer] == hashlib.sha256(mutant.encode()).hexdigest()
    for path in baseline['unchanged_inputs']:
        assert positive_inputs[path] == negative_inputs[path] == digest(root / path), path
    assert 'immutable preparation waited for publication lock' in (negative / 'persistence.log').read_text()
    phases = json.loads((positive / 'persistence-result.json').read_text())['phases']
    assert [row['phase'] for row in phases] == ['first', 'unchanged', 'restore', 'changed', 'corrupt', 'contended']
    contended = phases[-1]
    assert contended['artifact_preparations'] >= 2 and contended['artifact_restorations'] == 2
    assert contended['compiled'] == contended['initializer_executions'] == 0
    return {'baseline': baseline, 'positive': reference(positive / 'result.json'),
            'negative': reference(negative / 'result.json'),
            'positive_log': reference(positive / 'persistence.log'),
            'negative_log': reference(negative / 'persistence.log')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument('--proposals', type=Path, required=True,
                        help='Root-reviewed array of id, baseline, selectors and relevant_inputs')
    parser.add_argument('--proof', type=Path, action='append', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    root = args.root.resolve()
    manifest_path = root / 'research/execution-protocol-audit/cases.json'
    validator = runpy.run_path(str(root / 'scripts/check-execution-history'))
    original = json.loads(manifest_path.read_text())
    updated = copy.deepcopy(original)
    cases = {case['id']: case for case in updated['cases']}
    proofs = [load_execution(root, path.resolve()) for path in args.proof]
    assert len({(str(p['sdk']), p['sdk_sha256']) for p in proofs}) == 1
    assert all(p['image'] == proofs[0]['image'] for p in proofs)
    proposals = json.loads(args.proposals.read_text())
    assert len({row['id'] for row in proposals}) == len(proposals)
    closures = []
    for proposal in proposals:
        case = cases[proposal['id']]
        baseline = proposal['baseline']
        producer = baseline['producer']
        assert baseline['kind'] == 'source-mutation'
        assert digest(root / producer) == baseline['producer_sha256']
        assert (root / producer).read_text().count(baseline['before']) == 1
        assert baseline['before'] != baseline['after']
        assert proposal.get('obligations_addressed'), proposal['id']
        seen = {key(selector) for selector in case['selectors']}
        for selector in proposal.get('selectors', []):
            if key(selector) not in seen:
                case['selectors'].append(selector)
                seen.add(key(selector))
        assert key(baseline['selector']) in seen
        receipts = []
        for selector in case['selectors']:
            wanted = key(selector)
            relevant = set(proposal.get('relevant_inputs', [])) | {selector['path']}
            for dependency in proposal.get('selector_inputs', []):
                if key(dependency['selector']) == wanted:
                    relevant.update(dependency['paths'])
            # The causal selector must bind the producer, not only its fixture.
            if wanted == key(baseline['selector']):
                relevant.add(producer)
                relevant.update(proposal.get('causal_inputs', []))
            matches = [proof for proof in proofs if wanted in proof['tests'] and
                       all(proof['hashes'].get(path) == digest(root / path) for path in relevant)]
            assert matches, (proposal['id'], wanted, 'missing exact current-input receipt')
            chosen = matches[0]
            receipts.append({'selector': selector, 'receipt': str(chosen['directory']),
                             'result': chosen['tests'][wanted],
                             'inputs_sha256': {path: digest(root / path) for path in sorted(relevant)}})
        # Runtime producer controls must concern the actual selected SDK Source.
        if producer.startswith('priv/'):
            assert digest(root / producer) == digest(proofs[0]['sdk'] / 'image' / producer), producer
        case['baseline'] = baseline
        previous_remaining = proposal.get('original_remaining', case['remaining'])
        case['remaining'] = []
        assert validator['controls_bound'](case)
        supporting = [validate_supporting_counter(root, control, proofs[0]['sdk'])
                      for control in proposal.get('supporting_counters', [])]
        closures.append({'id': case['id'], 'original_remaining': previous_remaining,
                         'obligations_addressed': proposal['obligations_addressed'],
                         'baseline': baseline, 'selectors': receipts,
                         'limits': proposal.get('limits', []),
                         'supporting_counters': supporting,
                         'old_historical_case_closed_flags_modified': False})
    report = {'version': 1, 'scope': 'Case-specific causal closure, not full release qualification',
              'sdk': str(proofs[0]['sdk']), 'sdk_metadata_sha256': proofs[0]['sdk_sha256'],
              'image': proofs[0]['image'], 'SDK_rebuilt': False,
              'closures': closures,
              'closed_cases_in_this_reconciliation': sum(bool(row['original_remaining']) for row in closures),
              'revalidated_closed_cases': [row['id'] for row in closures if not row['original_remaining']],
              'proofs': [proof['references'] for proof in proofs],
              'remaining': validator['audit'](updated['cases'])['open']}
    # Validate the entire proposed manifest even for a dry run. An edited
    # producer may have invalidated an old pin; only executed proposals can
    # repair it, and every unrelated case must still satisfy the stock rules.
    temporary = manifest_path.with_suffix('.proposed.json')
    try:
        temporary.write_text(json.dumps(updated, indent=2) + '\n')
        validator['read_manifest'](root, temporary)
        if args.apply:
            temporary.replace(manifest_path)
    finally:
        temporary.unlink(missing_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'closed': report['closed_cases_in_this_reconciliation'],
                      'revalidated': report['revalidated_closed_cases'], 'open': len(report['remaining']),
                      'applied': args.apply}))


if __name__ == '__main__':
    main()
