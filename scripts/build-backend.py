#!/usr/bin/env python3
"""Consume build.backend's generated Nix projection before an SDK exists.

This adapter never parses or evaluates .bl. The first-party codec owns that
compilation; its exact projection is checked again by the SDK qualification.
"""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import subprocess


def load(path):
    path = Path(path).resolve(strict=True)
    if path.suffix != '.bl':
        raise ValueError('Backend descriptions use .bl Source data')
    source = path.read_bytes()
    if len(source) > 1048576:
        raise ValueError('Backend description exceeds byte bound')
    projection = path.with_suffix('.nix')
    value = json.loads(subprocess.check_output([
        'nix-instantiate', '--eval', '--strict', '--json', str(projection),
        '--option', 'allow-import-from-derivation', 'false'], text=True, timeout=60))
    if set(value) != {'description', 'sourceSha256', 'clientConfig'} or value['sourceSha256'] != hashlib.sha256(source).hexdigest():
        raise ValueError('Stale backend projection; run scripts/compile-build-backends.bl')
    description = value['description']
    if set(description) - {'version', 'kind', 'nix', 'evaluation'} or description['version'] != 1:
        raise ValueError('Unsupported backend description')
    if description['kind'] not in ('local', 'configured', 'ssh', 'nixbuild'):
        raise ValueError('Unsupported backend kind')
    if not isinstance(value['clientConfig'], str) or '\0' in value['clientConfig']:
        raise ValueError('Invalid compiled Nix client configuration')
    if path.read_bytes() != source:
        raise ValueError('Backend description changed during evaluation')
    return description, value['clientConfig']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--description', type=Path, required=True)
    parser.add_argument('--config-out', type=Path)
    parser.add_argument('--github-output', type=Path)
    args = parser.parse_args()
    if args.github_output and not args.config_out:
        parser.error('--github-output requires --config-out')
    description, config = load(args.description)
    result = dict(backend=description['kind'], nixConfig=config)
    if args.config_out:
        args.config_out.write_text(config)
        args.config_out.chmod(0o600)
        result['configPath'] = str(args.config_out.resolve())
    if args.github_output:
        outputs = {'backend': result['backend'], 'config-path': result['configPath']}
        if description['kind'] == 'nixbuild':
            hosts = {item['hostName'] for item in description['nix']['buildMachines']}
            if len(hosts) != 1:
                raise ValueError('One nixbuild provider endpoint is required per description')
            outputs['nixbuild-host'] = next(iter(hosts))
        with args.github_output.open('a') as stream:
            for name, value in outputs.items():
                delimiter = secrets.token_hex(16)
                stream.write(f'{name}<<{delimiter}\n{value}\n{delimiter}\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
