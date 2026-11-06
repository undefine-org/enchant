"""Synthetic portable release cache: real launcher, abrupt guest death, same disk."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import time
import tarfile

FILES = {
    'bin/bl': b'#!/bin/sh\nprintf "cache-fixture-complete\\n"\n',
    'releases/start_erl.data': b'17.0 0.1.0\n',
    'releases/0.1.0/elixir': b'elixir fixture\n',
    'erts-17.0/bin/erl': b'erl fixture\n',
    'erts-17.0/bin/beam.smp': b'beam fixture\n',
    'lib/beam_lisp-0.1.0/ebin/beam_lisp.app': b'app fixture\n',
}


def sync_tree(root):
    for child in root.iterdir():
        if child.is_dir():
            sync_tree(child)
        elif child.is_file():
            with child.open('rb') as stream:
                os.fsync(stream.fileno())
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def fixture(parent, launcher):
    parent.mkdir()
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode='w:gz') as tar:
        for name, content in FILES.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(content), 0o755, 0
            tar.addfile(info, io.BytesIO(content))
    data = payload.getvalue()
    digest = hashlib.sha256(data).digest()
    binary = launcher.read_bytes()
    drop = parent / 'fixture.drop'
    drop.write_bytes(binary + data + struct.pack('<QQ32sBBH4s', len(binary), len(data), digest, 0, 0, 1, b'DRP1'))
    drop.chmod(0o755)
    destination = parent / 'store' / digest.hex()[:8]
    (destination / 'bin').mkdir(parents=True)
    (destination / 'bin/bl').write_bytes(b'broken cache entry\n')
    (parent / 'original-data').write_bytes(b'authoritative data untouched\n')
    (parent / 'fixture.json').write_text(json.dumps({'id': digest.hex()[:8], 'payload_sha256': digest.hex()}))
    sync_tree(parent)
    fd = os.open(parent.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return destination


def environment(parent):
    return dict(os.environ, DROP_STORE_ROOT=str(parent / 'store'), XDG_RUNTIME_DIR='/run/drop-cache-fixture')


def prepare(args, parent):
    destination = fixture(parent, args.launcher)
    env = dict(environment(parent), LD_PRELOAD=str(args.injector), DROP_CACHE_STORE=str(parent / 'store'),
               DROP_CACHE_DESTINATION=str(destination), DROP_CACHE_BOUNDARY=args.boundary,
               DROP_CACHE_ACK=str(parent / 'stopped'))
    with (parent / 'victim.log').open('wb') as output:
        victim = subprocess.Popen([str(parent / 'fixture.drop'), '--cold', 'eval', 'fixture'],
                                  env=env, cwd=parent, stdout=output, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 30
        try:
            while not (parent / 'stopped').exists():
                if victim.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError('launcher did not reach the injected boundary: ' + (parent / 'victim.log').read_text())
                time.sleep(.02)
            while '\nState:\tT ' not in Path(f'/proc/{victim.pid}/status').read_text():
                if time.monotonic() >= deadline:
                    raise RuntimeError('victim did not stop')
                time.sleep(.01)
            assert (parent / 'stopped').read_text() == args.boundary
            # Only after observing the actual stopped process may the host cut
            # power. No guest sync, shutdown, or cleanup follows this message.
            Path('/tmp/xchg/power-ack').write_text(args.boundary)
            while True:
                time.sleep(1)
        finally:
            if victim.poll() is None:
                victim.kill()
            victim.wait(timeout=10)


def recover(args, parent):
    info = json.loads((parent / 'fixture.json').read_text())
    destination = parent / 'store' / info['id']
    selection_survived = (destination / 'releases/start_erl.data').is_file()
    env = environment(parent)
    for turn in range(2):
        result = subprocess.run([str(parent / 'fixture.drop'), '--cold', 'eval', 'fixture'],
                                cwd=parent, env=env, capture_output=True, timeout=30)
        assert (result.returncode, result.stdout, result.stderr) == (0, b'cache-fixture-complete\n', b''), result
        for name, content in FILES.items():
            assert (destination / name).read_bytes() == content, name
        if turn == 0:
            inode = destination.stat().st_ino
            (destination / 'winner-preserved').write_bytes(b'keep')
        else:
            assert destination.stat().st_ino == inode
            assert (destination / 'winner-preserved').read_bytes() == b'keep'
    assert (parent / 'original-data').read_bytes() == b'authoritative data untouched\n'
    return {'boundary': args.boundary, 'release_selection_survived': selection_survived,
            'repaired_or_reused': True, 'warm_retry_kept_inode': True,
            'files_verified': len(FILES), 'original_data_preserved': True}


def real_sdk_check(launcher, candidate):
    parent = Path('/build/real-sdk-cache')
    parent.mkdir()
    store = parent / 'store'
    env = dict(os.environ, DROP_STORE_ROOT=str(store), BL_USE='path:' + str(candidate),
               XDG_RUNTIME_DIR='/run/drop-real-sdk-fixture')
    result_rows = []
    for turn in range(2):
        result = subprocess.run([str(launcher), '--cold', 'eval', '(+ 1700 1)'],
                                cwd=parent, env=env, capture_output=True, timeout=90)
        assert result.returncode == 0 and result.stdout.strip() == b'1701', (result.returncode, result.stdout, result.stderr)
        roots = [p for p in store.iterdir() if p.is_dir() and len(p.name) == 8]
        assert len(roots) == 1, roots
        root = roots[0]
        selected = (root / 'releases/start_erl.data').read_bytes()
        result_rows.append({'turn': turn, 'startup_ok': True, 'release_selection_present': True})
        if turn == 0:
            before = selected
            (root / 'releases/start_erl.data').unlink()
            assert (root / 'bin').is_dir()
        else:
            assert selected == before
    return {'candidate_sha256': hashlib.file_digest(candidate.open('rb'), 'sha256').hexdigest(),
            'controls': result_rows, 'missing_selection_with_bin_present_repaired': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('launcher', 'injector', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--operation', choices=('prepare', 'recover'), required=True)
    parser.add_argument('--boundary', choices=('file-synced', 'tree-synced', 'renamed', 'published'), required=True)
    args = parser.parse_args()
    parent = Path('/build/cache-' + args.boundary)
    if args.operation == 'prepare':
        prepare(args, parent)
    else:
        row = recover(args, parent)
        args.out.mkdir(exist_ok=True)
        path = args.out / 'result.json'
        result = json.loads(path.read_text()) if path.exists() else {'version': 1, 'status': 'running', 'controls': []}
        result['controls'].append(row)
        if len(result['controls']) == 4:
            result['status'] = 'passed'
            if args.candidate:
                result['real_sdk'] = real_sdk_check(args.launcher, args.candidate)
        result.update(worker_memory_kib=int(os.environ['BL_WORKER_MEMORY_KIB']),
                      worker_swap_kib=int(os.environ['BL_WORKER_SWAP_KIB']))
        path.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
