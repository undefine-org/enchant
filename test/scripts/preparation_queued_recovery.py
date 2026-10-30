#!/usr/bin/env python3
"""Real pre-claim worker loss and same-job recovery; main-thread execution only.

Use a retained native operation.json from preparation_lifecycle.py as --operation.
Exit 77 means the real queued window was not observed; it is not a passed test.
No producer hook or manufactured ledger outcome is used. All evidence/roots stay.
"""
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import re
import time

from preparation_lifecycle import Qualification, STORE, atomic_json, read_json, require


class QueuedWindowNotObserved(Exception):
    pass


def birth_ticks(pid):
    return int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19])


def tokens(pid):
    return Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")[:-1]


def sequence(actual, expected):
    expected = [os.fsencode(value) for value in expected]
    return any(actual[index:index + len(expected)] == expected for index in range(len(actual)))


def managed_unit(q, identifier):
    # identifier came from the sole real row in this fresh private job ledger;
    # it is not a constructed submission handle or a caller-selected service.
    name = "foundry-artifact-" + identifier + ".service"
    result = q.command([q.platform / "bin/systemctl", "--user", "show", name,
                        "--property=MainPID", "--property=InvocationID", "--property=ActiveState",
                        "--property=LoadState"], "queued-unit")
    fields = dict(line.split("=", 1) for line in result.stdout.decode().splitlines() if "=" in line)
    require("MainPID" in fields or fields.get("LoadState") == "not-found",
            "owned queued service cannot be observed")
    return fields


def belongs_to_unit(pid, identifier):
    components = re.split(r"[/\n]", Path(f"/proc/{pid}/cgroup").read_text())
    return "foundry-artifact-" + identifier + ".service" in components


