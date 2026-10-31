#!/usr/bin/env python3
"""Test absent-row seed protection and corrupt-row refusal in an exact SDK copy.

One fresh bare child; no SDK lease is removed. Private helpers do not publish
code. Strict public replay attempts publication only in its disposable child;
a defective SDK may admit it. The indexed artifact is corrupted/restored before rechecking
all copied regular file bytes. Use one process-tree cap around this command.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import time


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--source-only', action='store_true', help='controlled Source receiver without an image index; no new SDK identity')
    parser.add_argument('--require-actual-protection', action='store_true', help='strict public Source-only publication replay; requires fixed actual Env')
    args = parser.parse_args()
    if args.require_actual_protection and not args.source_only:
        parser.error('strict actual publication currently requires --source-only')
    root, sdk, out = args.root.resolve(), args.sdk.resolve(), args.out.absolute()
    out.mkdir(parents=True, exist_ok=False)
    image = out / 'image'
    started = time.monotonic()
    shutil.copytree(sdk / 'image', image, symlinks=True)
    image.chmod(image.stat().st_mode | 0o200)
    files = {}
    for path in image.rglob('*'):
        if not path.is_symlink():
            if path.is_dir():
                path.chmod(path.stat().st_mode | 0o200)
            elif path.is_file():
                relative = str(path.relative_to(image))
                files[relative] = sha(path)
                assert files[relative] == sha(sdk / 'image' / relative)
                if path.suffix == '.beam':
                    path.chmod(path.stat().st_mode | 0o200)
    removed_index = None
    if args.source_only:
        index = image / 'priv/sdk-code.term'
        removed_index = sha(index)
        index.unlink()
        del files['priv/sdk-code.term']
    fixture = root / 'test/fixtures/sdk_prelease_publication_control.bl'
    descriptor = sdk / 'artifact.json'
    report = {'scope': 'private guards and optional strict public replay in a disposable SDK receiver; no parent VM code change',
              'sdk': str(sdk), 'descriptor_sha256': sha(descriptor), 'files': files,
              'fixture_sha256': sha(fixture), 'preparation_seconds': round(time.monotonic() - started, 3),
              'passed': False, 'source_only_component': args.source_only, 'strict_actual_publication': args.require_actual_protection, 'removed_image_index_sha256': removed_index}
    (out / 'inputs.json').write_text(json.dumps(report, indent=2) + '\n')
    boot = runpy.run_path(str(root / 'test/scripts/check_sdk_sealed_initialization.py'))['BOOT']
    (out / 'boot.exs').write_text(boot)
    platform = Path(json.loads(descriptor.read_text())['platform'])
    command = [str(platform / 'bin/elixir')]
    for dependency in sorted((sdk / 'lib').glob('*/ebin')):
        if not dependency.parent.name.startswith('beam_lisp-'):
            command += ['-pa', str(dependency)]
    command += ['-pa', str(image / 'ebin'), str(out / 'boot.exs'), str(fixture)]
    environment = {**os.environ, 'BL_ROOT': str(image), 'BL_DAEMON': 'off', 'BEAM_LISP_PATH': '',
                   'BL_TEST_SDK_PRELEASE_MUTABLE_ROOT': str(image / 'priv'),
                   'BL_TEST_SDK_PRELEASE_SOURCE_ONLY': 'yes' if args.source_only else 'no',
                   'BL_TEST_SDK_PRELEASE_REQUIRE_ACTUAL': 'yes' if args.require_actual_protection else 'no',
                   'XDG_CACHE_HOME': str(out / 'cache'),
                   'ELIXIR_ERL_OPTIONS': '+S 4:4 +SDcpu 2:2 +SDio 1:1',
                   'PATH': str(platform / 'bin') + ':' + os.environ['PATH']}
    started = time.monotonic()
    result = subprocess.run(command, cwd=image, env=environment, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
    (out / 'child.log').write_text(result.stdout)
    print(result.stdout, flush=True)
    report.update({'execution_seconds': round(time.monotonic() - started, 3), 'exit': result.returncode,
                   'all_copied_bytes_restored': all(sha(image / path) == digest for path, digest in files.items()),
                   'fixture_unchanged': sha(fixture) == report['fixture_sha256']})
    report['passed'] = (result.returncode == 0 and 'SDK_PRELEASE_PUBLICATION_CONTROL_READY' in result.stdout
                         and (':sdk-prelease-source-only' if args.source_only else ':sdk-prelease-image-corruption') in result.stdout
                         and report['all_copied_bytes_restored'] and report['fixture_unchanged'])
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    assert report['passed']
    print('SDK_PRELEASE_SOURCE_ONLY_CONTROLS_READY' if args.source_only else 'SDK_PRELEASE_IMAGE_CONTROLS_READY', flush=True)


if __name__ == '__main__':
    main()
