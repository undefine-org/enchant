#!/usr/bin/env python3
"""Verify the selected Nix compiler's existing P/B/C proof without executing it.

The registered immutable compiler output is the evidence boundary. Generation
directories are not retained: compare their stored inventories, then hash the
complete installed C seed and the selected SDK image's floor independently.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys


STORE = re.compile(r'/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-[^/]+')
SHA = re.compile(r'[0-9a-f]{64}')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def regular(path):
    require(path.is_file() and not path.is_symlink(), f'Expected regular file: {path}')
    return path


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f'Duplicate JSON key in {path}: {key}')
            result[key] = value
        return result
    return json.loads(regular(path).read_text(), object_pairs_hook=unique)


def inventory(value, label):
    require(isinstance(value, dict) and value, f'Missing {label} inventory')
    for name, sha in value.items():
        require(isinstance(name, str) and name not in ('.', '..')
                and PurePosixPath(name).name == name and '\\' not in name
                and (name == 'manifest.term' or name.endswith(('.beam', '.app')))
                and isinstance(sha, str) and SHA.fullmatch(sha),
                f'Invalid {label} inventory entry: {name}')
    require({'manifest.term', 'beam_lisp.app'} <= value.keys(),
            f'Incomplete {label} inventory')
    return value


def actual_inventory(directory):
    require(directory.is_dir() and not directory.is_symlink(),
            f'Expected seed directory: {directory}')
    return {path.name: digest(regular(path)) for path in sorted(directory.iterdir())}


def manifest_keys(path):
    # Read the two binary-string fields as data; never evaluate an Erlang term.
    pairs = re.findall(rb'<<"(compiler_key|build_key)">>\s*=>\s*<<"([0-9a-f]{64})">>',
                       regular(path).read_bytes())
    require(len(pairs) == 2 and {name for name, _ in pairs} == {b'compiler_key', b'build_key'},
            'Seed manifest must contain unique compiler/build keys')
    return {key.decode(): value.decode() for key, value in pairs}


def verify_proof(compiler, image_floor):
    """Check proof structure and actual bytes; callers establish store custody."""
    qualification = compiler / 'qualification'
    require(qualification.is_dir() and not qualification.is_symlink(),
            'Missing compiler qualification directory')
    expected = {'inputs.json', 'result.json'} | {
        f'{label}.{suffix}' for label in 'PBC'
        for suffix in ('bootstrap.json', 'boot.log', 'producer.log')}
    require({path.name for path in qualification.iterdir()} == expected,
            'Incomplete or unexpected compiler qualification files')
    report = read_json(qualification / 'result.json')
    require(isinstance(report, dict) and type(report.get('version')) is int
            and report['version'] == 1 and report.get('kind') == 'artifact-generation-qualification',
            'Unsupported compiler qualification report')
    require(report.get('self_reproduction_qualified') is True
            and report.get('changed_files') == [] and 'error' not in report,
            'Compiler self-reproduction did not pass')
    require(report.get('floor_installed') is False
            and report.get('native_execution_admission') is False,
            'Compiler qualification has invalid trust boundaries')
    stages = report.get('stages')
    require(isinstance(stages, list) and len(stages) == 2,
            'Compiler qualification must contain exactly B and C')
    generations = [report.get('preparation'), *stages]
    initial = inventory(report.get('initial_seed_files'), 'initial seed')
    inputs = read_json(qualification / 'inputs.json')
    require(isinstance(inputs, dict) and inputs, 'Missing compiler input inventory')
    for name, sha in inputs.items():
        require(isinstance(name, str) and not PurePosixPath(name).is_absolute()
                and '..' not in PurePosixPath(name).parts
                and isinstance(sha, str) and SHA.fullmatch(sha),
                'Invalid compiler input inventory')
    require({'env.bl', 'scripts/check-source-floor', 'scripts/qualify-artifact-generation',
             'scripts/demo-artifact-production', 'test/scripts/artifact-generation.bl'} <= inputs.keys(),
            'Compiler input inventory lacks producer/source gates')
    require({name.removeprefix('priv/bootstrap/seed/'): sha for name, sha in inputs.items()
             if name.startswith('priv/bootstrap/seed/')} == initial,
            'Initial compiler floor differs from recorded producer inputs')

    boot_seeds = []
    boot_runtimes = []
    for label, generation in zip('PBC', generations):
        require(isinstance(generation, dict) and generation.get('generation') == label
                and generation.get('produced') is True
                and generation.get('fresh_boot_qualified') is True,
                f'Generation {label} was not produced and freshly booted')
        files = inventory(generation.get('files'), label)
        bootstrap = read_json(qualification / f'{label}.bootstrap.json')
        require(isinstance(bootstrap, dict) and generation.get('bootstrap') == bootstrap
                and bootstrap.get('stable_predecessor_unchanged') is True,
                f'Generation {label} bootstrap trust receipt differs or failed')
        for field in ('input_build_key', 'input_compiler_key', 'seed_build_key', 'seed_compiler_key'):
            require(isinstance(bootstrap.get(field), str) and SHA.fullmatch(bootstrap[field]),
                    f'Generation {label} has invalid bootstrap keys')
        current = (bootstrap['input_build_key'], bootstrap['input_compiler_key'])
        predecessor = (bootstrap['seed_build_key'], bootstrap['seed_compiler_key'])
        require(bootstrap.get('installation') in ('current', 'previous-generation')
                and (bootstrap['installation'] == 'current') == (current == predecessor)
                and (label == 'P' or bootstrap['installation'] == 'current'),
                f'Generation {label} has invalid predecessor installation')
        producer = regular(qualification / f'{label}.producer.log').read_text().splitlines()
        require(bool(producer) and re.fullmatch(
            r'ARTIFACT-GENERATION \{:modules ' + str(sum(n.endswith('.beam') for n in files))
            + r', :milliseconds [0-9]+, :units [1-9][0-9]*, :producer-unchanged true\}',
            producer[-1]), f'Generation {label} has no successful producer receipt')
        lines = regular(qualification / f'{label}.boot.log').read_text().splitlines()
        require(bool(lines), f'Generation {label} has no fresh-boot receipt')
        boot = json.loads(lines[-1])
        require(isinstance(boot, dict) and boot.get('kind') == 'fresh-source-floor'
                and boot.get('status') == 'passed' and boot.get('tests') == []
                and isinstance(boot.get('seed'), str) and Path(boot['seed']).is_absolute()
                and Path(boot['seed']).name == label
                and isinstance(boot.get('runtime'), str) and boot['runtime'],
                f'Generation {label} has an invalid fresh-boot receipt')
        boot_seeds.append(Path(boot['seed']))
        boot_runtimes.append(boot['runtime'])
    require(len(set(boot_runtimes)) == 1 and len({path.parent for path in boot_seeds}) == 1,
            'Generation fresh-boot receipts use different runtimes or output roots')
    require(generations[0].get('producer_floor') == report.get('initial_seed')
            and isinstance(report.get('initial_seed'), str)
            and Path(report['initial_seed']).is_absolute()
            and all(stage.get('producer_floor') == str(floor)
                    for stage, floor in zip(generations[1:], boot_seeds[:-1])),
            'Compiler generation predecessor chain differs')
    require(len({(g['bootstrap']['input_build_key'], g['bootstrap']['input_compiler_key'])
                 for g in generations}) == 1, 'Compiler inputs changed between generations')
    require(generations[1]['files'] == generations[2]['files'], 'B and C byte inventories differ')
    final = generations[2]['files']
    require(actual_inventory(compiler / 'seed') == final,
            'Installed compiler seed differs from complete generation C inventory')
    keys = manifest_keys(compiler / 'seed/manifest.term')
    require(all(keys[key] == generations[2]['bootstrap']['input_' + key] for key in keys),
            'Installed compiler manifest differs from qualified compiler keys')
    require(actual_inventory(image_floor) == final,
            'SDK image floor differs from complete qualified compiler seed')
    return {'status': 'passed', 'files': len(final), 'generations': ['P', 'B', 'C'],
            'manifest_sha256': final['manifest.term'],
            'qualification_sha256': digest(qualification / 'result.json'),
            'inputs_sha256': digest(qualification / 'inputs.json'), **keys}


def store_output(value):
    require(isinstance(value, str) and STORE.fullmatch(value),
            'Expected an immutable top-level Nix store output')
    path = Path(value)
    require(path.is_dir() and path.resolve(strict=True) == path,
            'Expected a genuine Nix store output directory')
    return path


def check_sdk(selected):
    sdk = store_output(str(selected.resolve(strict=True)))
    metadata = read_json(sdk / 'artifact.json')
    require(type(metadata.get('version')) is int and metadata['version'] == 1
            and metadata.get('kind') == 'sdk' and metadata.get('producerAPI') == 2
            and metadata.get('target') == 'x86_64-linux', 'Unsupported SDK selection')
    compiler, image = (store_output(metadata[field]) for field in ('compiler', 'image'))
    # Verify the registered NAR hashes, not just path-shaped names or success
    # markers in a mutable report. This performs no realization or compilation.
    subprocess.run(['nix-store', '--check-validity', str(sdk), str(compiler), str(image)],
                   check=True, timeout=120)
    subprocess.run(['nix-store', '--verify-path', str(sdk), str(compiler), str(image)],
                   check=True, timeout=120)
    image_metadata = read_json(image / 'artifact.json')
    require(image_metadata.get('compiler') == str(compiler)
            and image_metadata.get('kind') == 'sdk' and image_metadata.get('version') == 1,
            'Selected SDK image uses a different compiler')
    require((sdk / 'image').resolve(strict=True) == (image / 'image').resolve(strict=True),
            'SDK image link differs from selected image')
    receipt = verify_proof(compiler, sdk / 'image/priv/bootstrap/seed')
    return {'version': 1, 'kind': 'produced-compiler-check', 'sdk': str(sdk),
            'compiler': str(compiler), 'sdk_descriptor_sha256': digest(sdk / 'artifact.json'),
            **receipt}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--out', type=Path, help='write an optional JSON receipt')
    args = parser.parse_args()
    try:
        receipt = check_sdk(args.sdk)
        encoded = json.dumps(receipt, sort_keys=True) + '\n'
        if args.out:
            with args.out.open('x') as stream:
                stream.write(encoded)
        print(encoded, end='')
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
        print('check-produced-compiler: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
