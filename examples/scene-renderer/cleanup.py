#!/usr/bin/env python3
"""Drain only processes carrying this preview's unique private runtime path.
Checkout compiler VMs move into their own capped systemd scopes, so stopping
only the preview's cgroup does not establish that its compiler has stopped.
"""
from pathlib import Path
import os
import signal
import sys
import time

runtime = sys.argv[1]
assert runtime.startswith('/tmp/bl-scene-preview.')
marker = b'XDG_RUNTIME_DIR=' + os.fsencode(runtime)
exclude = {os.getpid(), os.getppid()}

def owned():
    result = []
    for p in Path('/proc').iterdir():
        if not p.name.isdigit() or int(p.name) in exclude:
            continue
        try:
            if marker in (p / 'environ').read_bytes().split(b'\0'):
                result.append(int(p.name))
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            pass
    return result

def stop(sig):
    for pid in owned():
        try: os.kill(pid, sig)
        except ProcessLookupError: pass
stop(signal.SIGTERM)
for _ in range(20):
    if not owned(): break
    time.sleep(.1)
stop(signal.SIGKILL)
