#!/usr/bin/env python3
"""Exercise incremental SDK edits through the complete production Nix recipe.

Use a baseline built from the current producer. Run under a process-tree cap.
Every edit lives in a private engine tree; all products remain GC rooted.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
PROVIDER = 'priv/std/sdk/artifact/provider.bl'
UNRELATED = 'priv/std/sdk/artifact/unrelated.bl'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    sdk = args.sdk.resolve(strict=True)
    metadata = json.loads((sdk / 'artifact.json').read_text())
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = out / 'source'
    source.mkdir()
    policy = json.loads((ROOT / 'nix/engine-inputs.json').read_text())
    for relative in policy['roots']:
        origin, target = ROOT / relative, source / relative
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if origin.is_dir():
            shutil.copytree(origin, target, ignore=shutil.ignore_patterns('target', '.git', '.bl', '__pycache__'))
        else:
            shutil.copy2(origin, target)
    report = dict(status='running', sdk=str(sdk), scope='complete-production-sdk', stages=[])

    def save():
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')

    def command(name, argv, env=None, cwd=None):
        started = time.monotonic()
        log = out / (name + '.log')
        print(name, flush=True)
        with log.open('w') as stream:
            done = subprocess.run(list(map(str, argv)), env=env, cwd=cwd, stdout=stream,
                                  stderr=subprocess.STDOUT, timeout=3600)
        report['stages'].append(dict(name=name, seconds=round(time.monotonic() - started, 3),
                                     exit=done.returncode, log=str(log)))
        save()
        if done.returncode:
            raise RuntimeError(log.read_text()[-6000:])
        return log.read_text()

    def hashes(directory):
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir() if p.is_file()}

    def receiver(name, product, answer, real_value=None):
        info = json.loads((product / 'artifact.json').read_text())
        image = out / (name + '-receiver/lib/beam_lisp-0.1.0')
        shutil.copytree(product / 'image', image, symlinks=True)
        for path in [image, *image.rglob('*')]:
            if not path.is_symlink():
                path.chmod(path.stat().st_mode | 0o200)
                if path.is_file() and path.name.endswith(('.bl', '.bl.md', '.bl.org')):
                    path.unlink()
        env = dict(os.environ, BL_ROOT=str(image), BL_INCREMENTAL_BASE=str(product),
                   BL_INCREMENTAL_IMAGE=str(image), BL_INCREMENTAL_ANSWER=str(answer), BL_DAEMON='off',
                   XDG_CACHE_HOME=str(out / (name + '-empty-cache')),
                   ELIXIR_ERL_OPTIONS='+S 4:4 +SDcpu 2:2 +SDio 1:1')
        if real_value is not None:
            env['BL_INCREMENTAL_REAL_VALUE'] = str(real_value)
        text = command(name + '-consumer', [info['platform'] + '/bin/elixir',
                       ROOT / 'test/scripts/incremental_sdk_receiver.exs'], env, image)
        assert 'INCREMENTAL-CONSUMER passed' in text

    def build(name, previous, expected, answer, real_value=None):
        pointer = out / name
        command(name + '-capture', ['nix-build', ROOT / 'nix/sdk-source.nix', '--argstr', 'source', source,
                '--out-link', out / (name + '-source'), '--max-jobs', '0', '--option',
                'experimental-features', 'nix-command flakes'])
        engine = (out / (name + '-source')).resolve(strict=True)
        command(name, ['nix-build', ROOT / 'nix/sdk-artifact.nix', '--argstr', 'source', engine,
                '--argstr', 'previous', previous, '--out-link', pointer, '--max-jobs', '0',
                '--option', 'timeout', '3300', '--option', 'experimental-features', 'nix-command flakes'])
        product = pointer.resolve(strict=True)
        info = json.loads((product / 'artifact.json').read_text())
        assert {key: info[key] for key in ('compiler', 'dependencies')} == {
            key: metadata[key] for key in ('compiler', 'dependencies')}, info
        prior = json.loads((previous / 'artifact.json').read_text())
        if info['image'] == prior['image']:
            # Reusing the actual producer output performs no assembly. Its old
            # build log describes that earlier build, not this selection.
            assert expected in (-1, 0), (name, expected)
            for key in ('assemblyIdentity', 'release', 'source', 'compiler', 'dependencies'):
                assert info[key] == prior[key], key
            assert (product / 'unit-store').resolve(strict=True) == (previous / 'unit-store').resolve(strict=True)
            report['stages'][-1].update(product=str(product), assembly_reused=True)
            save()
            if answer is not None:
                receiver(name, product, answer, real_value)
            return product
        drv = subprocess.check_output(['nix-store', '--query', '--deriver', info['image']], text=True).strip()
        log = subprocess.check_output(['nix', '--extra-experimental-features', 'nix-command', 'log', drv],
                                      text=True, stderr=subprocess.STDOUT, timeout=30)
        (out / (name + '-worker.log')).write_text(log)
        metrics = [json.loads(line.split('SDK-UNIT-RESULT ', 1)[1]) for line in log.splitlines()
                   if line.startswith('SDK-UNIT-RESULT ')][-1]
        stage = report['stages'][-1]
        stage.update(product=str(product), counts=metrics, derivation=drv)
        if expected == -1:
            pass
        elif expected is not None:
            assert metrics['compiled'] == expected, metrics
        else:
            assert 1 <= metrics['compiled'] < metrics['cached'], metrics
        before = json.loads((previous / 'unit-store/unit-index.json').read_text())['units']
        after = json.loads((product / 'unit-store/unit-index.json').read_text())['units']
        unchanged = [ns for ns in before.keys() & after.keys() if before[ns] == after[ns]]
        assert metrics['cached'] == len(unchanged), (metrics, len(unchanged))
        for ns in unchanged:
            assert hashes(previous / 'unit-store/.units' / ns) == hashes(product / 'unit-store/.units' / ns), ns
        stage['unchanged_units_byte_identical'] = len(unchanged)
        save()
        if answer is not None:
            receiver(name, product, answer, real_value)
        return product

    try:
        # Recipe/client edits made while the baseline was qualifying may
        # update a few library units. Establish the exact current producer.
        synchronized = build('synchronized', sdk, -1, None)
        recipe = source / 'nix/artifact-selection.nix'
        original_recipe = recipe.read_bytes()
        recipe.write_bytes(original_recipe + b'\n# Provider-only selection control.\n')
        try:
            selected = build('provider-only', synchronized, 0, None)
            before = json.loads((synchronized / 'artifact.json').read_text())
            after = json.loads((selected / 'artifact.json').read_text())
            assert after['image'] == before['image']
            for key in ('coordinator', 'platform'):
                assert after[key] != before[key], key
            expression = '''let
              root = builtins.toPath %s;
              lock = builtins.fromJSON (builtins.readFile (root + "/flake.lock"));
              pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
            in map (sdk: (import (root + "/nix/sdk-worker-filesystem.nix") {
              inherit pkgs; sdk = builtins.storePath sdk;
            }).outPath) [ %s %s ]''' % (json.dumps(str(source)), json.dumps(str(synchronized)), json.dumps(str(selected)))
            filesystems = json.loads(command('provider-filesystem-identity', ['nix-instantiate',
                '--eval', '--strict', '--json', '--expr', expression,
                '--option', 'experimental-features', 'nix-command flakes']).strip())
            assert len(set(filesystems)) == 1, filesystems
        finally:
            recipe.write_bytes(original_recipe)
        fixture = ROOT / 'test/fixtures/sdk-artifacts'
        for name in ('provider.bl', 'consumer.bl'):
            target = source / 'priv/std/sdk/artifact' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(fixture / name, target)
        (source / UNRELATED).write_text('(ns sdk.artifact.unrelated) (defn answer [] 7)\n')
        first = build('added', synchronized, 3, 42)
        (source / PROVIDER).write_text('(ns sdk.artifact.provider) (def base 50) (defmacro forty [] base)\n')
        macro = build('macro-edit', first, 2, 52)
        with (source / 'priv/std/errors.bl').open('a') as stream:
            stream.write('\n(defn incremental-prototype-value [] 73)\n')
        real = build('real-library-edit', macro, None, 52, 73)
        (source / UNRELATED).unlink()
        deleted = build('deleted', real, 0, 52, 73)
        units = json.loads((deleted / 'unit-store/unit-index.json').read_text())['units']
        assert 'sdk.artifact.unrelated' not in units
        assert not (deleted / 'unit-store/.units/sdk.artifact.unrelated').exists()
        assert not (deleted / 'image/ebin/Elixir.BeamLisp.Ns.Sdk.Artifact.Unrelated.beam').exists()
        managed_root = source / '.bl/sdks'
        managed_root.mkdir(parents=True)
        (managed_root / 'current-sdk').symlink_to(deleted, target_is_directory=True)
        info = json.loads((deleted / 'artifact.json').read_text())
        env = dict(os.environ, BL_CHECKOUT_PLATFORM=info['platform'], BL_DAEMON='off',
                   PATH=info['platform'] + '/bin:' + os.environ.get('PATH', ''),
                   ELIXIR_ERL_OPTIONS='+S 4:4 +SDcpu 2:2 +SDio 1:1')
        managed = Path(command('managed-prepare', [source / 'scripts/prepare-checkout-sdk'], env, source).strip().splitlines()[-1])
        assert managed.is_dir()
        assert (managed_root / 'current-sdk').resolve(strict=True) == managed
        jobs = list(managed_root.glob('*/job-*/operation.json'))
        assert len(jobs) == 1
        assert json.loads(jobs[0].read_text())['previous'] == str(deleted)
        drv = subprocess.check_output(['nix-store', '--query', '--deriver',
            json.loads((managed / 'artifact.json').read_text())['image']], text=True).strip()
        log = subprocess.check_output(['nix', '--extra-experimental-features', 'nix-command', 'log', drv],
                                      text=True, stderr=subprocess.STDOUT, timeout=30)
        (out / 'managed-worker.log').write_text(log)
        counts = [json.loads(line.split('SDK-UNIT-RESULT ', 1)[1]) for line in log.splitlines()
                  if line.startswith('SDK-UNIT-RESULT ')][-1]
        assert counts['compiled'] == 0 and counts['cached'] == len(units), counts
        assert command('managed-repeat', [source / 'scripts/prepare-checkout-sdk'], env, source).strip() == str(managed)
        expression = '(ns cutover.managed (:require [sdk.artifact.provider :as p] [errors :as e])) (assert (= 52 (+ 2 (p/forty)))) (assert (= 73 (e/incremental-prototype-value))) (println "MANAGED-INCREMENTAL passed")'
        assert 'MANAGED-INCREMENTAL passed' in command('managed-checkout-cli',
            [source / 'bin/bl', '--cold', 'eval', expression], env, source)
        report['managed'] = dict(sdk=str(managed), counts=counts, previous=str(deleted))
        report['status'] = 'passed'
    except BaseException as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
