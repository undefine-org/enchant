#!/usr/bin/env python3
"""Retain a verified SDK selection, never machine-local preparation handles.

The receipt is a cache hint, not SDK admission metadata. Normal preparation and
the SDK's sealed inventory still decide whether any compiler unit can be used.
"""
import argparse
import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
STORE = re.compile(r'/nix/store/[0-9a-z]{32}-[^/]+')
CI_ONLY_EXCLUSIONS = ('nix/ci-check.nix', 'nix/ci-release-runtime.nix', 'nix/ci-sdk-gates.nix')


def model_input():
    spec = importlib.util.spec_from_file_location('ci_model_input', ROOT / 'scripts/ci-model-input.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def store_path(value):
    if not isinstance(value, str) or not STORE.fullmatch(value):
        raise ValueError('SDK context must name an immutable Nix store output')
    return Path(value).resolve(strict=True)


def source_fingerprint(source, policy=None):
    loader = importlib.machinery.SourceFileLoader('ci_sdk_inputs', str(ROOT / 'scripts/sdk-inputs'))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    # Use the current preparation policy, exactly as prepare-checkout-sdk does
    # when comparing the captured engine to the caller's declared inputs.
    if policy is None:
        policy = json.loads((ROOT / 'nix/engine-inputs.json').read_text())
    return module.fingerprint(source, policy)


def retained_source_fingerprint(source):
    current = json.loads((ROOT / 'nix/engine-inputs.json').read_text())
    captured = json.loads((source / 'nix/engine-inputs.json').read_text())
    # Exact known policy transitions, never arbitrary historical admission.
    # Preserve each predecessor's original identity and filtering rules so
    # existing SDK units remain reusable without relabelling their source.
    allowed = [current]
    predecessor = current
    if current['reserved'].count('__pycache__') == 1:
        predecessor = dict(current, reserved=[name for name in current['reserved']
                                              if name != '__pycache__'])
        allowed.append(predecessor)
    if all(predecessor['excluded'].count(name) == 1 for name in CI_ONLY_EXCLUSIONS):
        allowed.append(dict(predecessor, excluded=[name for name in predecessor['excluded']
                                                   if name not in CI_ONLY_EXCLUSIONS]))
    canonical = lambda value: json.dumps(value, sort_keys=True, separators=(',', ':'))
    if canonical(captured) not in [canonical(policy) for policy in allowed]:
        raise ValueError('Retained engine policy is neither current nor an exact supported predecessor')
    return source_fingerprint(source, captured)


def describe_sdk(sdk):
    sdk = store_path(str(sdk.resolve(strict=True)))
    subprocess.run(['nix-store', '--check-validity', str(sdk)], check=True,
                   stdout=subprocess.DEVNULL)
    metadata = json.loads((sdk / 'artifact.json').read_text())
    if (metadata.get('version'), metadata.get('kind'), metadata.get('target'),
            metadata.get('producerAPI')) != (1, 'sdk', 'x86_64-linux', 2):
        raise ValueError('Unsupported retained SDK selection')
    for field in ('source', 'compiler', 'dependencies', 'image', 'platform', 'release', 'coordinator'):
        store_path(metadata[field])
    coordinator = store_path(metadata['coordinator'])
    if (sdk / 'preparation-coordinator').resolve(strict=True) != coordinator:
        raise ValueError('SDK coordinator selection differs from its descriptor')
    descriptor = json.loads((coordinator / 'artifact.json').read_text())
    if (descriptor.get('version'), descriptor.get('kind')) != (1, 'artifact-coordinator-runtime'):
        raise ValueError('Invalid SDK coordinator')
    for path in ('bin/bl', 'image/ebin/Elixir.BeamLisp.Launcher.beam',
                 'image/priv/bootstrap/seed/manifest.term', 'unit-store/unit-index.json'):
        if not (sdk / path).is_file():
            raise ValueError('Retained SDK is incomplete: ' + path)
    if not (coordinator / 'foundry/bin/preparation-operation.bl').is_file():
        raise ValueError('Retained coordinator is incomplete')
    return {'version': 1, 'kind': 'ci-sdk-cache-hint', 'sdk': str(sdk),
            'descriptor_sha256': digest(sdk / 'artifact.json'),
            'unit_index_sha256': digest(sdk / 'unit-store/unit-index.json')}


def verify_record(record):
    current = describe_sdk(Path(record['sdk']))
    engine = store_path(record['engine_source'])
    subprocess.run(['nix-store', '--check-validity', str(engine)], check=True,
                   stdout=subprocess.DEVNULL)
    current.update(engine_source=str(engine), engine_fingerprint=retained_source_fingerprint(engine))
    if record != current:
        raise ValueError('Retained SDK cache receipt no longer matches immutable bytes')
    return current


def replace_link(target, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp-' + str(os.getpid()))
    try:
        temporary.symlink_to(target)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def discard_hint(cache):
    for name in ('selection.json', 'sdk-root', 'engine-root'):
        (cache / name).unlink(missing_ok=True)


def retain(root, cache, record):
    sdk = record['sdk']
    # cache-nix-action merges the store/database, but intentionally does not
    # restore /nix/var GC roots. Re-register the real output before cache GC.
    cache.mkdir(parents=True, exist_ok=True)
    for name, target in (('sdk-root', sdk), ('engine-root', record['engine_source'])):
        gc_root = cache / name
        gc_root.unlink(missing_ok=True)
        subprocess.run(['nix-store', '--add-root', str(gc_root), '--indirect',
                        '--realise', target], check=True, stdout=subprocess.DEVNULL)
    replace_link(sdk, root / '.bl/sdks' / record['engine_fingerprint'] / 'result-sdk')
    replace_link(sdk, root / '.bl/sdks/current-sdk')


def capture(root, cache, sdk):
    fingerprint = source_fingerprint(root)
    record = describe_sdk(sdk)
    prior = cache / 'selection.json'
    if prior.is_file():
        predecessor = verify_record(json.loads(prior.read_text()))
        if predecessor['sdk'] == record['sdk'] and predecessor['engine_fingerprint'] == fingerprint:
            record = predecessor
    if 'engine_source' not in record:
        directory = root / '.bl/sdks' / fingerprint
        name = (directory / 'active-job').read_text().strip()
        if not re.fullmatch(r'job-[A-Za-z0-9]+', name):
            raise ValueError('Invalid managed SDK preparation selection')
        job = directory / name
        engine = store_path(str((job / 'source-retained').resolve(strict=True)))
        operation = json.loads((job / 'operation.json').read_text())
        if ((operation.get('version'), operation.get('kind'), operation.get('source'),
             operation.get('product')) != (2, 'sdk', str(engine), 'sdk')
                or (job / 'retained').resolve(strict=True) != Path(record['sdk'])
                or (directory / 'result-sdk').resolve(strict=True) != Path(record['sdk'])):
            raise ValueError('SDK differs from its managed immutable preparation result')
        record.update(engine_source=str(engine), engine_fingerprint=source_fingerprint(engine))
    if record['engine_fingerprint'] != fingerprint:
        raise ValueError('Produced SDK does not describe this checkout engine')
    retain(root, cache, record)
    temporary = cache / 'selection.json.tmp'
    temporary.write_text(json.dumps(record, sort_keys=True) + '\n')
    temporary.replace(cache / 'selection.json')
    return record['sdk']


def capture_completed(root, cache, sdk=None):
    """Keep completed products after failure, without a qualification selector."""
    rejected = (ValueError, KeyError, TypeError, OSError, subprocess.CalledProcessError)
    # Freeze the actual candidate before retaining an older hint can update
    # current-sdk. Missing/unfinished SDKs still permit caching dependencies.
    candidate = sdk or root / '.bl/sdks/current-sdk'
    candidate = candidate.resolve() if (candidate / 'artifact.json').is_file() else None
    prior = cache / 'selection.json'
    previous = None
    if prior.is_file():
        try:
            previous = verify_record(json.loads(prior.read_text()))
        except rejected as error:
            print('ci-sdk-cache: dropping invalid predecessor hint: ' + str(error), file=sys.stderr)
            discard_hint(cache)
    selected = ''
    if candidate:
        try:
            # The same source/operation/result binding as a successful save.
            selected = capture(root, cache, candidate)
        except rejected as error:
            print('ci-sdk-cache: completed SDK hint rejected: ' + str(error), file=sys.stderr)
    if not selected and previous:
        retain(root, cache, previous)
        selected = previous['sdk']
    try:
        model_input().restore(cache)
    except rejected as error:
        print('ci-sdk-cache: omitting incomplete model hint: ' + str(error), file=sys.stderr)
        for name in ('models.json', 'models-root'):
            (cache / name).unlink(missing_ok=True)
    return selected


def restore(root, cache, expected=None, required=False):
    path = cache / 'selection.json'
    if not path.is_file():
        if required or expected:
            raise ValueError('Required SDK cache expired or was not restored; rerun production')
        return ''
    try:
        current = verify_record(json.loads(path.read_text()))
    except (ValueError, KeyError, TypeError, OSError, subprocess.CalledProcessError) as error:
        if required or expected:
            raise
        # A predecessor is optional producer input. Reject its old policy or
        # damaged receipt without preventing the ordinary cold production path.
        # Exact downstream consumers above remain fail-closed.
        print('ci-sdk-cache: dropping invalid predecessor hint: ' + str(error), file=sys.stderr)
        discard_hint(cache)
        return ''
    if expected and current['sdk'] != str(expected.resolve(strict=True)):
        raise ValueError('Restored SDK differs from this run\'s producer')
    # Keep the predecessor's actual fingerprint. A changed checkout must pass
    # previous= through the normal recipe, never relabel old units as current.
    retain(root, cache, current)
    return current['sdk']


def read_selector(path, revision, run_id):
    record = json.loads(path.read_text())
    fields = {'version', 'kind', 'cache_key', 'sdk', 'sdk_descriptor_sha256',
              'candidate_sha256', 'engine_fingerprint', 'revision', 'run_id',
              'models', 'model_pins_sha256'}
    if (not isinstance(record, dict) or set(record) != fields
            or any(not isinstance(record[name], str) for name in fields - {'version'})
            or type(record['version']) is not int):
        raise ValueError('Selector differs from the requested successful CI revision/run')
    if ((record['version'], record['kind']) != (1, 'ci-sdk-selection')
            or not re.fullmatch(r'[0-9a-f]{40}', record['revision'])
            or not re.fullmatch(r'[0-9]+', record['run_id'])
            or not re.fullmatch(r'enchant-nix-v1-[A-Za-z0-9-]+', record['cache_key'])
            or not STORE.fullmatch(record['sdk'])
            or not STORE.fullmatch(record['models'])
            or any(not re.fullmatch(r'[0-9a-f]{64}', record[name]) for name in (
                'sdk_descriptor_sha256', 'candidate_sha256', 'engine_fingerprint', 'model_pins_sha256'))
            or record['revision'] != revision or record['run_id'] != run_id):
        raise ValueError('Selector differs from the requested successful CI revision/run')
    return record


def write_selector(root, cache, path, key, revision, run_id):
    retained = verify_record(json.loads((cache / 'selection.json').read_text()))
    if retained['engine_fingerprint'] != source_fingerprint(root):
        raise ValueError('Selector engine differs from this checkout')
    sdk = Path(retained['sdk'])
    metadata = json.loads((sdk / 'artifact.json').read_text())
    models = model_input().restore(cache)
    if not models:
        raise ValueError('Full inventory selector requires its pinned model prerequisite')
    record = {'version': 1, 'kind': 'ci-sdk-selection', 'cache_key': key, 'sdk': str(sdk),
              'sdk_descriptor_sha256': retained['descriptor_sha256'],
              'candidate_sha256': digest(store_path(metadata['release']) / 'bl.drop'),
              'engine_fingerprint': retained['engine_fingerprint'],
              'models': models['path'], 'model_pins_sha256': models['pins_sha256'],
              'revision': revision, 'run_id': run_id}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True) + '\n')
    return read_selector(path, revision, run_id)


