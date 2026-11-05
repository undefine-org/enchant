"""One synthetic Linux VM child: root-owned selection, unprivileged writer."""
import os
from pathlib import Path
import signal
import subprocess
import sys

candidate, worker, parent = map(Path, sys.argv[1:])
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
permissions(parent, 0o750)
permissions(parent / 'writer', 0o750)
permissions(parent / 'activation.json', 0o640)
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

child = subprocess.Popen([str(candidate), '--cold', 'run', str(worker), str(parent)],
                         cwd=sandbox, env=env, preexec_fn=drop_identity,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, start_new_session=True)
try:
    output, _ = child.communicate(timeout=90)
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
print(output, end='')
raise SystemExit(child.returncode)
