#!/usr/bin/env python3
"""Execute current checks on one immutable SDK; collect failures explicitly."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('sdk', 'request', 'root', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    root, sdk, out = args.root.resolve(), args.sdk.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    request = json.loads(args.request.read_text())
    metadata = json.loads((sdk / 'artifact.json').read_text())
    assert (metadata['version'], metadata['kind'], metadata['target']) == (1, 'sdk', 'x86_64-linux')
    # Resolve this on the executing station. Evaluation-time SDK metadata reads
    # would force a thin client to fetch the producer closure before offload.
    os.environ['PATH'] = str(Path(metadata['platform']) / 'bin') + os.pathsep + os.environ['PATH']
    portable = Path(metadata['release']) / 'bl.drop'
    qualifier = module(root / 'scripts/qualify-candidate.py')
    receipt = {'version': 1, 'status': 'running', 'request': request,
               'sdk_descriptor_sha256': digest(sdk / 'artifact.json'),
               'candidate_sha256': digest(portable),
               'compiler_manifest_sha256': digest(sdk / 'image/priv/bootstrap/seed/manifest.term'),
               'SDK_production_requested': os.environ['CI_CHECK_SDK_RETAINED'] != '1',
               'worker_memory_kib': int(os.environ['BL_WORKER_MEMORY_KIB']),
               'worker_swap_kib': int(os.environ['BL_WORKER_SWAP_KIB'])}
    started = time.monotonic()
    try:
        if request['kind'] == 'shard':
            groups = module(root / 'scripts/ci-test-shard.py').partitions(root, request['count'])
            files = groups[request['index']]
        elif request['kind'] == 'files':
            files = request['files']
        else:
            raise ValueError('Check kind must be files or shard')
        assert files and len(files) == len(set(files))
        for name in files:
            path = (root / name).resolve(strict=True)
            assert path.is_relative_to(root / 'test') and path.is_file()
            assert name.endswith(('_test.bl', '_test.exs'))
        receipt['files'] = files
        # Project the actual release for existing direct-runtime fixtures.
        module(root / 'scripts/ci-materialize-candidate.py').materialize(root, portable, sdk)
        candidate = root / '.bl/ci-candidate'
        shutil.copyfile(portable, candidate); candidate.chmod(0o755)
        subprocess.run(['git', 'init', '-q', str(root)], check=True)
        subprocess.run(['git', 'add', '-A'], cwd=root, check=True)
        before = qualifier.source_digest(root)
        receipt['source_sha256'] = before
        context = module(root / 'scripts/ci-test-shard.py').verified_context({'BL_SDK_PRODUCT': str(sdk)})
        env = dict(os.environ, **context, BL_HISTORY_SDK=str(sdk), BL_DAEMON='off',
                   BL_TEST_TIMES='1', BL_TEST_SOURCE_ROOT=str(root),
                   BL_TEST_USER_RUNTIME_DIR=os.environ['XDG_RUNTIME_DIR'],
                   BEAM_LISP_Z3=str(sdk / 'image/priv/z3/bin/z3'))
        for name in ('BL_ROOT', 'BL_EBIN', 'BL_BIN', 'BL_CHECKOUT_ROOT', 'BL_INTERNAL_PRODUCER',
                     'BEAM_LISP_PATH', 'ERL_LIBS', 'ERL_FLAGS', 'ERL_AFLAGS', 'ERL_ZFLAGS'):
            env.pop(name, None)
        command = [sys.executable, str(root / 'scripts/qualify-candidate.py'),
                   '--candidate', str(candidate), '--results', str(out / 'files.jsonl'),
                   '--timeout', str(request.get('file_timeout_seconds', 300)), *files]
        with (out / 'run.log').open('w') as log:
            result = subprocess.run(command, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT,
                                    timeout=request.get('timeout_seconds', 5400))
        receipt['exit'] = result.returncode
        receipt['frozen_inputs_unchanged'] = qualifier.source_digest(root) == before and digest(candidate) == receipt['candidate_sha256']
        if result.returncode or not receipt['frozen_inputs_unchanged']:
            raise RuntimeError('Current check failed; see file receipts and run.log')
        rows = qualifier.completed(out / 'files.jsonl', {'candidate': receipt['candidate_sha256'], 'source': before})
        assert set(rows) == set(files)
        assert all(row['pass'] > 0 and row['fail'] == row['error'] == 0 for row in rows.values())
        receipt.update(status='passed', assertions=sum(row['pass'] for row in rows.values()))
    except Exception as error:
        receipt.update(status='failed', error=str(error))
    finally:
        receipt['seconds'] = round(time.monotonic() - started, 3)
        (out / 'result.json').write_text(json.dumps(receipt, indent=2) + '\n')
        print(json.dumps({key: receipt[key] for key in ('status', 'seconds', 'sdk_descriptor_sha256')}))
    # A failed check stays collectable. scripts/ci-check requires status=passed.


if __name__ == '__main__':
    main()
