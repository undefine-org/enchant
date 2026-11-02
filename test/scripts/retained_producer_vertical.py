#!/usr/bin/env python3
"""Finish the real vertical slice after a control-plane-only recipe change.

Reuses recorded native SDK/application controls only when the immutable native
image, compiler and units remain identical. All subsequent checks use the new
selection through normal commands. Run under a process-tree cap.
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
    for field in ('image', 'compiler', 'dependencies', 'source', 'target', 'assemblyIdentity'):
        assert old[field] == metadata[field], field
    assert sha(previous / 'unit-store/unit-index.json') == sha(sdk / 'unit-store/unit-index.json')
    assert sha(previous / 'bl') == sha(sdk / 'bl')
    assert 'release' not in metadata
    cache = output / 'cache'
    env = dict(os.environ, BL_CHECKOUT_PLATFORM=metadata['platform'], BL_DAEMON='off',
               XDG_CACHE_HOME=str(cache), ELIXIR_ERL_OPTIONS='+S 2:2 +SDcpu 1:1 +SDio 1:1')
    report = dict(status='running', revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  sdk=str(sdk), previous=str(previous), native_image=metadata['image'], compiler=metadata['compiler'],
                  native_proof=str(args.evidence.resolve()), native_bytes_unchanged=True, stages=[])
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
        finally:
            record['seconds'] = round(time.monotonic() - started, 3)
            save()
    save()
    try:
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
