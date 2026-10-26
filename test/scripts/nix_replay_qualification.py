#!/usr/bin/env python3
"""Main-session qualification of a produced SDK's real replay CLI."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import uuid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--sdk', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
sdk = args.sdk.resolve(strict=True)
output = args.output.absolute()
output.mkdir(mode=0o700, parents=True, exist_ok=False)
source = output / 'source'
source.mkdir(mode=0o700)
marker = output / 'executed'
(source / 'pass_test.bl').write_text(
    '(ns replay.qualification.pass)\n(deftest pass '
    f'(File/write! {json.dumps(str(marker))} "ran") '
    '(is (= 42 (+ 40 2))))\n')
(source / 'fail_test.bl').write_text(
    '(ns replay.qualification.fail)\n(deftest fail (is (= 41 (+ 40 2))))\n')
(source / 'empty_test.bl').write_text('(ns replay.qualification.empty)\n')
(source / 'incoherent_test.bl').write_text(
    '(ns replay.qualification.incoherent)\n(deftest bad (is (= 1 (missing-replay-function 1))))\n')
metadata = json.loads((sdk / 'artifact.json').read_text())
platform = Path(metadata['platform']) / 'artifact-platform'
added = subprocess.run([str(platform / 'bin/nix'), 'build', '--impure', '--file',
                        str(platform / 'nix/project-snapshot.nix'), '--argstr', 'source', str(source),
                        '--argstr', 'rootsJson', '["."]', '--json', '--max-jobs', '0',
                        '--out-link', str(output / 'source-retained')],
                       text=True, capture_output=True, check=True)
rows = json.loads(added.stdout)
assert len(rows) == 1
frozen = Path(rows[0]['outputs']['out'])
assert os.readlink(output / 'source-retained') == str(frozen)
program_source = metadata['source']
report = {'sdk': str(sdk), 'testSource': str(frozen), 'stages': {}}


def run(label, argv, expected=0, cwd=frozen, extra_env=None):
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith(('BL_', 'BEAM_LISP_'))
                   and key not in ('ERL_LIBS', 'ERL_FLAGS', 'ERL_AFLAGS', 'ERL_ZFLAGS', 'ELIXIR_ERL_OPTIONS')}
    environment.update(ELIXIR_ERL_OPTIONS='+S 4:4 +SDcpu 2:2 +SDio 1:1')
    environment.update(extra_env or {})
    completed = subprocess.run([str(sdk / 'bin/bl'), '--cold', 'artifacts', *map(str, argv)],
                               cwd=cwd, env=environment, text=True, capture_output=True, timeout=180)
    (output / (label + '.stdout')).write_text(completed.stdout)
    (output / (label + '.stderr')).write_text(completed.stderr)
    report['stages'][label] = {'exit': completed.returncode}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    if completed.returncode != expected:
        raise AssertionError(f'{label}: exit {completed.returncode}, expected {expected}: '
                             + completed.stdout[-4000:] + completed.stderr[-4000:])
    return completed


def capture(label, filename):
    options = output / (label + '-options.json')
    capsule = output / (label + '-capsule.json')
    options.write_text(json.dumps({'product': str(sdk), 'source': program_source,
                                  'test-source': str(frozen), 'tests': [filename],
                                  'tool-names': ['nix-store']}))
    run(label + '-capture', ['replay-capture', options, capsule])
    record = json.loads(capsule.read_text())
    assert record['capsule']['identities']['sdk'] == str(sdk)
    assert capsule.stat().st_mode & 0o077 == 0
    return capsule


try:
    positive = capture('pass', 'pass_test.bl')
    run('pass-plan', ['replay-plan', positive])
    result_path = output / 'pass-result.json'
    run('pass-run', ['replay', positive, result_path])
    result = json.loads(result_path.read_text())
    assert result['status'] == 'passed' and result['aggregate']['tests'] == 1
    assert result['capsule']['qualification']['scope'] == 'selected-tests-only'
    assert result['capsule']['qualification']['status'] == 'passed'
    assert marker.read_text() == 'ran'
    marker.unlink()
    for label, filename, expected_status in [
        ('fail', 'fail_test.bl', 'failed'), ('empty', 'empty_test.bl', 'incomplete'),
        ('incoherent', 'incoherent_test.bl', 'failed')]:
        capsule = capture(label, filename)
        result_path = output / (label + '-result.json')
        run(label + '-run', ['replay', capsule, result_path], expected=1)
        result = json.loads(result_path.read_text())
        assert result['status'] == expected_status
        assert result['capsule']['qualification']['status'] != 'passed'
    wrapper = json.loads(positive.read_text())
    forged = output / 'forged.json'
    wrapper['capsule']['argv'] = ['eval', '(println "must not execute")']
    forged.write_text(json.dumps(wrapper))
    run('forged-plan', ['replay-plan', forged], expected=1)
    duplicated = output / 'duplicate.json'
    original = json.loads(positive.read_text())
    duplicated.write_text('{"capsule":' + json.dumps(original['capsule'])
                          + ',"capsule":{},"custody":' + json.dumps(original['custody']) + '}')
    run('duplicate-plan', ['replay-plan', duplicated], expected=1)
    mutable = output / 'mutable-project'
    mutable.mkdir()
    (mutable / 'env.bl').write_text('{:name "mutable-replay-caller" :paths ["."]}\n')
    run('mutable-caller', ['replay', positive, output / 'mutable-result.json'], expected=1, cwd=mutable)
    assert not (output / 'mutable-result.json').exists() and not marker.exists()
    report['status'] = 'passed'
    print(json.dumps({'status': 'passed', 'report': str(output / 'report.json')}))
except BaseException as error:
    report.update(status='failed', error=repr(error))
    raise
finally:
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
