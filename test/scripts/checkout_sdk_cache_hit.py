#!/usr/bin/env python3
"""Qualify restored SDK hits and changed-source refusal without starting a VM."""
import argparse
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--sdk', type=Path, required=True)
parser.add_argument('--engine', type=Path, required=True)
args = parser.parse_args()
engine = args.engine.resolve(strict=True)
sdk = args.sdk.resolve(strict=True)
with tempfile.TemporaryDirectory(prefix='bl-sdk-cache-hit-') as temporary:
    root = Path(temporary) / 'tree'
    shutil.copytree(engine, root)
    for path in [root, *root.rglob('*')]:
        path.chmod(path.stat().st_mode | 0o200)
    tools = Path(temporary) / 'tools'
    tools.mkdir()
    for name in ('nix-build', 'systemd-run'):
        tool = tools / name
        tool.write_text('#!/bin/sh\necho "unexpected producer: $0" >&2\nexit 99\n')
        tool.chmod(0o755)
    env = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ['PATH'])
    wrapper = root / 'scripts/prepare-checkout-sdk'
    wrapper.chmod(0o755)
    loader = importlib.machinery.SourceFileLoader('cache_hit_inputs', str(root / 'scripts/sdk-inputs'))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    policy = json.loads((root / 'nix/engine-inputs.json').read_text())

    def retain():
        fingerprint = module.fingerprint(root, policy)
        directory = root / '.bl/sdks' / fingerprint
        directory.mkdir(parents=True)
        (directory / 'result-sdk').symlink_to(sdk, target_is_directory=True)
        (directory / 'source-engine').symlink_to(engine, target_is_directory=True)
        return fingerprint, directory

    fingerprint, directory = retain()
    result = subprocess.run([str(wrapper), '--selection'], env=env, text=True,
                            capture_output=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(sdk) + ' ' + fingerprint, result.stdout
    assert (root / '.bl/sdks/current-sdk').resolve() == sdk
    assert not list(directory.glob('job-*')), 'cache hit created a producer job'
    # Only the private fixture changes; the actual immutable SDK stays intact.
    source = root / 'priv/std/errors.bl'
    source.write_text(source.read_text() + '\n; changed engine input\n')
    changed, directory = retain()
    assert changed != fingerprint
    result = subprocess.run([str(wrapper)], env=env, text=True,
                            capture_output=True, timeout=60)
    assert result.returncode == 69, (result.returncode, result.stderr)
    assert 'engine bytes differ' in result.stderr, result.stderr
    assert not list(directory.glob('job-*')), 'invalid selection started production'
print(json.dumps({'status': 'passed', 'sdk': str(sdk), 'cache_hit_jobs': 0,
                  'changed_source': 'refused', 'VMs_started': 0}))
