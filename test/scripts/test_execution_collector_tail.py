"""E50: actual native worker, calibrated resources and producer-root lifetime.

Both private builds have the same post-round barrier. The sole causal change
disables arming the delayed follow-up. No production library is overwritten.
Run inside a capped process tree; private inputs/products/logs are retained.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[2]
BEFORE = "settling = true;"
AFTER = "settling = false;"
ANCHOR = """                if SCHEDULE.finish_round(live, crate::accounted_retained_bytes()) {
                    wake();
                }
"""
HOOK = """                if let Ok(directory) = std::env::var("BL_HISTORY_COLLECTOR_BARRIER") {
                    let directory = std::path::Path::new(&directory);
                    let finished = directory.join("round-finished");
                    if !finished.exists() {
                        std::fs::write(&finished, b"round completed").unwrap();
                        while !directory.join("continue").exists() {
                            std::thread::sleep(std::time::Duration::from_millis(1));
                        }
                    }
                }
"""


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inputs(root):
    crate = root / "native/lazy_memo"
    paths = list((crate / "src").rglob("*.rs")) + list((crate / "fixtures").rglob("*"))
    paths += [crate / name for name in ["Cargo.toml", "Cargo.lock", "build.rs"]]
    return {str(p.relative_to(root)): digest(p) for p in paths if p.is_file()}


class CollectorTailControls(unittest.TestCase):
    def test_E50_last_producer_requires_the_actual_delayed_native_followup(self):
        root = Path(os.environ.get("BL_TEST_SOURCE_ROOT", ROOT)).resolve()
        hosts = {name: Path(value) for name, value in json.loads(os.environ["BL_COLLECTOR_HOSTS"]).items()}
        self.assertEqual({"memo", "tiers", "app"}, set(hosts))
        frozen = inputs(root)
        host_hashes = {name: digest(path) for name, path in hosts.items()}
        source = (root / "native/lazy_memo/src/collector.rs").read_text()
        self.assertEqual(1, source.count(ANCHOR))
        self.assertEqual(1, source.count(BEFORE))
        output = root / ".local/execution" / ("collector-tail-control-" + uuid.uuid4().hex)
        output.mkdir(parents=True)
        print("E50 retained evidence: " + str(output), flush=True)
        (output / "inputs.json").write_text(json.dumps({"native": frozen, "hosts": host_hashes}, indent=2))
        target = output / "target"
        if (root / "native/lazy_memo/target").is_dir():
            shutil.copytree(root / "native/lazy_memo/target", target)
        results = {}
        for mode in ["good", "no-followup"]:
            directory = output / mode
            crate = directory / "crate"
            shutil.copytree(root / "native/lazy_memo", crate,
                            ignore=shutil.ignore_patterns("target", ".git"))
            modified = source.replace(ANCHOR, ANCHOR + HOOK)
            if mode == "no-followup":
                modified = modified.replace(BEFORE, AFTER)
            (crate / "src/collector.rs").write_text(modified)
            env = dict(os.environ, CARGO_TARGET_DIR=str(target))
            with (directory / "build.log").open("w") as log:
                built = subprocess.run(["cargo", "build", "--offline", "--release", "--manifest-path",
                                        str(crate / "Cargo.toml"), "-j", "2"],
                                       cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=120)
            self.assertEqual(0, built.returncode, (directory / "build.log").read_text())
            app = directory / "beam_lisp-0.1.0"
            ebin, native = app / "ebin", app / "priv/native"
            ebin.mkdir(parents=True)
            native.mkdir(parents=True)
            for path in hosts.values():
                shutil.copy2(path, ebin / path.name)
            library = native / "lazy_memo.so"
            shutil.copy2(target / "release/liblazy_memo.so", library)
            barrier = directory / "barrier"
            barrier.mkdir()
            env = dict(os.environ, BL_ROOT=str(app), BL_HISTORY_COLLECTOR_BARRIER=str(barrier),
                       BL_HISTORY_COLLECTOR_MODE=mode)
            env.pop("BEAM_LISP_PATH", None)
            child = subprocess.run(["elixir", "--erl", "+S 2:2 +SDcpu 1:1 +SDio 1", "-pa", str(ebin),
                                    str(root / "test/scripts/execution-collector-tail.exs")],
                                   cwd=directory, env=env, text=True, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, timeout=30)
            (directory / "child.log").write_text(child.stdout)
            self.assertEqual(0, child.returncode, child.stdout)
            self.assertEqual(1, child.stdout.splitlines().count("E50-NATIVE-TAIL-PASSED " + mode))
            lines = [line.split() for line in child.stdout.splitlines() if line.startswith("E50-RESULT ")]
            self.assertEqual(1, len(lines))
            self.assertEqual(8, len(lines[0]))
            _, seen, before, held, after, runs, collected, identity = lines[0]
            self.assertEqual(mode, seen)
            self.assertRegex(identity, r"^[0-9a-f]{64}$")
            results[mode] = dict(zip(["before", "held", "after", "runs", "collected"],
                                     map(int, [before, held, after, runs, collected])),
                                 native_identity=identity, library_sha256=digest(library))
        good, bad = results["good"], results["no-followup"]
        self.assertEqual((2, 2), (good["runs"], good["collected"]))
        self.assertEqual((1, 0), (bad["runs"], bad["collected"]))
        self.assertEqual(good["before"], good["after"])
        self.assertEqual(bad["held"], bad["after"])
        self.assertGreater(bad["after"] - bad["before"], 16 * 1024 * 1024)
        self.assertNotEqual(good["native_identity"], bad["native_identity"])
        self.assertEqual(frozen, inputs(root))
        self.assertEqual(host_hashes, {name: digest(path) for name, path in hosts.items()})
        (output / "result.json").write_text(json.dumps({"status": "passed", "results": results}, indent=2))
        print("E50 native results: " + json.dumps(results), flush=True)
