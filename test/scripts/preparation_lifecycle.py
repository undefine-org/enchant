#!/usr/bin/env python3
"""Real coordinator isolation qualification. Execute only in the main session.

Usage: preparation_lifecycle.py --runtime STORE --platform STORE --output DIR
The caller supplies the memory/time cap. This script creates only its own units,
never runs global GC, and preserves requester ledgers/roots as evidence.
"""
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid

STORE = re.compile(r"/nix/store/[0-9a-z]{32}-[^/]+\Z")


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def atomic_json(path, value):
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(value, stream, separators=(",", ":"))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def read_json(path):
    return json.loads(path.read_text())


def patch_owned_ledger(path, fields):
    """Use Foundry's actual PID lock convention for an owned ledger mutation."""
    lock = path.parent.parent / ".lock"
    until = time.monotonic() + 30
    while True:
        try:
            descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            break
        except FileExistsError:
            require(time.monotonic() < until, "owned Foundry ledger mutex stayed busy")
            time.sleep(0.01)
    stamp = os.fstat(descriptor)
    try:
        os.write(descriptor, str(os.getpid()).encode())
        os.close(descriptor)
        current = read_json(path)
        original = {key: current[key] for key in fields}
        current.update(fields)
        atomic_json(path, current)
        return original
    finally:
        observed = lock.lstat()
        require((stamp.st_dev, stamp.st_ino) == (observed.st_dev, observed.st_ino),
                "owned ledger mutex identity changed")
        lock.unlink()


