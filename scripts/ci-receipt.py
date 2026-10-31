#!/usr/bin/env python3
"""Publish text-only CI receipts without retaining their build dependencies.

Nix scans output bytes for store references. Preserve content identities while
replacing physical store roots with opaque SHA-256 labels; the derivation also
enforces outputChecks.out.allowedReferences = [], rather than suppressing scanning.
"""
import argparse
import hashlib
from pathlib import Path
import re

STORE_ROOT = re.compile(r'/nix/store/[0-9a-z]{32}-[A-Za-z0-9+._?=~-]+')


def sanitize(text):
    return STORE_ROOT.sub(lambda match: 'nix-sha256:' + hashlib.sha256(
        match.group().encode()).hexdigest(), text)


def publish(source, destination):
    source, destination = Path(source), Path(destination)
    if destination.exists():
        raise ValueError('Receipt destination must be absent')
    destination.mkdir(parents=True)
    for path in sorted(source.rglob('*')):
        if path.is_symlink():
            raise ValueError('Receipts cannot export symlinks: ' + str(path))
        if path.is_dir():
            continue
        if not path.is_file() or path.suffix not in {'.json', '.jsonl', '.log', '.txt'}:
            raise ValueError('Receipts must contain only text records: ' + str(path))
        if path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError('Receipt exceeds the 64 MiB per-file limit')
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(sanitize(path.read_text(errors='replace')))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    publish(args.source, args.out)
