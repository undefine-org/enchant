#!/usr/bin/env python3
"""Qualify producer restoration in two serial, disposable VMs.

Run under a memory/time process-tree cap. No daemons or checkout preparation.
The SDK is immutable; all cache/source mutations belong to this probe.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    sdk = args.sdk.resolve(strict=True)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    capsule = out / 'capsule'
    writer = out / 'retain.bl'
    writer.write_text('''(ns producer.probe (:require [selfbuild]))
(BeamLisp/eval (File/read! (Path/join (System/fetch_env! "BL_TEST_SOURCE_ROOT") "scripts/retain-producer.bl")))
(BeamLisp.Ns.Rt/invoke (BeamLisp.Env/fetch_exact! "tooling.retain-producer" "retain!")
 (list (Path/join (System/fetch_env! "BL_SDK_PRODUCT") "unit-store")
       (Path/join (System/fetch_env! "BL_SDK_PRODUCT") "image")
       (System/fetch_env! "BL_TEST_PRODUCER_OUT")))
''')
    env = dict(os.environ, BL_DAEMON='off', BL_TEST_SOURCE_ROOT=str(ROOT), BL_TEST_PRODUCER_OUT=str(capsule),
               ELIXIR_ERL_OPTIONS='+S 2:2 +SDcpu 1:1 +SDio 1:1')
    def run(label, argv, **options):
        with (out / (label + '.log')).open('w') as stream:
            result = subprocess.run(list(map(str, argv)), stdout=stream, stderr=subprocess.STDOUT,
                                    env=env, timeout=600, **options)
        if result.returncode:
            print((out / (label + '.log')).read_text()[-12000:], flush=True)
            result.check_returncode()
    run('retain', [sdk / 'bin/bl', '--cold', 'run', writer])
    metadata = json.loads((sdk / 'artifact.json').read_text())
    image = out / 'lib/beam_lisp-0.1.0'
    image.mkdir(parents=True)
    shutil.copytree(sdk / 'image/priv', image / 'priv', symlinks=True,
                    ignore=shutil.ignore_patterns('sdk-code.term', 'precompiled.term', 'parts'))
    shutil.copytree(Path(metadata['compiler']) / 'seed', image / 'ebin')
    for path in image.rglob('*'):
        if path.is_dir() and not path.is_symlink():
            path.chmod(path.stat().st_mode | 0o700)
    platform = Path(metadata['platform'])
    argv = [platform / 'bin/elixir']
    for lib in sorted((sdk / 'lib').iterdir()):
        if not lib.name.startswith('beam_lisp-'):
            argv += ['-pa', lib / 'ebin']
    program = ROOT / 'test/scripts/retained_producer_cache.exs'
    argv += ['-pa', image / 'ebin', program]
    env.update(BL_ROOT=str(image), BL_EBIN=str(image / 'ebin'), BL_BIN=str(platform / 'bin/drop-launcher'),
               BL_ARTIFACT_PLATFORM=str(platform / 'artifact-platform'), BL_PREPARED_NATIVES=str(platform / 'native-products'),
               BL_PRODUCTION_CACHE=str(capsule), BL_PRODUCER_RESTORE=str(ROOT / 'scripts/restore-producer.exs'), BEAM_LISP_DEV='0')
    run('receive', argv, cwd=out)
    (out / 'result.json').write_text(json.dumps(dict(status='passed', sdk=str(sdk), checks=[
        'normal-launcher-zero-producer-compilation', 'qualified-floor-byte-identity',
        'changed-constructor-input-misses', 'forged-constructor-input-set-refused',
        'corrupt-complete-unit-refused', 'different-runtime-misses'])) + '\n')


if __name__ == '__main__':
    main()
