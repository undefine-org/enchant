#!/usr/bin/env python3
"""Qualify retained SDK production, ordinary applications and portable output.

Control-plane-only runs require identical immutable image/compiler/unit bytes.
Changed-native runs additionally recheck source-free use and producer controls,
and verify all unaffected units byte-for-byte. Run under a process-tree cap.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--changed-native', action='store_true')
    parser.add_argument('--value', type=int, default=73)
    args = parser.parse_args()
    prior = json.loads(args.evidence.read_text())
    for name in ('producer-controls', 'application-build', 'library-change-source-free'):
        assert any(stage['name'] == name and stage['status'] == 'passed' for stage in prior['stages']), name
    source = args.evidence.parent.resolve()
    engine = source / 'engine'
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=False)
    previous = Path(prior['products']['library-change']['sdk'])
    sdk = (engine / '.bl/sdks/current-sdk').resolve(strict=True)
    old = json.loads((previous / 'artifact.json').read_text())
    metadata = json.loads((sdk / 'artifact.json').read_text())
    fields = ('compiler', 'dependencies', 'target') if args.changed_native else ('image', 'compiler', 'dependencies', 'source', 'target', 'assemblyIdentity')
    for field in fields:
        assert old[field] == metadata[field], field
    unchanged_units = None
    if args.changed_native:
        before = json.loads((previous / 'unit-store/unit-index.json').read_text())['units']
        after = json.loads((sdk / 'unit-store/unit-index.json').read_text())['units']
        unchanged = [name for name in before.keys() & after.keys() if before[name] == after[name]]
        assert len(unchanged) >= 500
        for name in unchanged:
            a, b = [base / 'unit-store/.units' / name for base in (previous, sdk)]
            assert {p.name: sha(p) for p in a.iterdir()} == {p.name: sha(p) for p in b.iterdir()}, name
        unchanged_units = len(unchanged)
    else:
        assert sha(previous / 'unit-store/unit-index.json') == sha(sdk / 'unit-store/unit-index.json')
        assert sha(previous / 'bl') == sha(sdk / 'bl')
    assert 'release' not in metadata
    cache = output / 'cache'
    env = dict(os.environ, BL_CHECKOUT_PLATFORM=metadata['platform'], BL_DAEMON='off',
               XDG_CACHE_HOME=str(cache), ELIXIR_ERL_OPTIONS='+S 2:2 +SDcpu 1:1 +SDio 1:1')
    report = dict(status='running', revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  sdk=str(sdk), previous=str(previous), native_image=metadata['image'], compiler=metadata['compiler'],
                  native_proof=str(args.evidence.resolve()), native_bytes_unchanged=not args.changed_native, unchanged_units_byte_identical=unchanged_units, stages=[])
    def save():
        (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    def run(name, argv, cwd=engine, extra=None, timeout=900, machine=False):
        print(name, flush=True)
        record = dict(name=name, status='running', argv=list(map(str, argv)))
        report['stages'].append(record)
        save()
        started = time.monotonic()
        try:
            log = output / (name + '.log')
            with log.open('w') as stream:
                result = subprocess.run(record['argv'], cwd=cwd, env={**env, **(extra or {})}, timeout=timeout,
                                        stdout=subprocess.PIPE if machine else stream,
                                        stderr=stream if machine else subprocess.STDOUT, text=machine)
                if machine:
                    stream.write(result.stdout)
            assert result.returncode == 0, log.read_text(errors='replace')[-12000:]
            record['status'] = 'passed'
            return result.stdout if machine else log.read_text()
        except BaseException as error:
            record.update(status='failed', error=str(error))
            raise
        finally:
            record['seconds'] = round(time.monotonic() - started, 3)
            save()
    save()
    try:
        if args.changed_native:
            drv = run('native-deriver', ['nix-store', '--query', '--deriver', metadata['image']], machine=True).strip()
            log = run('native-worker', ['nix', '--extra-experimental-features', 'nix-command', 'log', drv], machine=True)
            counts = [json.loads(line.split('SDK-UNIT-PHASES ', 1)[1]) for line in log.splitlines()
                      if line.startswith('SDK-UNIT-PHASES ')][-1]
            assert counts['compiled'] == 9 and counts['cached'] == 504, counts
            report['native_counts'] = counts
            image = output / 'source-free/lib/beam_lisp-0.1.0'
            shutil.copytree(sdk / 'image', image, symlinks=True)
            for path in [image, *image.rglob('*')]:
                if not path.is_symlink():
                    path.chmod(path.stat().st_mode | 0o200)
                    if path.is_file() and path.name.endswith(('.bl', '.bl.md', '.bl.org')):
                        path.unlink()
            extra = dict(BL_ROOT=str(image), BL_INCREMENTAL_BASE=str(sdk), BL_INCREMENTAL_IMAGE=str(image),
                         BL_INCREMENTAL_ANSWER='42', BL_INCREMENTAL_REAL_VALUE=str(args.value))
            text = run('source-free-current-sdk', [metadata['platform'] + '/bin/elixir',
                       ROOT / 'test/scripts/incremental_sdk_receiver.exs'], cwd=image, extra=extra, timeout=300)
            assert 'INCREMENTAL-CONSUMER passed' in text
            checks = ['build_pipeline_test.bl', 'build_pipeline_image_test.bl', 'build_namespace_sources_test.bl',
                      'build_cache_test.bl', 'build_scoped_ownership_test.bl', 'build_custody_regressions_test.bl',
                      'build_plan_test.bl', 'boot_build_barrier_test.bl', 'compiler_unit_store_test.bl',
                      'aot_reproducible_test.bl', 'aot_generated_class_inventory_test.bl']
            run('current-producer-controls', [engine / 'bin/bl', '--cold', 'test',
                *[ROOT / 'test/bl' / name for name in checks]], extra={'BL_TEST_SOURCE_ROOT': str(ROOT)}, timeout=900)
        recipe = Path(metadata['platform']) / 'artifact-platform/nix/portable-artifact.nix'
        expression = f'let p = import {recipe} {{ sdk = {json.dumps(str(sdk))}; }}; in p.outPath'
        selected = json.loads(run('portable-selection', ['nix-instantiate', '--eval', '--strict', '--json', '--expr', expression,
                              '--option', 'allow-import-from-derivation', 'false', '--extra-experimental-features', 'nix-command flakes'], machine=True))
        release = Path(selected)
        assert not release.exists(), 'SDK selection eagerly realized portable packaging'
        report['portable_was_lazy'] = True
        candidate = output / 'first-portable'
        run('portable-first-request', [engine / 'bin/bl', '--cold', 'self-build', '--out', candidate])
        descriptor = json.loads((release / 'artifact.json').read_text())
        assert descriptor['image'] == metadata['image'] and descriptor['compiler'] == metadata['compiler']
        expected = sha(candidate)
        assert descriptor['sha256'] == sha(release / 'bl.drop') == expected
        report.update(release=str(release), candidate_sha256=expected)
        assert Path(run('ci-portable-lookup', ['python3', ROOT / 'scripts/sdk-release.py', '--sdk', sdk], machine=True).strip()) == release
        project = source / 'application'
        appout = output / 'application'
        run('application-new-selection', [engine / 'bin/bl', '--cold', 'build', '--out', appout], cwd=project)
        product = (appout / '.nix-product').resolve(strict=True)
        assert json.loads((product / 'artifact.json').read_text())['sdk'] == str(sdk)
        report['application'] = str(product)
        jobs = set((engine / '.bl/sdks').glob('*/job-*'))
        with tempfile.TemporaryDirectory(prefix='bl-retained-producer-', dir='/run/user/' + str(os.getuid())) as runtime:
            extra = dict(XDG_RUNTIME_DIR=runtime, BL_DAEMON='auto')
            try:
                for name in ('fresh-vm', 'warm-repeat'):
                    target = output / name
                    run(name, [engine / 'bin/bl', 'self-build', '--out', target], extra=extra, timeout=300)
                    assert sha(target) == expected
            finally:
                run('stop-owned-realm', [engine / 'bin/bl', 'realm', 'stop'], extra=extra, timeout=60)
        assert jobs == set((engine / '.bl/sdks').glob('*/job-*'))
        releases = list((cache / 'beam_lisp/artifacts').glob('portable-release-*/job/handle.json'))
        assert len(releases) == 1, 'unchanged publication submitted another portable production job'
        report.update(new_sdk_jobs_during_repeats=0, portable_jobs=1)
        run('portable-no-nix-store', ['nix-build', ROOT / 'test/nix/portable-runtime-control.nix', '--argstr', 'release', release,
                                    '--max-jobs', '0', '--out-link', output / 'fhs', '--extra-experimental-features', 'nix-command flakes'])
        assert json.loads((output / 'fhs/result.json').read_text()) == dict(passed=True, nixStoreVisible=False, answer=42, nativeJson=True)
        run('portable-ci-gates', ['nix-build', ROOT / 'nix/ci-sdk-gates.nix', '--argstr', 'sdk', sdk,
                                 '--max-jobs', '0', '--out-link', output / 'gates', '--extra-experimental-features', 'nix-command flakes'])
        report['status'] = 'passed'
    except BaseException as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
