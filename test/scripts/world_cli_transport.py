#!/usr/bin/env python3
"""Exercise world commands through one checkout VM; always stop the private VM.

Run under a process-tree cap, as for checkout_transport.py. No project files or
shared daemon are changed. The manifest and emitted code retain their own gates.
"""
from pathlib import Path
import json
import os
import signal
import subprocess
import tempfile
import time


root = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix="bl-world-transport-") as temporary:
    scratch = Path(temporary)
    runtime = scratch / "runtime"
    runtime.mkdir(mode=0o700)
    env = {**os.environ, "XDG_RUNTIME_DIR": str(runtime), "XDG_STATE_HOME": str(scratch / "state")}
    env.pop("BL_CHECKOUT_COLD", None)
    env.pop("BL_DAEMON", None)
    marker = f"XDG_RUNTIME_DIR={runtime}".encode() + b"\0"
    report = {"status": "running", "seconds": {}, "native_admission": False}

    def run(label, *args):
        started = time.monotonic()
        result = subprocess.run([str(root / "bin/bl"), *args], cwd=root, env=env,
                                text=True, capture_output=True, timeout=180)
        report["seconds"][label] = round(time.monotonic() - started, 3)
        assert result.returncode == 0, (label, result.stdout, result.stderr)
        return result.stdout

    def owned_vms():
        found = []
        for path in Path("/proc").iterdir():
            if not path.name.isdigit():
                continue
            try:
                if marker in (path / "environ").read_bytes() and b"beam.smp" in (path / "cmdline").read_bytes():
                    found.append(int(path.name))
            except (FileNotFoundError, PermissionError, ProcessLookupError):
                pass
        return found

    try:
        manifest = "test/fixtures/contextual-validation/world.bl"
        first = json.loads(run("first_check", "world", "check", manifest, "--json"))
        before = run("owner_before", "eval", '(println (str "WORLD-OWNER " (System/pid)))')
        repeated = json.loads(run("repeat_check", "world", "check", manifest, "--json"))
        value = run("run", "world", "run", manifest)
        after = run("owner_after", "eval", '(println (str "WORLD-OWNER " (System/pid)))')
        owner = lambda text: int(next(line[12:] for line in text.splitlines() if line.startswith("WORLD-OWNER ")))
        assert owner(before) == owner(after), "world commands replaced the warm VM"
        assert owner(before) in owned_vms(), "commands did not use the private persistent VM"
        assert first["snapshot"] == repeated["snapshot"]
        assert first["phase-check"] == "proved" and first["native-effects"] == "unknown"
        assert "[42 99 42]" in value.splitlines()
        report.update(status="passed", same_vm=True, repeated_snapshot=True, value=[42, 99, 42])
    finally:
        try:
            subprocess.run([str(root / "bin/bl"), "realm", "stop"], cwd=root, env=env,
                           text=True, capture_output=True, timeout=30)
        except (subprocess.TimeoutExpired, OSError):
            pass
        # Match only this test's unique runtime directory if the normal stop
        # fails. Never select peers by command names or a shared checkout path.
        for pid in owned_vms():
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + 10
        while owned_vms() and time.monotonic() < deadline:
            time.sleep(0.05)
        for pid in owned_vms():
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + 2
        while owned_vms() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not owned_vms(), "private world test VM survived cleanup"
        report["private_vm_stopped"] = True
    print(json.dumps(report, indent=2))
