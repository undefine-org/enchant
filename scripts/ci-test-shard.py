#!/usr/bin/env python3
"""Run one disjoint partition of the complete conventional test corpus."""
import argparse
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import signal
import sys
import tempfile
import time


def host_nix_files(root):
    """Only declared real Nix consumers need the host daemon and writable store."""
    manifest = Path(root) / 'scripts/test-prerequisites.json'
    if not manifest.is_file():
        return set()
    # Use the existing validator, without admitting or starting any test tool.
    runpy.run_path(str(Path(__file__).with_name('test_prerequisites.py')))['require'](root, [])
    entries = json.loads(manifest.read_text())['tests']
    return {name for name, targets in entries.items()
            if {'nix', 'nix-instantiate', 'nix-store'} &
            set(targets.get('all', []) + targets.get('linux', []))}


def partitions(root, count, *, lane='all', startup_ms=11000):
    if count < 1:
        raise ValueError("count must be positive")
    if type(startup_ms) is not int or startup_ms < 0:
        raise ValueError("startup_ms must be a nonnegative integer")
    files = []
    for directory, dirs, names in os.walk(root / "test"):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in names:
            if name.endswith(("_test.bl", "_test.exs")):
                files.append(str((Path(directory) / name).relative_to(root)))
    if lane not in {'all', 'bounded', 'host-nix'}:
        raise ValueError('Unknown inventory execution lane')
    if lane != 'all':
        host = host_nix_files(root)
        files = [name for name in files if (name in host) == (lane == 'host-nix')]
    timing_file = root / "scripts/test-durations.json"
    if not timing_file.exists():
        return [sorted(files)[index::count] for index in range(count)]
    timings = json.loads(timing_file.read_text())
    isolation_file = root / "scripts/test-isolation.json"
    isolated = json.loads(isolation_file.read_text()) if isolation_file.exists() else {}
    # File receipts exclude application startup. Each isolated file owns an
    # additional cold VM; the ordinary warm group pays startup once per shard.
    # Serial produced-SDK receipts measured 10.7--11.4 s per isolated process.
    # Keep every isolation boundary and charge its estimated fixed work here.
    def cost(name):
        return max(1, timings.get(name, 1000)) + (startup_ms if name in isolated else 0)
    groups, loads = [[] for _ in range(count)], [0] * count
    for name in sorted(files, key=lambda name: (-cost(name), name)):
        index = min(range(count), key=lambda index: (loads[index], index))
        groups[index].append(name)
        loads[index] += cost(name)
    return groups


