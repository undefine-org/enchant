#!/usr/bin/env python3
"""Use the existing exact historical-selector executor on the selected SDK.

The source-component gate remains scripts/check-execution-history. This adapter
binds its existing manifest, runner and validators to an immutable SDK receiver;
it does not replace runtime modules or infer case closure from a replay.
Run under the shared BL lock and a whole-process-tree memory/time cap.
"""
import argparse
import json
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
HISTORY = runpy.run_path(str(ROOT / 'scripts/check-execution-history'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=1800)
    parser.add_argument('--cases', nargs='+')
    args = parser.parse_args()
    sdk, out = args.sdk.resolve(), args.out.absolute()
    if os.path.lexists(out):
        parser.error('output must be absent; preserve earlier receipts')
    selected = subprocess.check_output([str(ROOT / 'scripts/prepare-checkout-sdk'), '--selection'],
                                       cwd=ROOT, text=True).strip().split()
    if len(selected) != 2 or Path(selected[0]).resolve() != sdk:
        parser.error('SDK must be the current normal backend selection')
    metadata = json.loads((sdk / 'artifact.json').read_text())
    if metadata.get('version') != 1 or metadata.get('kind') != 'sdk':
        parser.error('invalid SDK selection')
    image = (sdk / 'image').resolve(strict=True)
    manifest = ROOT / HISTORY['MANIFEST']
    cases = HISTORY['read_manifest'](ROOT, manifest)
    by_id = {case['id']: case for case in cases}
    ids = args.cases or list(by_id)
    if not ids or len(ids) != len(set(ids)) or any(key not in by_id for key in ids):
        parser.error('select distinct known case IDs')
    chosen = [by_id[key] for key in ids]
    if any(not case['selectors'] for case in chosen):
        parser.error('selected case has no executable selector')
    groups = {}
    for case in chosen:
        for selector in case['selectors']:
            entry = {key: selector[key] for key in ['namespace', 'test']}
            group = groups.setdefault(selector['path'], [])
            if entry not in group:
                group.append(entry)
    plan = [{'path': path, 'selectors': selectors} for path, selectors in groups.items()]
    runpy.run_path(str(ROOT / 'scripts/test_prerequisites.py'))['require'](ROOT, list(groups))
    solver = image / 'priv/z3/bin/z3'
    if not solver.is_file():
        parser.error('selected SDK solver is absent')
    # The child and native standalone controls must resolve this exact tool.
    os.environ['BEAM_LISP_Z3'] = str(solver)

    def capture():
        frozen = HISTORY['capture'](ROOT, manifest)
        frozen['floor'] = {p.name: HISTORY['digest'](p)
                           for p in (image / 'priv/bootstrap/seed').iterdir() if p.is_file()}
        frozen['sdk'] = {'path': str(sdk), 'metadata': HISTORY['digest'](sdk / 'artifact.json'),
                         'image': str(image), 'engine': selected[1]}
        frozen['adapter'] = HISTORY['digest'](Path(__file__))
        return frozen

    out.mkdir(parents=True)
    frozen = capture()
    (out / 'inputs.json').write_text(json.dumps(frozen, indent=2) + '\n')
    (out / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    receipt = {'version': 1, 'status': 'running', 'sdk': str(sdk), 'engine': selected[1],
               'cases': ids, 'complete_goal': False, 'scope': 'exact-SDK historical selector replay'}
    start = time.monotonic()
    cleanup = runpy.run_path(str(ROOT / 'scripts/qualify-candidate.py'))['stop_children']
    try:
        with tempfile.TemporaryDirectory(prefix='bl-history-', dir=os.environ.get('XDG_RUNTIME_DIR')) as runtime:
            env = dict(os.environ, BL_EXECUTION_HISTORY_ROOT=str(ROOT),
                       BL_EXECUTION_HISTORY_RUNTIME_ROOT=str(image), BL_EXECUTION_HISTORY_OUT=str(out),
                       BL_TEST_SOURCE_ROOT=str(ROOT), BL_QUALIFY_CANDIDATE=str(sdk / 'bin/bl'),
                       BL_DAEMON='off', BL_TEST_TIMES='1', XDG_RUNTIME_DIR=runtime,
                       ELIXIR_ERL_OPTIONS='+S 4:4 +SDcpu 2:2 +SDio 1:1')
            for key in ['BL_ROOT', 'BL_EBIN', 'BL_BIN', 'BL_USE', 'BL_CHECKOUT_ROOT',
                        'BL_CHECKOUT_COLD', 'BL_CHECKOUT_GENERATION', 'BL_CHECKOUT_SOURCE_GENERATION',
                        'BEAM_LISP_PATH', 'BL_SDK_PRODUCT']:
                env.pop(key, None)
            try:
                with (out / 'run.log').open('w') as log:
                    result = subprocess.run([str(sdk / 'bin/bl'), '--cold', 'run', str(ROOT / HISTORY['DRIVER'])],
                                            cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT,
                                            timeout=args.timeout)
            finally:
                cleanup(runtime)
        receipt['child_exit'] = result.returncode
        if result.returncode:
            raise RuntimeError('historical receiver failed; see retained run.log/execution.json')
        if capture() != frozen:
            raise RuntimeError('frozen source/test/tool/SDK/floor inputs changed')
        if subprocess.check_output([str(ROOT / 'scripts/prepare-checkout-sdk'), '--fingerprint'],
                                   cwd=ROOT, text=True).strip() != selected[1]:
            raise RuntimeError('SDK engine inputs changed')
        execution = json.loads((out / 'execution.json').read_text())
        HISTORY['validate_identity'](execution.get('image'), image, frozen)
        actual = HISTORY['validate_execution'](execution.get('files'), plan)
        receipt.update(status='regressions-passed', frozen_inputs_unchanged=True,
                       image=execution['image'], files=len(plan), tests=len(actual),
                       assertions=sum(test['pass'] for test in actual.values()),
                       case_results=[{'id': case['id'], 'status': 'regressions-passed',
                                      'historical_case_closed': HISTORY['controls_bound'](case),
                                      'remaining': case['remaining']} for case in chosen])
    except Exception as error:
        receipt.update(status='failed', error=str(error))
        raise
    finally:
        receipt['seconds'] = round(time.monotonic() - start, 3)
        (out / 'result.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({key: receipt[key] for key in ['status', 'sdk', 'files', 'tests', 'assertions']}))


if __name__ == '__main__':
    main()