def run(qualification, operation):
    q = qualification
    require(hasattr(os, "pidfd_open") and hasattr(signal, "pidfd_send_signal"),
            "exact PID cancellation control requires Linux pidfds")
    require(operation.get("version") == 1 and operation.get("kind") == "native"
            and set(operation) == {"version", "kind", "request"}, "fixed native operation required")
    request = operation["request"]
    require(request["version"] in (1, 2) and STORE.fullmatch(request["source"])
            and Path(request["source"]).is_dir(), "already retained immutable native input required")
    directory = q.output / "a"
    directory.mkdir(mode=0o700)
    atomic_json(directory / "operation.json", operation)
    state = str(directory / "foundry-state")
    expected_worker = q.runtime / "foundry/bin/jobs.bl"
    jobs = directory / "foundry-state/ledger/jobs"
    until = time.monotonic() + 80
    frozen = None
    descriptor = None
    observed_id = None
    path = None
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    submitting = pool.submit(q.call, "submit", directory)

    def accept_handle(timeout):
        accepted = submitting.result(timeout=timeout)
        require(accepted["directory"] == str(directory)
                and accepted["coordinator"] == str(q.runtime), "submit returned a foreign handle")
        if observed_id is not None:
            require(accepted["id"] == observed_id, "submit handle differs from observed real queued row")
        q.handles["a"] = accepted
        atomic_json(q.output / "handle.json", accepted)
        return accepted

    try:
        while time.monotonic() < until:
            try:
                candidates = list(jobs.iterdir())
            except FileNotFoundError:
                candidates = []
            candidates = [candidate for candidate in candidates if candidate.name.endswith(".json")]
            require(len(candidates) <= 1, "fresh private requester has multiple job rows")
            if not candidates:
                if submitting.done():
                    accept_handle(0)
                    raise QueuedWindowNotObserved("submit completed before queued ledger observation")
                time.sleep(0.005)
                continue
            path = candidates[0]
            info = path.lstat()
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                    and info.st_mode & 0o077 == 0 and info.st_size <= 1048576,
                    "queued observation requires one private bounded regular ledger row")
            row = read_json(path)
            observed_id = row["id"]
            require(re.fullmatch(r"job_[0-9a-f]{16}", observed_id)
                    and path.name == observed_id + ".json", "queued ledger identity differs from filename")
            if row["status"] != "queued":
                raise QueuedWindowNotObserved("worker claimed before a verified queued observation")
            # The queued ledger names the outer systemd-run client. The real
            # pre-claim BEAM is the owned unit's MainPID until it claims the row.
            unit = managed_unit(q, observed_id)
            pid = int(unit.get("MainPID", "0"))
            invocation = unit.get("InvocationID", "")
            if pid > 1 and invocation:
                try:
                    tick = birth_ticks(pid)
                    argv = tokens(pid)
                    executable = os.readlink(f"/proc/{pid}/exe")
                    environment = dict(part.split(b"=", 1) for part in
                                       Path(f"/proc/{pid}/environ").read_bytes().split(b"\0") if b"=" in part)
                    known = (Path(executable).name in ("beam.smp", "beam")
                             and Path(f"/proc/{pid}").stat().st_uid == os.getuid()
                             and belongs_to_unit(pid, observed_id)
                             and os.fsencode(expected_worker) in argv
                             and sequence(argv, ["--state", state, "worker", "--id", observed_id,
                                                 "--nonce", row["worker_nonce"]])
                             and environment.get(b"BL_PREPARATION_COORDINATOR") == os.fsencode(q.runtime)
                             and environment.get(b"FOUNDRY_ROOT") == os.fsencode(q.runtime / "foundry"))
                    if known:
                        submit_active = not submitting.done()
                        descriptor = os.pidfd_open(pid)
                        require(tick == birth_ticks(pid), "owned worker PID was reused")
                        signal.pidfd_send_signal(descriptor, signal.SIGSTOP)
                        frozen = pid
                        current = read_json(path)
                        if current["status"] != "queued":
                            raise QueuedWindowNotObserved("worker claimed before its exact PID was frozen")
                        require(current["id"] == observed_id and current["worker_nonce"] == row["worker_nonce"]
                                and tick == birth_ticks(pid) and tokens(pid) == argv
                                and belongs_to_unit(pid, observed_id),
                                "frozen owned worker identity changed")
                        q.evidence["queuedBeforeLoss"] = {"ledger": current,
                            "actualPid": pid, "actualStartTicks": tick, "observedDuringSubmit": submit_active,
                            "unit": unit,
                            "argv": [os.fsdecode(value) for value in argv]}
                        # The returned handle must be genuine. Freezing must not
                        # manufacture a handle or require the worker to claim.
                        try:
                            handle = accept_handle(15)
                        except concurrent.futures.TimeoutError:
                            raise QueuedWindowNotObserved("submit blocked while verified queued worker was frozen")
                        require(read_json(path)["status"] == "queued", "frozen worker unexpectedly claimed")
                        same_unit = managed_unit(q, observed_id)
                        require(int(same_unit.get("MainPID", "0")) == pid
                                and same_unit.get("InvocationID") == invocation
                                and tick == birth_ticks(pid) and tokens(pid) == argv
                                and belongs_to_unit(pid, observed_id),
                                "owned queued unit changed before exact PID loss")
                        signal.pidfd_send_signal(descriptor, signal.SIGKILL)
                        frozen = None
                        break
                except (FileNotFoundError, ProcessLookupError, PermissionError):
                    if descriptor is not None and frozen is None:
                        os.close(descriptor)
                        descriptor = None
            time.sleep(0.005)
        else:
            raise QueuedWindowNotObserved("verified pre-claim BEAM window was not observed during submit")
    finally:
        if frozen is not None and descriptor is not None:
            try:
                signal.pidfd_send_signal(descriptor, signal.SIGCONT)
            except ProcessLookupError:
                pass
        if descriptor is not None:
            os.close(descriptor)
        try:
            # Reap the actual submit caller, including skip/error paths. The
            # helper's own bounded timeout prevents an unbounded future wait.
            if "a" not in q.handles:
                accept_handle(110)
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
    # Wait for the owned launcher to observe the killed service. Never alter the
    # ledger to manufacture a lost PID, queued status or successful outcome.
    until = time.monotonic() + 30
    while time.monotonic() < until:
        row = read_json(path)
        require(row["status"] == "queued", "killed pre-claim worker changed the queued ledger outcome")
        recorded = row.get("worker_pid")
        if not recorded or not Path(f"/proc/{recorded}").exists():
            unit_after = managed_unit(q, observed_id)
            if int(unit_after.get("MainPID", "0")) == 0:
                q.evidence["unitAfterLoss"] = unit_after
                break
        time.sleep(0.1)
    lost = q.call("status", directory)
    require(lost["status"] == "queued" and lost["needsRecovery"] and not lost["workerAlive"],
            "real queued worker loss was not reported")
    recovered = q.call("recover", directory)
    require(recovered["id"] == handle["id"], "recovery created a different job")
    product = q.call("await", directory, 900000, timeout=950)
    require(product["operation"] == "native" and product["source"] == request["source"],
            "recovered native result identifies different inputs")
    output = Path(product["output"])
    require(STORE.fullmatch(str(output)), "recovered output is not immutable")
    manifest = read_json(output / "artifact.json")
    require(manifest["kind"] == "native-library"
            and all(manifest.get(key) == value for key, value in request.items()),
            "recovered manifest disagrees with accepted request")
    library = output / ("lib/" + request["crate"] + ".so")
    require(manifest["library"] == str(library.relative_to(output))
            and library.is_file() and not library.is_symlink()
            and hashlib.sha256(library.read_bytes()).hexdigest() == manifest["sha256"],
            "recovered native library bytes disagree")
    require(os.readlink(directory / "source-retained") == request["source"]
            and os.readlink(directory / "retained") == str(output), "recovered requester roots were lost")
    require(read_json(path)["id"] == handle["id"] and read_json(path)["status"] == "succeeded",
            "same durable job did not succeed")
    q.evidence.update({"passed": True, "lost": lost, "recovered": recovered,
                       "product": product, "manifest": manifest, "sameJob": handle["id"]})


def cleanup_queued_worker(q):
    for handle in q.handles.values():
        row = read_json(q.ledger_path(handle))
        pid, ticks = row.get("worker_pid"), row.get("worker_ticks")
        if row["status"] != "queued" or not isinstance(pid, int) or not isinstance(ticks, int):
            continue
        try:
            argv = tokens(pid)
            if (birth_ticks(pid) != ticks
                    or os.fsencode(q.runtime / "foundry/bin/jobs.bl") not in argv
                    or not sequence(argv, ["--state", str(Path(handle["directory"]) / "foundry-state"),
                                           "worker", "--id", handle["id"], "--nonce", row["worker_nonce"]])):
                continue
            descriptor = os.pidfd_open(pid)
            try:
                if birth_ticks(pid) == ticks:
                    signal.pidfd_send_signal(descriptor, signal.SIGKILL)
            finally:
                os.close(descriptor)
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--operation", required=True, type=Path)
    args = parser.parse_args()
    q = Qualification(args)
    code = 0
    try:
        run(q, read_json(args.operation))
    except QueuedWindowNotObserved as error:
        q.evidence.update({"passed": False, "status": "not-observed", "reason": str(error)})
        code = 77
    except BaseException as error:
        q.evidence.update({"passed": False, "status": "failed", "error": repr(error)})
        raise
    finally:
        try:
            cleanup_queued_worker(q)
        finally:
            q.cleanup()
    print(json.dumps({"status": "passed" if code == 0 else "not-observed",
                      "evidence": str(q.output / "evidence.json")}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
