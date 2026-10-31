#!/usr/bin/env python3
"""Run a finite proof request on an existing SDK; no preparation/build entry.

The surrounding Nix VM owns memory, disk, process lifetime and its user manager.
A successful Nix realization only transports the receipt; callers must require
status=passed, exact selectors, nonzero assertion counts and unchanged inputs.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import time


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(root):
    return {str(p.relative_to(root)): digest(p) for p in sorted(root.rglob('*'))
            if p.is_file() and not any(x in p.relative_to(root).parts
                                      for x in ['.git', '.bl', '__pycache__', 'target'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    root, sdk, out = args.root.resolve(), args.sdk.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    request = json.loads(args.request.read_text())
    metadata = json.loads((sdk / 'artifact.json').read_text())
    assert metadata['kind'] == 'sdk' and metadata['version'] == 1
    image = (sdk / 'image').resolve()
    frozen = snapshot(root)
    (out / 'inputs.json').write_text(json.dumps(frozen, indent=2) + '\n')
    receipt = {'version': 1, 'status': 'running', 'scope': 'existing-SDK case-specific proof',
               'sdk': str(sdk), 'sdk_metadata_sha256': digest(sdk / 'artifact.json'),
               'request': request, 'worker_memory_kib': os.environ.get('BL_WORKER_MEMORY_KIB'),
               'worker_swap_kib': os.environ.get('BL_WORKER_SWAP_KIB'),
               'SDK_rebuilt': False, 'compiler_rebuilt': False}
    started = time.monotonic()
    env = dict(os.environ, BL_DAEMON='off', BL_TEST_TIMES='1',
               BL_TEST_SOURCE_ROOT=str(root), BEAM_LISP_Z3=str(image / 'priv/z3/bin/z3'),
               BL_EXECUTION_HISTORY_ROOT=str(root), BL_EXECUTION_HISTORY_RUNTIME_ROOT=str(image),
               BL_EXECUTION_HISTORY_OUT=str(out), BL_TEST_USER_RUNTIME_DIR=os.environ['XDG_RUNTIME_DIR'],
               ELIXIR_ERL_OPTIONS='+S 2:2 +SDcpu 1:1 +SDio 1:1 +fnu')
    env['CLOSURE_PROOF_SDK'] = str(sdk)
    env['CLOSURE_PROOF_OUTPUT'] = str(out)
    for key in ['BL_ROOT', 'BL_EBIN', 'BL_BIN', 'BL_USE', 'BL_CHECKOUT_ROOT', 'BL_SDK_PRODUCT']:
        env.pop(key, None)
    try:
        if request['kind'] == 'selectors':
            plan = request['files']
            assert plan and all(row['selectors'] for row in plan)
            for row in plan:
                path = (root / row['path']).resolve()
                assert path.is_relative_to(root) and path.is_file()
            (out / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
            command = [str(sdk / 'bin/bl'), '--cold', 'run', str(root / 'test/scripts/execution-history-driver.bl')]
        elif request['kind'] == 'python':
            path = (root / request['path']).resolve()
            assert path.is_relative_to(root) and path.is_file()
            command = ['python3', str(path), *request.get('args', [])]
        else:
            raise ValueError('unknown proof request kind')
        with (out / 'run.log').open('w') as log:
            result = subprocess.run(command, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT,
                                    timeout=request.get('timeout', 900))
        receipt['child_exit'] = result.returncode
        if result.returncode:
            raise RuntimeError('proof child failed; see run.log and execution.json')
        if request['kind'] == 'selectors':
            execution = json.loads((out / 'execution.json').read_text())
            history = runpy.run_path(str(root / 'scripts/check-execution-history'))
            actual = history['validate_execution'](execution['files'], plan)
            floor = image / 'priv/bootstrap/seed'
            identity = {'floor': {p.name: digest(p) for p in floor.iterdir() if p.is_file()},
                        'tools': history['capture_tools'](root)}
            # capture_tools uses the same exact solver override used by the child.
            os.environ['BEAM_LISP_Z3'] = env['BEAM_LISP_Z3']
            identity['tools'] = history['capture_tools'](root)
            history['validate_identity'](execution['image'], image, identity)
            receipt.update(files=len(plan), tests=len(actual),
                           assertions=sum(row['pass'] for row in actual.values()),
                           image=execution['image'])
        assert snapshot(root) == frozen, 'proof Source/test inputs changed'
        receipt.update(status='passed', frozen_inputs_unchanged=True)
    except Exception as error:
        receipt.update(status='failed', error=str(error))
    finally:
        receipt['frozen_inputs_unchanged'] = snapshot(root) == frozen
        if not receipt['frozen_inputs_unchanged']:
            receipt.update(status='failed', error='proof Source/test inputs changed')
        receipt['seconds'] = round(time.monotonic() - started, 3)
        (out / 'result.json').write_text(json.dumps(receipt, indent=2) + '\n')
        print(json.dumps({k: receipt[k] for k in ['status', 'seconds', 'sdk']}), flush=True)
    # A failed proof remains a collectible artifact. Nix success is not proof.


if __name__ == '__main__':
    main()