def verified_context(environ):
    names = ("BL_SDK_PRODUCT", "BL_ARTIFACT_PLATFORM", "BL_PREPARATION_COORDINATOR",
             "BL_PREPARED_NATIVES", "BL_TEST_CHECKOUT_PLATFORM")
    if not any(environ.get(name) for name in names):
        return {}
    sdk = Path(environ["BL_SDK_PRODUCT"]).resolve(strict=True)
    if not re.fullmatch(r"/nix/store/[0-9a-z]{32}-[^/]+", str(sdk)):
        raise ValueError("CI SDK context requires a retained immutable selection")
    metadata = json.loads((sdk / "artifact.json").read_text())
    if (metadata["version"], metadata["kind"], metadata["target"]) != (1, "sdk", "x86_64-linux"):
        raise ValueError("CI SDK context has unsupported identity")
    platform = Path(metadata["platform"]).resolve(strict=True)
    coordinator = (sdk / "preparation-coordinator").resolve(strict=True)
    if str(coordinator) != metadata["coordinator"]:
        raise ValueError("CI SDK coordinator retention disagrees")
    expected = {"BL_SDK_PRODUCT": sdk, "BL_ARTIFACT_PLATFORM": platform / "artifact-platform",
                "BL_PREPARATION_COORDINATOR": coordinator,
                "BL_PREPARED_NATIVES": (platform / "native-products").resolve(strict=True),
                "BL_TEST_CHECKOUT_PLATFORM": platform}
    for name, path in expected.items():
        path = path.resolve(strict=True)
        if not path.is_dir() or path.parts[:3] != ("/", "nix", "store"):
            raise ValueError(name + " must select an existing immutable Nix path")
        if environ.get(name) and Path(environ[name]).resolve(strict=True) != path:
            raise ValueError(name + " disagrees with the selected SDK")
        expected[name] = str(path)
    return expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=int, required=True)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--startup-ms", type=int, default=11000,
                        help="estimated cold VM startup cost for each isolated file")
    args = parser.parse_args()
    if not 0 <= args.index < args.count:
        parser.error("index must be within [0, count)")
    root = Path(__file__).resolve().parent.parent
    selected = partitions(root, args.count, startup_ms=args.startup_ms)[args.index]
    if not selected:
        parser.error("empty shard")
    print(f"Shard {args.index + 1}/{args.count}: {len(selected)} test files", flush=True)
    if args.list:
        print("\n".join(selected))
        return 0
    try:
        runpy.run_path(str(root / "scripts/test_prerequisites.py"))["require"](root, selected)
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))
    # One VM per shard. Independent runners provide isolation; each runner
    # executes its files serially under a cap, including any child processes.
    command = ["systemd-run", "--user", "--collect", "--wait", "--pipe", "--quiet",
               f"--working-directory={root}", "--property=MemoryMax=6G",
               "--property=MemorySwapMax=0", "--property=RuntimeMaxSec=5400",
               f"--setenv=PATH={os.environ.get('PATH', '')}",
               "--setenv=BL_TEST_TIMES=1",
               sys.executable, str(root / "scripts/qualify-candidate.py"),
               "--candidate", str(root / ".bl/ci-candidate"),
               "--results", str(Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())) /
                                f"bl-test-results-{args.index}.jsonl"), *selected]
    # The user manager does not inherit the Actions step environment. Carry
    # the producer's selected Rust identity across the same boundary as PATH.
    if os.environ.get("RUSTUP_TOOLCHAIN"):
        command.insert(command.index(sys.executable),
                       f"--setenv=RUSTUP_TOOLCHAIN={os.environ['RUSTUP_TOOLCHAIN']}")
    # CI may select an already-retained SDK on this host. Only its fixed
    # immutable provider context crosses this manager boundary; never producer
    # flags, checkout source roots, or arbitrary caller overrides.
    try:
        context = verified_context(os.environ)
    except (KeyError, OSError, ValueError) as error:
        parser.error(str(error))
    for name, value in context.items():
        command.insert(command.index(sys.executable), f"--setenv={name}={value}")
    runtime_parent = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    with tempfile.TemporaryDirectory(prefix="bl-ci-runtime-", dir=runtime_parent) as runtime:
        # Keep automatic checkout endpoints local to this shard. Preserve the
        # manager's actual bus address for capped subprocess verifiers.
        bus = os.environ.get("DBUS_SESSION_BUS_ADDRESS",
                             f"unix:path={runtime_parent}/bus")
        command[command.index(sys.executable):command.index(sys.executable)] = [
            f"--setenv=XDG_RUNTIME_DIR={runtime}",
            f"--setenv=DBUS_SESSION_BUS_ADDRESS={bus}"]
        try:
            return subprocess.call(command, cwd=root)
        finally:
            owned = []
            for proc in Path("/proc").iterdir():
                if not proc.name.isdigit():
                    continue
                try:
                    if (f"XDG_RUNTIME_DIR={runtime}".encode() + b"\0" in (proc / "environ").read_bytes()
                            and any(name in (proc / "cmdline").read_bytes().lower()
                                    for name in (b"beam_lisp", b"beamlisp."))):
                        owned.append(int(proc.name))
                        os.kill(int(proc.name), signal.SIGTERM)
                except (FileNotFoundError, ProcessLookupError, PermissionError):
                    pass
            deadline = time.monotonic() + 5
            while owned and time.monotonic() < deadline:
                owned = [pid for pid in owned if Path(f"/proc/{pid}").exists()]
                if owned:
                    time.sleep(0.05)
            for pid in owned:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass


if __name__ == "__main__":
    raise SystemExit(main())