class Qualification:
    def __init__(self, args):
        self.runtime = Path(args.runtime).resolve(strict=True)
        self.platform = Path(args.platform).resolve(strict=True)
        for path in (self.runtime, self.platform):
            require(STORE.fullmatch(str(path)), "qualified immutable store runtime/platform required")
        self.output = Path(args.output).absolute()
        self.output.mkdir(mode=0o700, parents=True, exist_ok=False)
        self.token = uuid.uuid4().hex
        self.handles = {}
        self.waiter = None
        self.waiter_unit = "bl-preparation-await-" + self.token + ".service"
        self.forged_original = None
        self.evidence = {}
        self.env = dict(os.environ, BL_PREPARATION_COORDINATOR=str(self.runtime))

    def command(self, argv, label, timeout=100):
        result = subprocess.run([str(a) for a in argv], env=self.env, capture_output=True,
                                timeout=timeout, check=False)
        prefix = self.output / (label + "-" + uuid.uuid4().hex)
        prefix.with_suffix(".stdout").write_bytes(result.stdout)
        prefix.with_suffix(".stderr").write_bytes(result.stderr)
        return result

    def argv(self, mode, directory, *arguments):
        return [self.runtime / "bin/bl", "--cold", "run",
                self.runtime / "foundry/bin/preparation-operation.bl", "--", mode,
                directory, *map(str, arguments)]

    def call(self, mode, directory, *arguments, timeout=100):
        result = self.command(self.argv(mode, directory, *arguments), mode, timeout)
        require(result.returncode == 0,
                f"{mode} exited {result.returncode}: {result.stderr[-8192:].decode(errors='replace')}")
        envelope = json.loads(result.stdout)
        require(result.returncode == 0 and envelope.get("ok") is True,
                f"{mode} refused: {envelope}")
        return envelope["value"]

    def unit(self, handle):
        name = "foundry-artifact-" + handle["id"] + ".service"
        result = self.command([self.platform / "bin/systemctl", "--user", "show", name,
                               "--property=MainPID", "--property=ActiveState", "--property=InvocationID"], "unit")
        fields = dict(line.split("=", 1) for line in result.stdout.decode().splitlines() if "=" in line)
        require("MainPID" in fields, "cannot inspect owned worker service")
        return fields

    def ledger_path(self, handle):
        return Path(handle["directory"]) / "foundry-state/ledger/jobs" / (handle["id"] + ".json")

    def wait_running(self, deadline=180):
        until = time.monotonic() + deadline
        while time.monotonic() < until:
            rows = {key: read_json(self.ledger_path(handle)) for key, handle in self.handles.items()}
            if all(row["status"] == "running" for row in rows.values()) and all(
                    (Path(handle["directory"]) / "source-retained").is_symlink()
                    for handle in self.handles.values()):
                units = {key: self.unit(handle) for key, handle in self.handles.items()}
                if all(int(units[key].get("MainPID", "0")) == row.get("worker_pid")
                       and row.get("worker_ticks") and row.get("worker_nonce")
                       for key, row in rows.items()):
                    self.evidence["running"] = {"rows": rows, "units": units}
                    return rows
            require(all(row["status"] not in ("failed", "interrupted", "cancelled", "succeeded")
                        for row in rows.values()), "fixture settled before concurrent-running observation")
            time.sleep(0.5)
        raise AssertionError("both actual worker identities did not become running")

    def restore_a(self):
        if self.forged_original is not None:
            path = self.ledger_path(self.handles["a"])
            patch_owned_ledger(path, self.forged_original)
            self.forged_original = None

    def run(self):
        fixture = self.output / "fixture"
        fixture.mkdir(mode=0o700)
        (fixture / "src").mkdir()
        (fixture / "Cargo.toml").write_text('[package]\nname="lifecycle-probe"\nversion="0.1.0"\nedition="2021"\nbuild="build.rs"\n[lib]\nname="lifecycle_probe"\ncrate-type=["cdylib"]\n')
        (fixture / "Cargo.lock").write_text('version = 4\n[[package]]\nname = "lifecycle-probe"\nversion = "0.1.0"\n')
        (fixture / "src/lib.rs").write_text('#[no_mangle]\npub extern "C" fn answer() -> u64 { 42 }\n// ' + self.token + '\n')
        (fixture / "build.rs").write_text('fn main() { std::thread::sleep(std::time::Duration::from_secs(90)); }\n')
        snapshot_root = self.output / "snapshot-retained"
        snapshot = self.command([self.platform / "bin/nix", "build", "--impure", "--file",
                                 self.platform / "nix/native-snapshot.nix", "--argstr", "source", fixture,
                                 "--argstr", "crate", "lifecycle_probe", "--arg", "version", "2",
                                 "--argstr", "member", ".", "--argstr", "package", "lifecycle-probe",
                                 "--json", "--out-link", snapshot_root, "--max-jobs", "0"], "snapshot", 600)
        require(snapshot.returncode == 0, "rooted fixture snapshot failed")
        rows = json.loads(snapshot.stdout)
        require(len(rows) == 1, "snapshot returned multiple products")
        source = rows[0]["outputs"]["out"]
        require(STORE.fullmatch(source) and os.readlink(snapshot_root) == source,
                "snapshot did not retain immutable fixture")
        request = {"version": 2, "source": source, "member": ".", "package": "lifecycle-probe",
                   "crate": "lifecycle_probe", "abi": "lifecycle-v1", "target": "x86_64-linux"}
        operation = {"version": 1, "kind": "native", "request": request}
        directories = {key: self.output / key for key in ("a", "b")}
        for directory in directories.values():
            directory.mkdir(mode=0o700)
            atomic_json(directory / "operation.json", operation)
        # At most two cold coordinator VMs at once, only for this admission race.
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.call, "submit", directories["a"]) for _ in range(2)]
            handles = [future.result() for future in futures]
        require(handles[0] == handles[1], "identical concurrent submissions produced different jobs")
        self.handles["a"] = handles[0]
        self.handles["b"] = self.call("submit", directories["b"])
        require(self.handles["a"]["id"] != self.handles["b"]["id"], "requester jobs were merged")
        atomic_json(self.output / "handles.json", self.handles)
        running = self.wait_running()
        a_path = self.ledger_path(self.handles["a"])
        fields = ("worker_pid", "worker_ticks", "worker_nonce")
        self.forged_original = patch_owned_ledger(a_path, {field: running["b"][field] for field in fields})
        forged = self.call("cancel", directories["a"])
        require(forged["needsRecovery"] and not read_json(a_path)["cancel_requested"],
                "forged foreign worker identity authorized cancellation")
        require(int(self.unit(self.handles["b"])["MainPID"]) == running["b"]["worker_pid"],
                "foreign worker service stopped")
        self.evidence["forgedCancellation"] = forged
        self.restore_a()
        cancelled = self.call("cancel", directories["a"])
        require(cancelled["status"] in ("interrupted", "cancelled"), "owned cancellation did not settle")
        require(int(self.unit(self.handles["a"]).get("MainPID", "0")) == 0,
                "cancelled owned service still has a MainPID")
        require(int(self.unit(self.handles["b"])["MainPID"]) == running["b"]["worker_pid"],
                "independent requester was cancelled")
        require((directories["a"] / "source-retained").is_symlink(), "cancel removed owned source root")
        require(snapshot_root.is_symlink(), "cancel removed snapshot root")
        self.evidence["genuineCancellation"] = cancelled
        # A killed observer is separate from the worker and must not cancel it.
        waiter_stdout = open(self.output / "abandoned-await.stdout", "wb")
        waiter_stderr = open(self.output / "abandoned-await.stderr", "wb")
        try:
            self.waiter = subprocess.Popen([str(self.platform / "bin/systemd-run"), "--user", "--quiet",
                "--wait", "--collect", "--pipe", "--unit=" + self.waiter_unit,
                "--property=MemoryMax=1G", "--property=MemorySwapMax=0", "--property=RuntimeMaxSec=365",
                "--property=KillMode=control-group", "--", *map(str, self.argv("await", directories["b"], 300000))],
                env=self.env, stdout=waiter_stdout, stderr=waiter_stderr)
            time.sleep(2)
            stopped = self.command([self.platform / "bin/systemctl", "--user", "stop", self.waiter_unit], "stop-observer")
            require(stopped.returncode == 0, "owned await observer could not be stopped")
            self.waiter.wait(timeout=30)
        finally:
            waiter_stdout.close()
            waiter_stderr.close()
        require(int(self.unit(self.handles["b"])["MainPID"]) == running["b"]["worker_pid"],
                "observer death stopped durable worker")
        deletion = self.command([self.platform / "bin/nix-store", "--delete", source], "selective-delete", 100)
        reason = (deletion.stdout + deletion.stderr).decode(errors="replace").lower()
        require(deletion.returncode != 0 and Path(source).is_dir()
                and any(word in reason for word in ("alive", "root", "cannot delete")),
                "selective deletion did not demonstrate rooted source protection")
        product = self.call("await", directories["b"], 900000, timeout=950)
        output = Path(product["output"])
        require(STORE.fullmatch(str(output)), "native output is not immutable")
        manifest = read_json(output / "artifact.json")
        require(manifest["version"] == 2 and manifest["kind"] == "native-library"
                and all(manifest.get(key) == request[key] for key in request if key != "version")
                and manifest["library"] == "lib/lifecycle_probe.so", "native manifest identity disagrees")
        library = output / manifest["library"]
        require(library.is_file() and not library.is_symlink(), "native output library is not regular")
        digest = hashlib.sha256(library.read_bytes()).hexdigest()
        require(digest == manifest["sha256"], "native SHA differs")
        compiled = Path(manifest["compiled"])
        require(STORE.fullmatch(str(compiled)), "compiled native provenance is not immutable")
        cargo_library = manifest["cargoLibrary"]
        require(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", cargo_library), "invalid Cargo library provenance")
        original = compiled / "lib" / (cargo_library + ".so")
        require(original.is_file() and not original.is_symlink()
                and hashlib.sha256(original.read_bytes()).hexdigest() == digest,
                "Cargo product provenance or bytes disagree")
        require(manifest["toolchain"]["name"] == "rustc"
                and re.fullmatch(r"[0-9a-f]{64}", manifest["toolchain"]["identity"]),
                "native toolchain closure missing")
        require(os.readlink(directories["b"] / "retained") == str(output), "successful output root differs")
        # Cancellation cannot delete any root that existed at cancellation time.
        require((directories["a"] / "source-retained").is_symlink(), "late cleanup removed cancelled roots")
        self.evidence.update({"product": product, "manifest": manifest, "source": source,
                              "observerReconnected": True, "rootDeletionRefused": True})
        return self.evidence

    def cleanup(self):
        errors = []
        # A submit may have persisted its handle before its caller failed. Only
        # adopt handles under the two exact private directories created here.
        for key in ("a", "b"):
            try:
                path = self.output / key / "handle.json"
                if key not in self.handles and path.is_file() and not path.is_symlink():
                    handle = read_json(path)
                    if (handle.get("directory") == str(self.output / key)
                            and handle.get("coordinator") == str(self.runtime)
                            and re.fullmatch(r"job_[0-9a-f]{16}", handle.get("id", ""))):
                        self.handles[key] = handle
            except Exception as error:
                errors.append(repr(error))
        try:
            self.restore_a()
        except Exception as error:
            errors.append(repr(error))
        units = [self.waiter_unit] + ["foundry-artifact-" + handle["id"] + ".service"
                                     for handle in self.handles.values()]
        for unit in units:
            try:
                # Names belong only to this harness's private requester jobs.
                self.command([self.platform / "bin/systemctl", "--user", "stop", unit], "cleanup-unit")
            except Exception as error:
                errors.append(repr(error))
        if self.waiter is not None:
            try:
                self.waiter.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.waiter.terminate()
                try:
                    self.waiter.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.waiter.kill()
                    self.waiter.wait(timeout=10)
        if errors:
            self.evidence.update({"passed": False, "cleanupErrors": errors})
        atomic_json(self.output / "evidence.json", self.evidence)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--output", required=True, help="new private evidence directory; retained after completion")
    args = parser.parse_args()
    qualification = Qualification(args)
    try:
        result = qualification.run()
        result["passed"] = True
        print(json.dumps({"passed": True, "evidence": str(qualification.output / "evidence.json")}))
    except BaseException as error:
        qualification.evidence.update({"passed": False, "error": repr(error)})
        raise
    finally:
        qualification.cleanup()


if __name__ == "__main__":
    main()