def verify_selector(root, cache, path, revision, run_id):
    record = read_selector(path, revision, run_id)
    retained = verify_record(json.loads((cache / 'selection.json').read_text()))
    sdk = Path(retained['sdk'])
    metadata = json.loads((sdk / 'artifact.json').read_text())
    models = model_input().restore(cache)
    if (record['sdk'] != retained['sdk']
            or record['sdk_descriptor_sha256'] != retained['descriptor_sha256']
            or record['candidate_sha256'] != digest(store_path(metadata['release']) / 'bl.drop')
            or record['engine_fingerprint'] != retained['engine_fingerprint']
            or record['engine_fingerprint'] != source_fingerprint(root)
            or not models or record['models'] != models['path']
            or record['model_pins_sha256'] != models['pins_sha256']):
        raise ValueError('Selector does not describe the restored SDK/candidate/engine bytes')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('restore', 'save', 'save-products', 'write-selector', 'read-selector', 'verify-selector'))
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--cache', type=Path, default=Path.home() / '.cache/enchant-ci')
    parser.add_argument('--sdk', type=Path)
    parser.add_argument('--required', action='store_true')
    parser.add_argument('--selector', type=Path)
    parser.add_argument('--key')
    parser.add_argument('--revision')
    parser.add_argument('--run-id')
    parser.add_argument('--github-output', action='store_true')
    args = parser.parse_args()
    if args.operation == 'save' and not args.sdk:
        parser.error('Saving requires an explicitly qualified --sdk')
    selector = args.operation.endswith('-selector')
    if selector and not (args.selector and args.revision and args.run_id):
        parser.error('Selector operations require --selector, --revision and --run-id')
    if args.operation == 'write-selector' and not args.key:
        parser.error('Writing a selector requires --key')
    try:
        if selector:
            if args.operation == 'write-selector':
                record = write_selector(args.root.resolve(), args.cache.resolve(), args.selector,
                                        args.key, args.revision, args.run_id)
            elif args.operation == 'verify-selector':
                record = verify_selector(args.root.resolve(), args.cache.resolve(), args.selector,
                                         args.revision, args.run_id)
            else:
                record = read_selector(args.selector, args.revision, args.run_id)
            if args.github_output:
                with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
                    print('key=' + record['cache_key'], file=output)
                    print('sdk=' + record['sdk'], file=output)
            print(json.dumps(record, sort_keys=True))
            return 0
        if args.operation == 'save-products':
            sdk = capture_completed(args.root.resolve(), args.cache.resolve(), args.sdk)
        else:
            sdk = (capture(args.root.resolve(), args.cache.resolve(), args.sdk) if args.operation == 'save'
                   else restore(args.root.resolve(), args.cache.resolve(), args.sdk, args.required))
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        print('ci-sdk-cache: ' + str(error), file=sys.stderr)
        return 1
    print(sdk)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
