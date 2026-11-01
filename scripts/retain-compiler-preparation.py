#!/usr/bin/env python3
"""Retain successful P input records across a later failed SDK qualification.

This is a cache hint, not a qualified compiler selection. The compiler producer
rechecks current inputs and every restored byte against its qualified baseline.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

STORE = re.compile(r'/nix/store/[0-9a-z]{32}-[^/]+')
TAG = re.compile(rb'COMPILER-PREPARATION-OUTPUT (/nix/store/[0-9a-z]{32}-[^\s"\\]+)')


def validate_stage(path):
    report = json.loads((path / 'result.json').read_text())
    stage = report.get('generation', {})
    if (report.get('kind') != 'artifact-generation-stage' or stage.get('generation') != 'P'
            or stage.get('produced') is not True or stage.get('fresh_boot_qualified') is not True
            or report.get('native_execution_admission') is not False or 'error' in report
            or not (path / 'unit-store').is_dir() or (path / 'unit-store').is_symlink()):
        raise ValueError('Not a completed preparation stage')
    actual = {}
    for item in sorted((path / 'P').iterdir()):
        if not item.is_file() or item.is_symlink():
            raise ValueError('Nonregular preparation artifact')
        actual[item.name] = hashlib.sha256(item.read_bytes()).hexdigest()
    if actual != stage.get('files') or not {'manifest.term', 'beam_lisp.app'} <= actual.keys():
        raise ValueError('Preparation bytes differ from its receipt')
    boot = json.loads((path / 'P.boot.log').read_text().splitlines()[-1])
    if boot.get('kind') != 'fresh-source-floor' or boot.get('status') != 'passed' or boot.get('seed') != str(path / 'P'):
        raise ValueError('Preparation fresh-boot receipt differs')
    return path


def candidates(job):
    remaining = 64 * 1024 * 1024
    seen = 0
    for directory, names, files in os.walk(job, followlinks=False):
        names[:] = sorted(name for name in names if not (Path(directory) / name).is_symlink())
        for name in sorted(files):
            path = Path(directory) / name
            seen += 1
            if seen > 256:
                return
            if path.is_symlink() or not path.is_file() or path.stat().st_size > min(remaining, 16 * 1024 * 1024):
                continue
            data = path.read_bytes()
            remaining -= len(data)
            for match in TAG.finditer(data):
                yield Path(match[1].decode())


def retain(candidate, root):
    if not STORE.fullmatch(str(candidate)) or candidate.resolve(strict=True) != candidate:
        raise ValueError('Preparation must be a top-level immutable store output')
    subprocess.run(['nix-store', '--check-validity', str(candidate)], check=True, timeout=30,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    validate_stage(candidate)
    root.mkdir(parents=True, exist_ok=True)
    target = root / 'previous-preparation'
    if target.is_symlink() and target.resolve(strict=True) == candidate:
        return
    # add-root registers the indirect root at its permanent pathname.
    subprocess.run(['nix-store', '--add-root', str(target), '--indirect', '--realise', str(candidate)],
                   check=True, timeout=30, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--job', type=Path)
    parser.add_argument('--candidate', type=Path)
    args = parser.parse_args()
    found = [args.candidate] if args.candidate else list(candidates(args.job))
    for candidate in reversed(found):
        try:
            retain(candidate, args.root)
            return 0
        except (OSError, ValueError, KeyError, subprocess.SubprocessError):
            continue
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
