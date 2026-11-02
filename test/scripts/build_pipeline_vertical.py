#!/usr/bin/env python3
"""Qualify the complete incremental pipeline through normal checkout preparation.

Run under a process-tree memory cap. All mutations are in a private engine;
preparation and products retain their ordinary durable owners and GC roots.
Requires a configured remote Nix builder and forbids local build execution.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--preparation', type=Path)
    parser.add_argument('--resume', action='store_true', help='resume retained products and evidence after a harness failure')
    args = parser.parse_args()
    previous = args.sdk.resolve(strict=True)
    output = args.out.resolve()
    engine = output / 'engine'
    if not args.resume:
        output.mkdir(parents=True, exist_ok=False)
        engine.mkdir()
        policy = json.loads((ROOT / 'nix/engine-inputs.json').read_text())
        for name in policy['roots']:
            source, target = ROOT / name, engine / name
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, target, ignore=shutil.ignore_patterns('target', '.git', '.bl', '__pycache__'))
            else:
                shutil.copy2(source, target)
        fixture = engine / 'priv/std/sdk/artifact'
        fixture.mkdir(parents=True, exist_ok=True)
        for name in ('provider.bl', 'consumer.bl'):
            shutil.copy2(ROOT / 'test/fixtures/sdk-artifacts' / name, fixture / name)
        retained = engine / '.bl/sdks'
        retained.mkdir(parents=True)
        (retained / 'current-sdk').symlink_to(previous)
        if args.preparation:
            (retained / 'previous-preparation').symlink_to(args.preparation.resolve(strict=True))
    retained = engine / '.bl/sdks'
    assert engine.is_dir() and retained.is_dir()
    metadata = json.loads((previous / 'artifact.json').read_text())
    env = dict(os.environ, BL_CHECKOUT_PLATFORM=metadata['platform'], BL_DAEMON='off',
               ELIXIR_ERL_OPTIONS='+S 4:4 +SDcpu 2:2 +SDio 1:1')
    settings = json.loads(subprocess.check_output(
        ['nix', '--extra-experimental-features', 'nix-command', 'config', 'show', '--json'], text=True))
    assert settings['max-jobs']['value'] == 0, 'qualification requires the normal remote-only builder policy'
    report = dict(version=1, status='running', revision=subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), stages=[], products={},
        placement={'local_max_jobs': 0, 'builders': settings['builders']['value']},
        scope='managed-checkout-sdk-and-ordinary-application-vertical-prototype')

    if args.resume:
        report = json.loads((output / 'result.json').read_text())
        report.setdefault('resumed_failures', []).append(dict(status=report['status'], error=report.pop('error', None)))
        report['status'] = 'running'

    def save():
        (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')

    def run(name, argv, cwd=engine, extra=None, timeout=3900):
        print(name, flush=True)
        stage = dict(name=name, argv=list(map(str, argv)), log=str(output / (str(len(report['stages'])) + '-' + name + '.log')), status='running')
        report['stages'].append(stage)
        save()
        started = time.monotonic()
        try:
            with Path(stage['log']).open('w') as stream:
                result = subprocess.run(stage['argv'], cwd=cwd, env={**env, **(extra or {})},
                                        stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
            stage['exit'] = result.returncode
            assert result.returncode == 0, Path(stage['log']).read_text(errors='replace')[-10000:]
            stage['status'] = 'passed'
            return Path(stage['log']).read_text()
        finally:
            stage['seconds'] = round(time.monotonic() - started, 3)
            save()

    def worker(name, sdk):
        info = json.loads((sdk / 'artifact.json').read_text())
        drv = subprocess.check_output(['nix-store', '--query', '--deriver', info['image']], text=True).strip()
        log = subprocess.check_output(['nix', '--extra-experimental-features', 'nix-command', 'log', drv],
                                      text=True, stderr=subprocess.STDOUT, timeout=60)
        (output / (name + '-worker.log')).write_text(log)
        counts = [json.loads(line.split('SDK-UNIT-PHASES ', 1)[1]) for line in log.splitlines()
                  if line.startswith('SDK-UNIT-PHASES ')][-1]
        parts = [json.loads(line.split('SDK-PARTS-RESULT ', 1)[1]) for line in log.splitlines()
                 if line.startswith('SDK-PARTS-RESULT ')]
        assert 1 < counts['jobs'] <= 4, counts
        assert counts['input-reads']['final'] < counts['input-reads']['references'], counts
        assert parts[-1]['parsed'] == 0 and parts[-1]['reused'] > 0, parts
        report['products'][name] = dict(sdk=str(sdk), derivation=drv, counts=counts, parts=parts)
        save()
        # The durable job's stdout events retain Nix's actual remote dispatch.
        # systemd journal holds service lifecycle; command output is in the ledger.
        source_jobs = list(retained.glob('*/job-*/operation.json'))
        matches = [p.parent for p in source_jobs
                   if (p.parent / 'retained').exists() and (p.parent / 'retained').resolve() == sdk]
        assert len(matches) == 1, matches
        handle = json.loads((matches[0] / 'handle.json').read_text())
        events = matches[0] / 'foundry-state/ledger/events' / (handle['id'] + '.jsonl')
        rows = [json.loads(line) for line in events.read_text().splitlines()]
        stdout = '\n'.join(row.get('text', '') for row in rows)
        (output / (name + '-placement.log')).write_text(stdout + '\n')
        dispatches = [line for line in stdout.splitlines() if 'building ' in line and ' on ' in line]
        assert any('ssh' in line for line in dispatches), 'actual remote dispatch absent from durable stdout events'
        report['products'][name]['remote_dispatches'] = dispatches
        save()
        return counts

    def receiver(name, sdk, real=None):
        info = json.loads((sdk / 'artifact.json').read_text())
        image = output / (name + '-source-free/lib/beam_lisp-0.1.0')
        shutil.copytree(sdk / 'image', image, symlinks=True)
        for path in [image, *image.rglob('*')]:
            if not path.is_symlink():
                path.chmod(path.stat().st_mode | 0o200)
                if path.is_file() and path.name.endswith(('.bl', '.bl.md', '.bl.org')):
                    path.unlink()
        extra = dict(BL_ROOT=str(image), BL_INCREMENTAL_BASE=str(sdk), BL_INCREMENTAL_IMAGE=str(image),
                     BL_INCREMENTAL_ANSWER='42', XDG_CACHE_HOME=str(output / (name + '-empty-cache')))
        if real is not None:
            extra['BL_INCREMENTAL_REAL_VALUE'] = str(real)
        text = run(name + '-source-free', [info['platform'] + '/bin/elixir',
            ROOT / 'test/scripts/incremental_sdk_receiver.exs'], cwd=image, extra=extra, timeout=300)
        assert 'INCREMENTAL-CONSUMER passed' in text

    def prepare(name):
        text = run(name, [engine / 'scripts/prepare-checkout-sdk'])
        sdk = Path(text.strip().splitlines()[-1]).resolve(strict=True)
        assert re.fullmatch(r'/nix/store/[0-9a-z]{32}-[^/]+', str(sdk))
        assert (retained / 'current-sdk').resolve() == sdk
        return sdk

    save()
    try:
        recorded = report['products'].get('producer-change')
        baseline = Path(recorded['sdk']) if recorded else prepare('producer-change')
        worker('producer-change', baseline)
        receiver('producer-change', baseline)
        # This changes existing SDK Source, not a comment or selection recipe.
        errors = engine / 'priv/std/errors.bl'
        definition = '(defn incremental-prototype-value [] 73)'
        if definition not in errors.read_text():
            with errors.open('a') as stream:
                stream.write('\n' + definition + '\n')
        changed = prepare('library-change')
        counts = worker('library-change', changed)
        assert 0 < counts['compiled'] < counts['cached'], counts
        before = json.loads((baseline / 'unit-store/unit-index.json').read_text())['units']
        after = json.loads((changed / 'unit-store/unit-index.json').read_text())['units']
        unchanged = [name for name in before.keys() & after.keys() if before[name] == after[name]]
        assert counts['cached'] == len(unchanged), (counts, len(unchanged))
        for name in unchanged:
            old = baseline / 'unit-store/.units' / name
            new = changed / 'unit-store/.units' / name
            assert {p.name: sha(p) for p in old.iterdir()} == {p.name: sha(p) for p in new.iterdir()}, name
        assert report['products']['library-change']['parts'][0]['reused'] > 0
        report['products']['library-change']['unchanged_units_byte_identical'] = len(unchanged)
        receiver('library-change', changed, 73)
        checks = ['build_pipeline_test.bl', 'build_pipeline_image_test.bl', 'build_namespace_sources_test.bl',
                  'build_cache_test.bl', 'build_scoped_ownership_test.bl', 'build_custody_regressions_test.bl',
                  'build_plan_test.bl', 'boot_build_barrier_test.bl', 'compiler_unit_store_test.bl',
                  'aot_reproducible_test.bl', 'aot_generated_class_inventory_test.bl']
        run('producer-controls', [engine / 'bin/bl', '--cold', 'test',
            *[ROOT / 'test/bl' / name for name in checks]],
            extra={'BL_TEST_SOURCE_ROOT': str(ROOT)}, timeout=900)
        project = output / 'application'
        (project / 'src').mkdir(parents=True)
        (project / 'env.bl').write_text('{:paths ["src"] :build {:paths ["src"] :jobs 2}}\n')
        (project / 'src/application.bl').write_text(
            '(ns vertical.application (:require [errors :as errors])) '
            '(defn answer [] (errors/incremental-prototype-value))\n')
        appout = output / 'application-build'
        run('application-build', [engine / 'bin/bl', '--cold', 'build', '--out', appout], cwd=project)
        product = (appout / '.nix-product').resolve(strict=True)
        assert json.loads((product / 'artifact.json').read_text())['sdk'] == str(changed)
        report['products']['application'] = str(product)
        jobs_before = set(retained.glob('*/job-*'))
        info = json.loads((changed / 'artifact.json').read_text())
        expected = sha(Path(info['release']) / 'bl.drop')
        warm = []
        with tempfile.TemporaryDirectory(prefix='bl-pipeline-warm-', dir='/run/user/' + str(os.getuid())) as runtime:
            extra = dict(XDG_RUNTIME_DIR=runtime)
            extra['BL_DAEMON'] = 'auto'
            try:
                for label in ('fresh-vm', 'warm-repeat'):
                    candidate = output / label
                    run(label, [engine / 'bin/bl', 'self-build', '--out', candidate], extra=extra, timeout=300)
                    assert sha(candidate) == expected
                    warm.append(report['stages'][-1]['seconds'])
            finally:
                run('stop-owned-realm', [engine / 'bin/bl', 'realm', 'stop'], extra=extra, timeout=60)
        assert jobs_before == set(retained.glob('*/job-*')), 'unchanged build created a new SDK job'
        report['unchanged'] = dict(fresh_vm_seconds=warm[0], warm_seconds=warm[1], new_sdk_jobs=0,
                                   candidate_sha256=expected)
        report['status'] = 'passed'
    except BaseException as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
