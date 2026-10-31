#!/usr/bin/env python3
"""Project an already-produced portable drop for direct-runtime CI fixtures.

The normal public launcher remains the only SDK producer. This helper checks
that publication's digest, uses its existing stock unpacker, and preserves
sealed metadata unchanged. It does not transfer the SDK producer closure.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def immutable(path):
    path = Path(path).resolve(strict=True)
    if not re.fullmatch(r'/nix/store/[0-9a-z]{32}-[^/]+', str(path)) or not path.is_dir():
        raise ValueError('Expected a retained top-level Nix store product: ' + str(path))
    return path


def selection(sdk, candidate):
    sdk = immutable(sdk)
    metadata = json.loads((sdk / 'artifact.json').read_text())
    if (metadata['version'], metadata['kind'], metadata['target']) != (1, 'sdk', 'x86_64-linux'):
        raise ValueError('Unsupported produced SDK')
    release, platform = immutable(metadata['release']), immutable(metadata['platform'])
    portable = json.loads((release / 'artifact.json').read_text())
    if (portable['version'], portable['kind'], portable['target'], portable['file'], portable['compiler']) != (
            1, 'release', 'x86_64-linux', 'bl.drop', metadata['compiler']):
        raise ValueError('SDK/release identity mismatch')
    expected = portable['sha256']
    if digest(release / 'bl.drop') != expected or digest(candidate) != expected:
        raise ValueError('Candidate bytes differ from the selected immutable release')
    descriptor = json.loads((platform / 'platform.json').read_text())
    coordinator = immutable(metadata['coordinator'])
    if (sdk / 'preparation-coordinator').resolve(strict=True) != coordinator:
        raise ValueError('SDK coordinator retention mismatch')
    return sdk, metadata, platform, descriptor, coordinator, expected


def materialize(root, candidate, sdk):
    sdk, metadata, platform, descriptor, coordinator, expected = selection(sdk, candidate)
    output = root / '.bl/ci-runtime'
    for name in ('.bl/ci-runtime', 'build', 'priv/native', 'priv/z3', '.bl/lib', '.bl/ci-image',
                 'tooling/drop/target/release/drop-launcher'):
        if os.path.lexists(root / name):
            raise ValueError('Refusing to replace an existing fixture projection: ' + name)
    output.parent.mkdir(parents=True, exist_ok=True)
    # This tool is already in the selected platform's executor product. Neither
    # Cargo nor a second Nix build is needed to obtain it.
    unpacker = immutable(descriptor['executor']) / 'bin/drop'
    subprocess.run([str(unpacker), 'unpack', str(candidate), '--dir', str(output)], check=True)
    apps = sorted((output / 'lib').glob('beam_lisp-*'))
    if len(apps) != 1:
        raise ValueError('Portable candidate must contain exactly one language application')
    app = apps[0]
    watched = ['priv/bootstrap/seed/manifest.term', 'priv/precompiled.term', 'priv/sdk-code.term']
    for name in watched:
        if (app / name).read_bytes() != (sdk / 'image' / name).read_bytes():
            raise ValueError('Portable packaging changed sealed compiler metadata: ' + name)
    # Fresh checkout-only compatibility projections. Their contents come from
    # the selected portable image; the sealed inventory and floor stay intact.
    links = {'build': app / 'ebin', 'priv/native': app / 'priv/native',
             'priv/z3': app / 'priv/z3', '.bl/lib': output / 'lib', '.bl/ci-image': app}
    for name, target in links.items():
        destination = root / name
        if os.path.lexists(destination):
            raise ValueError('Refusing to replace an existing fixture projection: ' + name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.symlink_to(os.path.relpath(target, destination.parent), target_is_directory=True)
    launcher = root / 'tooling/drop/target/release/drop-launcher'
    if os.path.lexists(launcher):
        raise ValueError('Refusing to replace an existing stock launcher')
    launcher.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(immutable(descriptor['executor']) / 'bin/drop-launcher', launcher)
    receipt = {'version': 1, 'kind': 'ci-runtime-projection', 'sdk': str(sdk),
               'sdk_descriptor_sha256': digest(sdk / 'artifact.json'), 'candidate_sha256': expected,
               'image': str(app.relative_to(root)), 'metadata_sha256': {name: digest(app / name) for name in watched}}
    (root / '.bl/ci-sdk.json').write_text(json.dumps(receipt, sort_keys=True) + '\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    args = parser.parse_args()
    root, candidate = args.root.resolve(), args.candidate.resolve(strict=True)
    result = materialize(root, candidate, args.sdk)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
