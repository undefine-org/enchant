"""Finite generation-creation process/power cuts on one synthetic persistent root."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import tarfile
import time


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inputs():
    return {str(path): digest(path) for path in [
        Path('scripts/datom-generation-crash-check.py'), Path('scripts/datom-power-cut.py'),
        Path('test/support/datom_generation_fsync.c'), Path('test/support/datom_generation_crash.bl'),
        *sorted(Path('test/fixtures/datom').glob('*')), Path('flake.lock')] if path.is_file()}


def tree(root):
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_file():
            with path.open('rb') as stream:
                result[str(path.relative_to(root))] = hashlib.file_digest(stream, 'sha256').hexdigest()
        elif path.is_dir():
            result[str(path.relative_to(root)) + '/'] = 'directory'
        else:
            raise ValueError('Unexpected fixture entry')
    return result


def sync_fixture(parent):
    # Sync only the test's ext4 fixture and its ancestor directory entries.
    # Global sync would also flush the shared Nix store through virtiofs.
    paths = sorted(parent.rglob('*'), key=lambda p: len(p.parts), reverse=True)
    for path in [*paths, parent, *parent.parents]:
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--injector', required=True)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--power', choices=('prepare', 'recover'))
    parser.add_argument('--boundary', choices=('marker-created', 'marker-synced', 'marker-retired', 'data-ack'))
    args = parser.parse_args()
    if args.power and not args.boundary:
        parser.error('--power requires --boundary')
    # Refuse before any fixture/BL process when invoked outside the finite VM.
    assert 0 < int(os.environ['BL_WORKER_MEMORY_KIB']) <= 6144 * 1024
    assert int(os.environ['BL_WORKER_SWAP_KIB']) == 0
    source_hashes = inputs()
    candidate_hash = digest(args.candidate)
    args.out.mkdir(exist_ok=bool(args.power))
    rows = []
    for boundary in ([args.boundary] if args.boundary else ('marker-created', 'marker-synced', 'marker-retired', 'data-ack')):
        parent = Path('/build/generation-crash-fixtures') / boundary
        original = parent / 'original'
        baseline = parent / 'baseline.json'
        if args.power == 'recover':
            before = json.loads(baseline.read_text())
        else:
            original.mkdir(parents=True)
            evidence = json.loads(Path('test/fixtures/datom/legacy-root-v1.json').read_text())
            for part in evidence['archives']:
                archive = Path('test/fixtures/datom') / part['file']
                assert digest(archive) == part['sha256']
                with tarfile.open(archive) as source:
                    source.extractall(original, filter='data')
            before = tree(original)
            baseline.write_text(json.dumps(before))
            # The original fixture predates the fault. Do this before the SDK
            # starts, so this cannot flush any conversion or publication work.
            sync_fixture(parent)
        env = dict(os.environ, DATOM_CRASH_ROOT=str(parent), DATOM_CRASH_BOUNDARY=boundary, BL_DAEMON='off')
        command = [args.candidate, '--cold', 'run', 'test/support/datom_generation_crash.bl', '--']
        if args.power != 'recover':
            with (args.out / (boundary + '-seed.log')).open('w') as log:
                seeded = subprocess.run([*command, 'seed'], env=env, stdout=log, stderr=subprocess.STDOUT, timeout=180)
            assert seeded.returncode == 0, 'generation seed failed'
            protocol = {name: digest(parent / 'generation' / name) for name in ('READY.json', '.bl-generation')}
            (parent / 'protocol.json').write_text(json.dumps(protocol))
            sync_fixture(parent)
        else:
            protocol = json.loads((parent / 'protocol.json').read_text())
        ack = parent / 'stopped'
        injected = dict(env, LD_PRELOAD=args.injector, DATOM_CRASH_ACK=str(ack))
        if args.power != 'recover':
            inject(args, [*command, 'write'], injected, ack, boundary)
        assert tree(original) == before
        with (args.out / (boundary + '-recovery.log')).open('w') as log:
            recovered = subprocess.run([*command, 'recover'], env=env,
                                       stdout=log, stderr=subprocess.STDOUT, timeout=180)
        assert recovered.returncode == 0, f'{boundary}: recovery failed'
        assert 'DATOM-GENERATION-RECOVERED' in (args.out / (boundary + '-recovery.log')).read_text()
        assert tree(original) == before
        ready = json.loads((parent / 'generation/READY.json').read_text())
        assert ready['keyFormat'] == 2 and len(ready['stores']) == 2
        assert protocol == {name: digest(parent / 'generation' / name) for name in protocol}
        assert not (parent / 'generation/firm/library.fjall/.bl-datom-create').exists()
        assert not (parent / 'generation/firm/library.fjall/.bl-datom-create.pending').exists()
        rows.append({'protocol_unchanged': True, 'writer_reopened': True, 'boundary': boundary, 'signal': 'VM-SIGKILL' if args.power else 'SIGKILL',
                     'recovered': True, 'original_unchanged': True})
        if args.power:
            (args.out / (boundary + '.json')).write_text(json.dumps(rows[0]) + '\n')
            rows = [json.loads(p.read_text()) for p in sorted(args.out.glob('*.json'))
                    if p.name != 'result.json']
    assert source_hashes == inputs() and candidate_hash == digest(args.candidate)
    sdk = Path(os.environ['BL_SDK_PRODUCT'])
    (args.out / 'result.json').write_text(json.dumps({'version': 1,
        'status': 'passed' if len(rows) == 4 else 'partial',
        'sdk_descriptor_sha256': digest(sdk / 'artifact.json'),
        'compiler_manifest_sha256': digest(sdk / 'image/priv/bootstrap/seed/manifest.term'),
        'candidate_sha256': candidate_hash,
        'source_sha256': hashlib.sha256(json.dumps(source_hashes, sort_keys=True).encode()).hexdigest(),
        'frozen_inputs_unchanged': True,
        'execution': 'bounded-vm', 'worker_memory_kib': int(os.environ['BL_WORKER_MEMORY_KIB']),
        'worker_swap_kib': int(os.environ['BL_WORKER_SWAP_KIB']), 'controls': rows}, indent=2) + '\n')


def inject(args, command, injected, ack, boundary):
    with (args.out / (boundary + '-victim.log')).open('w') as log:
        victim = subprocess.Popen(command, env=injected, stdout=log, stderr=subprocess.STDOUT,
                                  start_new_session=True)
        try:
            deadline = time.monotonic() + 180
            while not ack.exists():
                if victim.poll() is not None:
                    raise RuntimeError(f'{boundary}: victim exited before injected fsync')
                if time.monotonic() >= deadline:
                    raise TimeoutError(f'{boundary}: fsync boundary was not observed')
                time.sleep(.05)
            assert ack.read_text() == boundary
            # Verify the whole process actually stopped, not just a receipt.
            deadline = time.monotonic() + 10
            while Path(f'/proc/{victim.pid}/status').read_text().split('State:')[1].strip()[0] != 'T':
                if time.monotonic() >= deadline:
                    raise TimeoutError('victim did not stop')
                time.sleep(.01)
            if args.power:
                # The host sees this only after the guest has established
                # the victim's actual stopped state. It then kills QEMU.
                Path('/tmp/xchg/power-ack').write_text(boundary)
                victim.wait(timeout=300)
                raise RuntimeError('power-cut victim unexpectedly resumed')
            os.killpg(victim.pid, signal.SIGKILL)
            assert victim.wait(timeout=20) == -signal.SIGKILL
        finally:
            if victim.poll() is None:
                os.killpg(victim.pid, signal.SIGKILL)
                victim.wait(timeout=20)


if __name__ == '__main__':
    main()
