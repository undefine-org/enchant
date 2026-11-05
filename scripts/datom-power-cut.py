"""Own one finite KVM guest at a time; abruptly kill and reboot the same disk."""
import argparse
import json
from pathlib import Path
import signal
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', required=True)
    parser.add_argument('--virtiofsd', required=True)
    parser.add_argument('qemu_args', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = [args.qemu] + args.qemu_args[1:]
    # vmTools defaults cache=unsafe, which ignores the guest's flushes. This
    # control requires fsync to reach the host before the simulated power cut.
    command = [arg.replace('cache=unsafe', 'cache=writeback,format=raw')
                  .replace('path=virtio-store.sock', 'path=crash-store.sock')
                  .replace('path=virtio-xchg.sock', 'path=crash-xchg.sock') for arg in command]
    assert any('cache=writeback,format=raw' in arg for arg in command)
    cuts = []
    for boundary in ('converting', 'store-complete', 'ready', 'renamed'):
        for operation in ('prepare', 'recover'):
            print('DATOM-POWER', boundary, operation, flush=True)
            Path('xchg/power-stage').write_text(operation + ' ' + boundary + '\n')
            for name in ('xchg/power-ack', 'xchg/in-vm-exit', 'crash-store.sock', 'crash-xchg.sock'):
                Path(name).unlink(missing_ok=True)
            daemons = []
            guest = None
            try:
                for name, directory in (('store', '/nix/store'), ('xchg', 'xchg')):
                    daemons.append(subprocess.Popen([args.virtiofsd, '--xattr', '--sandbox', 'none',
                        '--seccomp', 'none', '--socket-path', 'crash-' + name + '.sock',
                        '--shared-dir', directory]))
                deadline = time.monotonic() + 20
                while not all(Path('crash-' + name + '.sock').exists() for name in ('store', 'xchg')):
                    if time.monotonic() >= deadline or any(p.poll() is not None for p in daemons):
                        raise RuntimeError('fixture filesystem service did not start')
                    time.sleep(.05)
                guest = subprocess.Popen(command)
                deadline = time.monotonic() + 300
                if operation == 'prepare':
                    while not Path('xchg/power-ack').exists():
                        if guest.poll() is not None or time.monotonic() >= deadline:
                            raise RuntimeError('guest failed before stopped-victim acknowledgement')
                        time.sleep(.05)
                    assert Path('xchg/power-ack').read_text() == boundary
                    guest.kill()  # No guest shutdown, unmount, or process cleanup.
                    assert guest.wait(timeout=20) == -signal.SIGKILL
                    cuts.append({'boundary': boundary, 'qemu_signal': 'SIGKILL',
                                 'same_disk_reboot': True, 'cache': 'writeback'})
                else:
                    assert guest.wait(timeout=300) == 0
                    assert Path('xchg/in-vm-exit').read_text().strip() == '0'
            except BaseException:
                debug = Path('xchg/worker-debug')
                if debug.exists():
                    print(debug.read_text(errors='replace')[-12000:], flush=True)
                raise
            finally:
                if guest is not None and guest.poll() is None:
                    guest.kill()
                    guest.wait(timeout=20)
                for daemon in daemons:
                    if daemon.poll() is None:
                        daemon.terminate()
                    daemon.wait(timeout=20)
    Path('xchg/power-controller.json').write_text(json.dumps({'version': 1,
        'status': 'passed', 'controls': cuts}, indent=2) + '\n')


if __name__ == '__main__':
    main()
