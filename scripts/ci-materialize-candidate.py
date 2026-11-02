#!/usr/bin/env python3
"""Project an already-produced portable drop for direct-runtime CI fixtures.

The normal public launcher remains the only SDK producer. This helper checks
that publication's digest, uses its existing stock unpacker, and preserves
sealed metadata unchanged. It does not transfer the SDK producer closure.
"""
import argparse
import contextlib
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


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
    spec = importlib.util.spec_from_file_location('sdk_release', Path(__file__).with_name('sdk-release.py'))
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    release, platform = helper.release(sdk), immutable(metadata['platform'])
    portable = json.loads((release / 'artifact.json').read_text())
    if (portable['version'], portable['kind'], portable['target'], portable['file'], portable['compiler']) != (
            1, 'release', 'x86_64-linux', 'bl.drop', metadata['compiler']):
        raise ValueError('SDK/release identity mismatch')
    expected = portable['sha256']
    if digest(candidate) != expected:
        raise ValueError('Candidate bytes differ from the selected immutable release')
    descriptor = json.loads((platform / 'platform.json').read_text())
    coordinator = immutable(metadata['coordinator'])
    if (sdk / 'preparation-coordinator').resolve(strict=True) != coordinator:
        raise ValueError('SDK coordinator retention mismatch')
    return sdk, metadata, platform, descriptor, coordinator, expected


def tree_identity(root):
    """Compare every extracted path, byte and executable bit; never follow links."""
    rows = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            path = Path(directory) / name
            relative = str(path.relative_to(root))
            if path.is_symlink():
                rows[relative] = ('link', os.readlink(path))
            elif path.is_dir():
                rows[relative] = ('directory',)
            elif path.is_file():
                rows[relative] = ('file', digest(path), path.stat().st_mode & 0o111)
            else:
                raise ValueError('Unsupported runtime fixture file: ' + str(path))
    return rows


def matching_file(path, references, final_target=None):
    references = [reference for reference in references if reference.is_file()]
    if path.is_symlink():
        resolved = path.resolve(strict=True)
        allowed = {reference.resolve(strict=True) for reference in references}
        if final_target is not None:
            allowed.add(final_target.resolve())
        if resolved not in allowed:
            return False
    if not path.is_file():
        return False
    return any(digest(path) == digest(reference)
               and path.stat().st_mode & 0o111 == reference.stat().st_mode & 0o111
               for reference in references)


def native_custody(directory, names, locks):
    """Preserve permanent anchors, and refuse an active existing publisher."""
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError('Foreign native custody metadata: ' + str(directory))
    directories = {'artifact-custody', 'artifact-custody/.bl', 'artifact-custody/.bl/locks'}
    files = set()
    for name in names:
        directories.add('artifact-custody/' + name)
        files.add('artifact-custody/' + name + '/.claim')
        files.add('artifact-custody/.bl/locks/' + name)
        files.add('artifact-custody/.bl/locks/' + name + '.followers')
    for parent, dirs, entries in os.walk(directory, followlinks=False):
        for name in dirs + entries:
            path = Path(parent) / name
            relative = str(path.relative_to(directory))
            if path.is_symlink() or not ((path.is_dir() and relative in directories)
                                        or (path.is_file() and relative in files)):
                raise ValueError('Foreign native custody metadata: ' + str(path))
            if path.is_file() and '/.bl/locks/' in relative:
                if path.stat().st_size:
                    raise ValueError('Modified native custody anchor: ' + str(path))
                stream = locks.enter_context(path.open('rb'))
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)


def retained_directory(destination, portable, sdk_directory, final, locks, *, native=False, products=None):
    """Keep genuine SDK files in place; fill only absent portable fixture files."""
    if destination.is_symlink() or not destination.is_dir():
        raise ValueError('Foreign runtime fixture directory: ' + str(destination))
    expected = tree_identity(portable)
    names = {name for name in expected if '/' not in name and name.endswith('.so')}
    for parent, dirs, files in os.walk(destination, followlinks=False):
        if native and Path(parent) == destination and '.bl' in dirs:
            native_custody(destination / '.bl', names, locks)
            dirs.remove('.bl')
        for name in dirs + files:
            path = Path(parent) / name
            relative = str(path.relative_to(destination))
            if relative not in expected:
                raise ValueError('Foreign runtime fixture path: ' + str(path))
            if expected[relative][0] == 'directory':
                if path.is_symlink() or not path.is_dir():
                    raise ValueError('Modified runtime fixture directory: ' + str(path))
                continue
            references = [portable / relative, sdk_directory / relative]
            if products is not None and relative in names:
                references.append(products / relative)
            if not matching_file(path, references, final / relative):
                raise ValueError('Modified or foreign runtime fixture: ' + str(path))
    missing = []
    for name, row in sorted(expected.items()):
        if native and (name == '.bl' or name.startswith('.bl/')):
            continue
        path = destination / name
        if not os.path.lexists(path):
            missing.append((path, row[0], final / name))
    return missing


