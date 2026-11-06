"""One synthetic Linux VM child: root-owned selection, unprivileged writer."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import json
import socket
import time
import urllib.request

candidate, worker, parent = map(Path, sys.argv[1:4])
mode = sys.argv[4] if len(sys.argv) == 5 else 'admit'
assert mode in ('admit', 'boot', 'incompatible')
assert os.getuid() == 0, "This fixture is for the bounded root VM only"
assert parent.parent == Path('/tmp') and parent.name.endswith('.nonroot-admission')
uid = gid = 65534

def permissions(path, mode, owner=0):
    assert not path.is_symlink()
    os.chown(path, owner, gid)
    os.chmod(path, mode)

generation = parent / 'generation'
for directory, children, files in os.walk(generation, followlinks=False):
    directory = Path(directory)
    permissions(directory, 0o2770)
    for name in children:
        assert not (directory / name).is_symlink()
    for name in files:
        permissions(directory / name, 0o660)
permissions(generation, 0o1770)
permissions(generation / 'libraries', 0o1770)
for name in ('.bl-generation', 'READY.json'):
    permissions(generation / name, 0o640)
# The SDK, not this helper, must publish the protected reader permissions.
for path, reader_mode in ((parent, 0o750), (parent / 'writer', 0o750), (parent / 'activation.json', 0o640)):
    metadata = path.stat()
    assert (metadata.st_uid, metadata.st_gid, metadata.st_mode & 0o777) == (0, gid, reader_mode), path
sandbox = parent / 'child'
sandbox.mkdir()
runtime = sandbox / 'runtime'
runtime.mkdir()
permissions(runtime, 0o700, uid)
permissions(sandbox, 0o755, uid)
env = dict(os.environ, XDG_RUNTIME_DIR=str(runtime), XDG_CACHE_HOME=str(sandbox / 'cache'))

def drop_identity():
    os.setgroups([])
    os.setgid(gid)
    os.setuid(uid)

arguments = [str(candidate), '--cold', 'run', str(worker), '--', str(parent)]
if mode != 'admit':
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    arguments.append(str(port))
child = subprocess.Popen(arguments,
                         cwd=sandbox, env=env, preexec_fn=drop_identity,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, start_new_session=True)
try:
    if mode == 'boot':
        deadline = time.monotonic() + 90
        successful = False
        while child.poll() is None and time.monotonic() < deadline:
            if (parent / 'stop').exists():
                break
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/health/ready', timeout=1) as response:
                    health = json.load(response)
                if health.get('status') == 'read-only-ready':
                    assert not (sandbox / 'application-loaded').exists(), 'application namespace ran before grant'
                    assert not (sandbox / 'initialized').exists(), 'initializer ran before grant'
                    proof = parent / 'readiness.json'
                    if not proof.exists():
                        proof.write_text(json.dumps(health))
                elif health.get('status') == 'ready':
                    assert health['generation']['status'] == 'write-admitted'
                    assert health['generation']['writesAdmitted'] is True
                    assert health['borrowed'] is True and health['rootSelected'] is True
                    assert (sandbox / 'application-loaded').exists()
                    assert (sandbox / 'initialized').exists()
                    successful = True
                    break
            except (OSError, ValueError):
                pass
            time.sleep(0.05)
        if not successful and child.poll() is not None:
            raise AssertionError('generation bootstrap exited early:\n' + child.stdout.read())
        assert successful, 'generation bootstrap did not complete after admission'
        output = 'NONROOT-GENERATION-BOOTSTRAPPED\n'
    else:
        output, _ = child.communicate(timeout=90)
        if mode == 'incompatible':
            assert child.returncode != 0, output
            assert 'Selected runtime cannot serve this index format' in output, output
            assert not (sandbox / 'application-loaded').exists()
            assert not (sandbox / 'initialized').exists()
            output += 'NONROOT-GENERATION-BOOT-REFUSED\n'
finally:
    # Stop only this fixture's process group, including a stuck cold child.
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        child.wait(timeout=3)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        child.wait(timeout=3)
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    # The test VM deliberately lacks DAC override. Return only this child's
    # directories so its root controller can remove the private sandbox.
    # Never follow cache symlinks or change payload file permissions.
    def hand_back(directory):
        os.chown(directory, 0, 0)
        os.chmod(directory, 0o700)
        for entry in directory.iterdir():
            if not entry.is_symlink() and entry.is_dir():
                hand_back(entry)
    hand_back(sandbox)
print(output, end='')
raise SystemExit(child.returncode if mode == 'admit' else 0)
