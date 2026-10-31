#!/usr/bin/env python3
"""Bind a release's measured host requirements and provenance to its exact bytes."""
import argparse
import hashlib
from importlib.machinery import SourceFileLoader
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent.parent


def load_helper(name, path):
    spec = importlib.util.spec_from_loader(name, SourceFileLoader(name, str(path)))
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    return helper


def digest(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def version_tuple(value):
    if not re.fullmatch(r'[0-9]+(?:\.[0-9]+)+', value):
        raise ValueError('Invalid measured glibc version')
    return tuple(map(int, value.split('.')))


def verify(candidate, receipt, revision=None):
    if (receipt.get('version'), receipt.get('kind'), receipt.get('target')) != (
            1, 'release-requirements', 'x86_64-linux'):
        raise ValueError('Unsupported release requirements')
    if digest(candidate) != receipt['candidate_sha256']:
        raise ValueError('Release bytes differ from the qualified requirements receipt')
    if version_tuple(receipt['minimum_glibc']) <= (0, 0):
        raise ValueError('Release has no measured glibc requirement')
    if not re.fullmatch(r'[0-9a-f]{40}', receipt['revision']):
        raise ValueError('Release revision must be a full Git commit')
    if revision is not None and receipt['revision'] != revision:
        raise ValueError('Release revision differs from the publication request')
    return receipt


def create(candidate, sdk, runtime, revision, label):
    materializer = load_helper('release_selection', ROOT / 'scripts/ci-materialize-candidate.py')
    selected, metadata, _, platform, _, expected = materializer.selection(sdk, candidate)
    adapter = load_helper('release_test_runtime', ROOT / 'scripts/with-release-runtime')
    runtime, _ = adapter.runtime_identity(runtime, selected)
    runtime_metadata = json.loads((runtime / 'runtime.json').read_text())
    env = dict(os.environ, READELF=str(runtime / 'bin/readelf'),
               DROP_BIN=str(Path(platform['executor']) / 'bin/drop'))
    measured = subprocess.check_output(
        ['sh', str(ROOT / 'tooling/drop/glibc-floor.sh'), str(candidate)], env=env, text=True).strip()
    floor, limiting_file = measured.split('  ', 1)
    if version_tuple(floor) > version_tuple(runtime_metadata['glibcVersion']):
        raise ValueError('Artifact requires a newer libc than its qualification runtime')
    application = (selected / 'image/ebin/beam_lisp.app').read_text()
    version = re.search(r'\{vsn,\s*"([^"]+)"\}', application)
    if version is None:
        raise ValueError('SDK application resource has no version')
    receipt = {'version': 1, 'kind': 'release-requirements', 'target': 'x86_64-linux',
               'candidate_sha256': expected, 'sdk_descriptor_sha256': digest(selected / 'artifact.json'),
               'compiler_manifest_sha256': digest(selected / 'image/priv/bootstrap/seed/manifest.term'),
               'revision': revision, 'release_label': label,
               'application_version': version.group(1), 'minimum_glibc': floor,
               'limiting_elf': limiting_file, 'qualification': 'pinned-fhs-runtime',
               'qualification_glibc': runtime_metadata['glibcVersion'],
               'nixpkgs_revision': runtime_metadata['nixpkgs']}
    return verify(candidate, receipt, revision)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='operation', required=True)
    produce = commands.add_parser('create')
    for name in ('candidate', 'sdk', 'runtime', 'out'):
        produce.add_argument('--' + name, type=Path, required=True)
    produce.add_argument('--revision', required=True)
    produce.add_argument('--label', default='')
    check = commands.add_parser('verify')
    check.add_argument('--candidate', type=Path, required=True)
    check.add_argument('--receipt', type=Path, required=True)
    check.add_argument('--revision')
    args = parser.parse_args()
    if args.operation == 'create':
        receipt = create(args.candidate.resolve(strict=True), args.sdk, args.runtime, args.revision, args.label)
        args.out.write_text(json.dumps(receipt, sort_keys=True, indent=2) + '\n')
    else:
        receipt = verify(args.candidate, json.loads(args.receipt.read_text()), args.revision)
    print(f"{receipt['target']}: glibc >= {receipt['minimum_glibc']}; "
          f"application {receipt['application_version']}; commit {receipt['revision']}")


if __name__ == '__main__':
    main()
