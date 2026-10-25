import contextlib
import io
import importlib.util
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts/test_prerequisites.py"
REQUIRE = runpy.run_path(str(GATE))["require"]
WATCHER = "test/bl/host_reload_watcher_test.bl"


def load(name, path):
    from importlib.machinery import SourceFileLoader
    loader = SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class Prerequisites(unittest.TestCase):
    def test_E63_actual_gate_refuses_missing_tool_and_source_mutant_accepts_it(self):
        with self.assertRaisesRegex(RuntimeError, "before VM startup.*inotifywait"):
            REQUIRE(ROOT, [WATCHER], platform="linux", path="")
        source = GATE.read_text()
        before, after = "    if missing:\n", "    if False and missing:\n"
        self.assertEqual(1, source.count(before))
        namespace = {"__file__": str(GATE)}
        exec(compile(source.replace(before, after), str(GATE), "exec"), namespace)
        admitted = namespace["require"](ROOT, [WATCHER], platform="linux", path="")
        self.assertEqual([{"test": WATCHER, "tool": "inotifywait", "executable": None}], admitted)

    def test_selected_tools_are_resolved_once_per_file_without_unrelated_requirements(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "inotifywait"
            executable.write_text("#!/bin/sh\nexit 0\n")
            executable.chmod(0o755)
            result = REQUIRE(ROOT, [WATCHER, WATCHER, "test/bl/reload/watcher_test.bl"],
                             platform="linux", path=directory)
            self.assertEqual([{"test": WATCHER, "tool": "inotifywait", "executable": str(executable)}], result)
        self.assertEqual([], REQUIRE(ROOT, [WATCHER], platform="darwin", path=""))
        with self.assertRaisesRegex(RuntimeError, "erl;.*erlc"):
            REQUIRE(ROOT, ["test/bl/datom/store_lock_test.bl"], platform="darwin", path="")

    def test_invalid_inventory_and_escaped_selection_refuse(self):
        with self.assertRaises(ValueError):
            REQUIRE(ROOT, ["../elsewhere_test.bl"], path="")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            manifest = root / "scripts/test-prerequisites.json"
            for data in [{"version": 2, "tests": {}},
                         {"version": 1, "tests": {"../outside": {"all": ["erl"]}}},
                         {"version": 1, "tests": {"test/a.bl": {"all": ["../erl"]}}},
                         {"version": 1, "tests": {"test/a.bl": {"linux": []}}}]:
                with self.subTest(data=data):
                    manifest.write_text(json.dumps(data))
                    with self.assertRaises(ValueError):
                        REQUIRE(root, ["test/a.bl"])

    def test_E63_ci_refuses_before_starting_the_user_manager(self):
        module = load("prerequisite_ci_shard", ROOT / "scripts/ci-test-shard.py")
        with patch.object(module, "partitions", return_value=[[WATCHER]]), \
                patch.object(sys, "argv", ["shard", "--index", "0", "--count", "1"]), \
                patch.dict(os.environ, {"PATH": ""}), patch.object(sys, "platform", "linux"), \
                patch.object(module.subprocess, "call") as launch, \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as errors:
            with self.assertRaises(SystemExit) as exit:
                module.main()
            self.assertEqual(2, exit.exception.code)
            self.assertIn("Missing test prerequisites before VM startup", errors.getvalue())
            launch.assert_not_called()

    def test_E63_candidate_refuses_before_receipts_or_candidate_start(self):
        module = load("prerequisite_candidate", ROOT / "scripts/qualify-candidate.py")
        with tempfile.TemporaryDirectory() as directory:
            results = Path(directory) / "not-created/results.jsonl"
            argv = ["qualify", "--candidate", str(GATE), "--results", str(results), WATCHER]
            with patch.object(module, "source_digest", return_value="source"), \
                    patch.object(sys, "argv", argv), patch.dict(os.environ, {"PATH": ""}), \
                    patch.object(sys, "platform", "linux"), patch.object(module.subprocess, "Popen") as launch, \
                    contextlib.redirect_stderr(io.StringIO()) as errors:
                with self.assertRaises(SystemExit) as exit:
                    module.main()
                self.assertEqual(2, exit.exception.code)
                self.assertIn("Missing test prerequisites before VM startup", errors.getvalue())
                self.assertFalse(results.parent.exists())
                launch.assert_not_called()

    def test_E63_history_refuses_before_freezing_or_starting_a_child(self):
        module = load("prerequisite_history", ROOT / "scripts/check-execution-history")
        case = {"id": "E63", "selectors": [{"path": WATCHER, "namespace": "watcher", "test": "real"}]}
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"PATH": ""}), \
                patch.object(sys, "platform", "linux"), patch.object(module, "capture") as freeze, \
                patch.object(module.subprocess, "run") as launch:
            output = Path(directory) / "not-created"
            with self.assertRaisesRegex(RuntimeError, "Missing test prerequisites before VM startup"):
                module.run(ROOT, ROOT / module.MANIFEST, [case], ["E63"], output, 30)
            self.assertFalse(output.exists())
            freeze.assert_not_called()
            launch.assert_not_called()

    def test_preflight_rejects_missing_or_drifted_bootstrap_consumers_before_vm_start(self):
        module = load("bootstrap_consumer_preflight", ROOT / "scripts/preflight-sdk-boundaries")
        original_loads, run = module.json.loads, module.subprocess.run

        def only_discovery(command, **kwargs):
            self.assertEqual("rg", command[0], "no candidate subprocess may start")
            return run(command, **kwargs)

        for edit in ["missing", "empty", "source", "consumer"]:
            def decode(text, *args, **kwargs):
                value = original_loads(text, *args, **kwargs)
                if isinstance(value, dict) and "external_writers" in value:
                    if edit == "missing":
                        value.pop("external_writers")
                    elif edit == "empty":
                        value["external_writers"] = []
                    elif edit == "source":
                        value["external_writers"][0]["source_sha256"] = "0" * 64
                    else:
                        value["external_writers"][0]["references"].pop()
                return value

            with self.subTest(edit=edit), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "not-created"
                argv = ["preflight", "--root", str(ROOT), "--out", str(output),
                        "--boundaries", "vector-lookup-default"]
                with patch.object(sys, "argv", argv), patch.object(module.json, "loads", side_effect=decode), \
                        patch.object(module.subprocess, "run", side_effect=only_discovery), \
                        contextlib.redirect_stderr(io.StringIO()) as errors:
                    with self.assertRaises(SystemExit) as exit:
                        module.main()
                    self.assertEqual(2, exit.exception.code)
                    self.assertRegex(errors.getvalue(), "bootstrap writer inventory|external writer source drift|external consumer map drift")
                    self.assertFalse(output.exists())

    def test_E63_preflight_refuses_after_mapping_before_freezing_or_starting_a_vm(self):
        module = load("prerequisite_preflight", ROOT / "scripts/preflight-sdk-boundaries")
        run = module.subprocess.run

        def only_discovery(command, **kwargs):
            self.assertEqual("rg", command[0], "no candidate subprocess may start")
            return run(command, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "not-created"
            argv = ["preflight", "--root", str(ROOT), "--out", str(output), "--boundaries", "native-custody"]
            with patch.object(sys, "argv", argv), patch.object(sys, "platform", "linux"), \
                    patch("shutil.which", return_value=None), \
                    patch.object(module.subprocess, "run", side_effect=only_discovery), \
                    contextlib.redirect_stderr(io.StringIO()) as errors:
                with self.assertRaises(SystemExit) as exit:
                    module.main()
                self.assertEqual(2, exit.exception.code)
                self.assertIn("Missing test prerequisites before VM startup", errors.getvalue())
                self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
