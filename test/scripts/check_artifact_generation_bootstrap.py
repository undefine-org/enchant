#!/usr/bin/env python3
"""Bounded component control of genuine previous-generation producer bootstrap.

Run under one process-tree memory/time cap. This executes three serial fresh
private compiler receivers, never emits or selects a compiler/SDK product.
The SDK supplies dependencies/platform only; the compiler is the recorded seed.
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    root, sdk, out = args.root.resolve(), args.sdk.resolve(), args.out.absolute()
    out.mkdir(parents=True, exist_ok=False)
    product = json.loads((sdk / 'artifact.json').read_text())
    platform = Path(product['platform'])
    deps = [p for p in sorted((sdk / 'lib').glob('*/ebin'))
            if not p.parent.name.startswith('beam_lisp-')]
    old_boot = runpy.run_path(str(root / 'scripts/demo-artifact-production'))['BOOT']
    new_boot = runpy.run_path(str(root / 'scripts/qualify-artifact-generation'))['PRODUCER_BOOT']
    seed = root / 'priv/bootstrap/seed'
    hashes = lambda directory: {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in sorted(directory.iterdir()) if p.is_file()}
    seed_before = hashes(seed)
    report = {'scope': 'private predecessor bootstrap component; no produced SDK',
              'seed_files': seed_before, 'receivers': [], 'passed': False}
    try:
        for mode in ('old-direct', 'authenticated-predecessor', 'corrupt-predecessor'):
            started = time.monotonic()
            image = out / mode
            shutil.copytree(root / 'priv', image / 'priv', symlinks=True)
            shutil.copy2(root / 'env.bl', image / 'env.bl')
            # A real Source edit rotates compiler identity even if the checkout
            # happens to match its seed. No manifest, cache or key is rewritten.
            with (image / 'priv/host/aot.bl').open('a') as stream:
                stream.write('\n; private predecessor-bootstrap Source transition control\n')
            app = image / '.bl/lib/beam_lisp-0.1.0'
            app.mkdir(parents=True)
            (app / 'priv').symlink_to(image / 'priv')
            shutil.copytree(seed, app / 'ebin')
            assert seed_before == hashes(image / 'priv/bootstrap/seed') == hashes(app / 'ebin')
            (image / 'driver.bl').write_text('(println :producer-bootstrap-driver-reached)\n')
            (image / 'boot.exs').write_text(old_boot if mode == 'old-direct' else new_boot)
            victim = image / 'priv/bootstrap/seed/Elixir.BeamLisp.CompilerData.beam'
            original = victim.read_bytes()
            if mode == 'corrupt-predecessor':
                victim.write_bytes(b'corrupt actual predecessor bytes')
            command = [str(platform / 'bin/elixir')]
            for dep in deps:
                command += ['-pa', str(dep)]
            command += ['-pa', str(app / 'ebin'), str(image / 'boot.exs')]
            env = {**os.environ, 'BL_ROOT': str(image), 'BL_DAEMON': 'off',
                   'BEAM_LISP_PATH': '', 'BL_ARTIFACT_DRIVER': str(image / 'driver.bl'),
                   'BL_GENERATION_BOOTSTRAP_RECEIPT': str(image / 'bootstrap.json'),
                   'XDG_CACHE_HOME': str(image / 'cache'),
                   'ELIXIR_ERL_OPTIONS': '+S 4:4 +SDcpu 2:2 +SDio 1:1',
                   'PATH': str(platform / 'bin') + ':' + os.environ['PATH']}
            preparation = round(time.monotonic() - started, 3)
            started = time.monotonic()
            try:
                result = subprocess.run(command, cwd=image, env=env, text=True,
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=90)
            finally:
                victim.write_bytes(original)
            (image / 'run.log').write_text(result.stdout)
            row = {'mode': mode, 'preparation_seconds': preparation,
                   'execution_seconds': round(time.monotonic() - started, 3),
                   'exit': result.returncode,
                   'driver_reached': ':producer-bootstrap-driver-reached' in result.stdout}
            report['receivers'].append(row)
            print(json.dumps(row), flush=True)
            if mode == 'authenticated-predecessor':
                assert result.returncode == 0 and row['driver_reached'], result.stdout
                receipt = json.loads((image / 'bootstrap.json').read_text())
                assert receipt['installation'] == 'previous-generation'
                assert receipt['seed_compiler_key'] != receipt['input_compiler_key']
                assert receipt['stable_predecessor_unchanged'] is True
                row['bootstrap'] = receipt
            else:
                assert result.returncode != 0 and not row['driver_reached'], result.stdout
                if mode == 'old-direct':
                    assert 'undefined var: compiler/list' in result.stdout, result.stdout
                else:
                    assert 'checksum mismatch' in result.stdout, result.stdout
                    assert not (image / 'bootstrap.json').exists()
            assert seed_before == hashes(image / 'priv/bootstrap/seed') == hashes(app / 'ebin')
        report['passed'] = True
    finally:
        report['original_seed_unchanged'] = hashes(seed) == seed_before
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    assert report['original_seed_unchanged']


if __name__ == '__main__':
    main()
