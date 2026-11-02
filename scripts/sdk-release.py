#!/usr/bin/env python3
"""Locate and verify an already produced portable product of an exact SDK.

This never starts production. CI declares the portable product separately;
normal users produce it with the public self-build command.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

STORE = re.compile(r'/nix/store/[0-9a-z]{32}-[^/]+\Z')


def immutable(value):
    path = Path(value).resolve(strict=True)
    if not STORE.fullmatch(str(path)) or not path.is_dir():
        raise ValueError('Expected an immutable store product')
    return path


def release(sdk):
    sdk = immutable(sdk)
    selected = json.loads((sdk / 'artifact.json').read_text())
    if (selected['version'], selected['kind'], selected['target']) != (1, 'sdk', 'x86_64-linux'):
        raise ValueError('Unsupported SDK selection')
    if 'release' in selected:
        output = immutable(selected['release'])
    elif os.environ.get('CI_CHECK_RELEASE'):
        # The bounded CI derivation supplies this exact declared input. Its
        # guest has no Nix daemon and must not evaluate or produce a package.
        output = immutable(os.environ['CI_CHECK_RELEASE'])
    else:
        platform = immutable(selected['platform'])
        recipes = immutable(json.loads((platform / 'platform.json').read_text())['recipes'])
        expression = ('let product = import ' + str(recipes / 'nix/portable-artifact.nix') +
                      ' { sdk = ' + json.dumps(str(sdk)) + '; }; in product.outPath')
        output = immutable(json.loads(subprocess.check_output([
            'nix-instantiate', '--eval', '--strict', '--json', '--expr', expression,
            '--option', 'allow-import-from-derivation', 'false',
            '--extra-experimental-features', 'nix-command flakes'], text=True, timeout=90)))
    descriptor = json.loads((output / 'artifact.json').read_text())
    if (descriptor['version'], descriptor['kind'], descriptor['target'], descriptor['file'], descriptor['compiler']) != (
            1, 'release', selected['target'], 'bl.drop', selected['compiler']):
        raise ValueError('SDK/portable product identity differs')
    if 'release' not in selected and descriptor.get('image') != selected['image']:
        raise ValueError('Portable product belongs to another native image')
    with (output / 'bl.drop').open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != descriptor['sha256']:
            raise ValueError('Portable product bytes differ')
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', required=True, type=Path)
    parser.add_argument('--copy-to', type=Path)
    args = parser.parse_args()
    output = release(args.sdk)
    if args.copy_to:
        shutil.copyfile(output / 'bl.drop', args.copy_to)
        args.copy_to.chmod(0o755)
    else:
        print(output)


if __name__ == '__main__':
    main()
