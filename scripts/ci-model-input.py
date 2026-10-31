#!/usr/bin/env python3
"""Capture only the pinned embedding prerequisite, without an SDK build."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent
STORE = re.compile(r'/nix/store/[0-9a-z]{32}-[^/]+')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def pins(root=ROOT):
    source = (root / 'priv/build/embed-asset.bl').read_text()
    name = re.search(r'\(def dir-name "([A-Za-z0-9_-]+)"\)', source)
    block = re.search(r'\(def files\s+(\[\[.*?\]\])\)', source, re.S)
    if not name or not block:
        raise ValueError('Embedding prerequisite source has an unsupported pin declaration')
    pairs = re.findall(r'\["([A-Za-z0-9_.-]+)" "([0-9a-f]{64})"\]', block[1])
    remainder = re.sub(r'\["[A-Za-z0-9_.-]+" "[0-9a-f]{64}"\]', '', block[1])
    files = dict(pairs)
    if (remainder.strip('[] \n\t') or len(files) != len(pairs)
            or set(files) != {'config.json', 'model.safetensors', 'tokenizer.json'}):
        raise ValueError('Embedding prerequisite file inventory differs from its pinned source')
    identity = hashlib.sha256(json.dumps([name[1], files], sort_keys=True).encode()).hexdigest()
    return name[1], files, identity


def verify(models, root=ROOT):
    name, files, identity = pins(root)
    for filename, expected in files.items():
        if digest(models / name / filename) != expected:
            raise ValueError('Embedding prerequisite pin mismatch: ' + filename)
    if (models / name / 'DIGEST').read_text().strip() != files['model.safetensors']:
        raise ValueError('Embedding prerequisite DIGEST differs from the pinned weights')
    return identity


def register(cache, record):
    models = Path(record['path'])
    if not STORE.fullmatch(str(models)):
        raise ValueError('Models must be an immutable registered Nix input')
    subprocess.run(['nix-store', '--check-validity', str(models)], check=True)
    if record != {'version': 1, 'kind': 'ci-model-input', 'path': str(models),
                  'pins_sha256': verify(models)}:
        raise ValueError('Model cache hint differs from its immutable pinned bytes')
    cache.mkdir(parents=True, exist_ok=True)
    gc_root = cache / 'models-root'
    gc_root.unlink(missing_ok=True)
    subprocess.run(['nix-store', '--add-root', str(gc_root), '--indirect', '--realise', str(models)],
                   check=True, stdout=subprocess.DEVNULL)
    return record


def restore(cache):
    path = cache / 'models.json'
    return register(cache, json.loads(path.read_text())) if path.is_file() else None


def capture(models, cache):
    name, files, identity = pins()
    verify(models)
    retained = restore(cache)
    if retained:
        return retained
    with tempfile.TemporaryDirectory(prefix='bl-ci-pinned-models-') as temporary:
        snapshot = Path(temporary) / 'models'
        destination = snapshot / name
        destination.mkdir(parents=True)
        for filename in (*files, 'DIGEST', 'PROVENANCE'):
            shutil.copyfile(models / name / filename, destination / filename)
        # Check the copied bytes as well: a mutable download/cache is never
        # admitted just because it matched before copying.
        verify(snapshot)
        selected = subprocess.check_output(['nix-store', '--add', str(snapshot)], text=True).strip()
    record = register(cache, {'version': 1, 'kind': 'ci-model-input',
                              'path': selected, 'pins_sha256': identity})
    (cache / 'models.json').write_text(json.dumps(record, sort_keys=True) + '\n')
    return record


def selected_sdk(sdk):
    spec = importlib.util.spec_from_file_location('ci_model_sdk_cache', ROOT / 'scripts/ci-sdk-cache.py')
    sdk_cache = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sdk_cache)
    return Path(sdk_cache.describe_sdk(sdk)['sdk'])


def provision(sdk, models, cache):
    # Use the same genuine SDK selection as the inventory. Its Nix-linked
    # Elixir/OTP need neither the portable FHS loader nor PRoot's tracer.
    selected = selected_sdk(sdk)
    environment = dict(os.environ, BL_DAEMON='off', BEAM_LISP_MODEL_DIR=str(models))
    subprocess.run([str(selected / 'bin/bl'), '--cold', 'install', 'embed'],
                   env=environment, check=True, timeout=600)
    # Exit status alone is insufficient: an aborted launcher/tracer may return
    # zero without downloading anything. capture verifies all pins and DIGEST
    # before it can retain a model root or publish a model-ready cache hint.
    return capture(models, cache)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('provision', 'capture', 'restore', 'verify'))
    parser.add_argument('--models', type=Path)
    parser.add_argument('--sdk', type=Path, help='genuine selected SDK, required for provision')
    parser.add_argument('--cache', type=Path, default=Path.home() / '.cache/enchant-ci')
    args = parser.parse_args()
    if args.operation != 'restore' and not args.models:
        parser.error('An explicit --models root is required')
    if args.operation == 'provision' and not args.sdk:
        parser.error('provision requires --sdk')
    if args.operation == 'provision':
        record = provision(args.sdk, args.models.resolve(), args.cache.resolve())
    elif args.operation == 'capture':
        record = capture(args.models.resolve(), args.cache.resolve())
    elif args.operation == 'restore':
        record = restore(args.cache.resolve())
    else:
        models = args.models.resolve(strict=True)
        record = register(args.cache.resolve(), {'version': 1, 'kind': 'ci-model-input',
                           'path': str(models), 'pins_sha256': pins()[2]})
    print(json.dumps(record, sort_keys=True))


if __name__ == '__main__':
    main()