def materialize(root, candidate, sdk):
    sdk, metadata, platform, descriptor, coordinator, expected = selection(sdk, candidate)
    root = Path(root)
    output = root / '.bl/ci-runtime'
    record = root / '.bl/ci-sdk.json'
    if os.path.lexists(output) and (output.is_symlink() or not output.is_dir() or not record.is_file()):
        raise ValueError('Refusing an unrecorded runtime fixture projection')
    output.parent.mkdir(parents=True, exist_ok=True)
    unpacker = immutable(descriptor['executor']) / 'bin/drop'
    with tempfile.TemporaryDirectory(prefix='.ci-runtime-', dir=output.parent) as temporary, \
            contextlib.ExitStack() as locks:
        staged = Path(temporary) / 'payload'
        # Always compare reruns to authenticated bytes, not a mutable receipt's
        # assertion that its own extracted files are still correct.
        subprocess.run([str(unpacker), 'unpack', str(candidate), '--dir', str(staged)], check=True)
        apps = sorted((staged / 'lib').glob('beam_lisp-*'))
        if len(apps) != 1:
            raise ValueError('Portable candidate must contain exactly one language application')
        app = apps[0]
        final_app = output / app.relative_to(staged)
        watched = ['priv/bootstrap/seed/manifest.term', 'priv/precompiled.term', 'priv/sdk-code.term']
        for name in watched:
            if (app / name).read_bytes() != (sdk / 'image' / name).read_bytes():
                raise ValueError('Portable packaging changed sealed compiler metadata: ' + name)
        receipt = {'version': 1, 'kind': 'ci-runtime-projection', 'sdk': str(sdk),
                   'sdk_descriptor_sha256': digest(sdk / 'artifact.json'), 'candidate_sha256': expected,
                   'image': str(final_app.relative_to(root)),
                   'metadata_sha256': {name: digest(app / name) for name in watched}}
        if record.exists() and (record.is_symlink() or json.loads(record.read_text()) != receipt):
            raise ValueError('Existing runtime projection receipt differs from the selected candidate')
        if output.exists() and tree_identity(output) != tree_identity(staged):
            raise ValueError('Existing extracted candidate files were modified')
        links = {'build': final_app / 'ebin', 'priv/native': final_app / 'priv/native',
                 'priv/z3': final_app / 'priv/z3', '.bl/lib': output / 'lib', '.bl/ci-image': final_app}
        publish, fill = [], []
        for name, target in links.items():
            destination = root / name
            if not os.path.lexists(destination):
                publish.append((destination, target))
            elif destination.is_symlink() and destination.resolve() == target.resolve():
                continue
            elif name in ('priv/native', 'priv/z3') and destination.is_dir() and not destination.is_symlink():
                fill += retained_directory(destination, app / name, sdk / 'image' / name, target, locks,
                                           native=name == 'priv/native',
                                           products=platform / 'native-products' if name == 'priv/native' else None)
            else:
                raise ValueError('Refusing to replace an existing fixture projection: ' + name)
        launcher = root / 'tooling/drop/target/release/drop-launcher'
        stock = immutable(descriptor['executor']) / 'bin/drop-launcher'
        if os.path.lexists(launcher) and not matching_file(launcher, [stock]):
            raise ValueError('Refusing to replace a modified or foreign stock launcher')
        # No existing fixture changes until every path has been checked. Retain
        # genuine Nix SDK natives/solver files and their custody inodes verbatim.
        if not output.exists():
            staged.rename(output)
        for destination, target in publish:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.symlink_to(os.path.relpath(target, destination.parent), target_is_directory=True)
        for path, kind, target in fill:
            if kind == 'directory':
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.symlink_to(os.path.relpath(target, path.parent))
        if not os.path.lexists(launcher):
            launcher.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(stock, launcher)
        if not record.exists():
            record.write_text(json.dumps(receipt, sort_keys=True) + '\n')
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
