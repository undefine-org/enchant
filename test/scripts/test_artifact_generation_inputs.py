"""Refuse inconsistent compiler copies before launching a producer VM.

These filesystem-only negative controls use inert placeholder bytes. They never
start code or claim that a placeholder is a valid compiler artifact.
"""
import contextlib
import io
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/qualify-artifact-generation"


class ArtifactGenerationInputsTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        for folder in ("scripts", "test/scripts", "priv/boot", "priv/bootstrap/seed", "priv/native"):
            (self.root / folder).mkdir(parents=True)
        shutil.copy2(SCRIPT, self.root / "scripts/qualify-artifact-generation")
        (self.root / "scripts/demo-artifact-production").write_text("BOOT = ''\n")
        (self.root / "scripts/check-source-floor").write_text("")
        (self.root / "test/scripts/artifact-generation.bl").write_text("nil\n")
        (self.root / "priv/boot/example.bl").write_text("(ns example)\n")
        (self.root / "priv/native/inert.so").write_bytes(b"inert native input, never loaded")
        (self.root / "env.bl").write_text("{}\n")
        self.seed = self.root / "priv/bootstrap/seed"
        (self.seed / "manifest.term").write_text("inert manifest placeholder\n")
        (self.seed / "Elixir.Probe.beam").write_bytes(b"inert artifact placeholder")
        self.output = self.root / "result"
        self.module = runpy.run_path(str(self.root / "scripts/qualify-artifact-generation"))
        self.arguments = [str(SCRIPT), "--root", str(self.root), "--seed", str(self.seed),
                          "--out", str(self.output)]
        self.native_started = False
        self.real_run = subprocess.run

    def run_without_native(self, command, *args, **kwargs):
        if command[0] == "cp":
            return self.real_run(command, *args, **kwargs)
        self.native_started = True
        raise AssertionError("a producer VM must not start for inconsistent inputs")

    def assert_copy_refused(self, damage):
        real_copytree = shutil.copytree
        diagnostic = io.StringIO()

        def copytree(source, destination, *args, **kwargs):
            result = real_copytree(source, destination, *args, **kwargs)
            damage(Path(destination))
            return result

        with contextlib.redirect_stderr(diagnostic), \
                patch.object(sys, "argv", self.arguments), \
                patch.object(shutil, "copytree", side_effect=copytree), \
                patch.object(subprocess, "run", side_effect=self.run_without_native):
            self.assertEqual(1, self.module["main"]())
        self.assertFalse(self.native_started)
        report = (self.output / "result.json").read_text()
        self.assertIn("copied", report)
        self.assertIn('"self_reproduction_qualified": false', report)
        self.assertIn("ARTIFACT-GENERATION FAILED:", diagnostic.getvalue())
        self.assertIn("copied", diagnostic.getvalue())

    def test_compiler_copy_corruption_refuses_even_when_original_is_unchanged(self):
        before = (self.seed / "Elixir.Probe.beam").read_bytes()

        def damage(destination):
            if destination.parts[-3:] == ("priv", "bootstrap", "seed"):
                (destination / "Elixir.Probe.beam").write_bytes(b"changed copy")

        self.assert_copy_refused(damage)
        self.assertEqual(before, (self.seed / "Elixir.Probe.beam").read_bytes())

    def test_application_code_copy_is_checked_independently(self):
        def damage(destination):
            if destination.name == "ebin":
                (destination / "Elixir.Probe.beam").write_bytes(b"changed code path")

        self.assert_copy_refused(damage)

    def test_copied_source_is_checked_before_code_starts(self):
        def damage(destination):
            if destination.name == "ebin":
                image = destination.parents[3]
                (image / "priv/boot/example.bl").write_text("(ns changed)\n")

        self.assert_copy_refused(damage)

    def test_copied_native_product_is_checked_before_code_starts(self):
        def damage(destination):
            if destination.name == "ebin":
                image = destination.parents[3]
                (image / "priv/native/inert.so").write_bytes(b"changed native copy")

        self.assert_copy_refused(damage)

    def run_staged_fixture(self, *, mismatch=False, fail_preparation=False):
        """Inert artifacts test orchestration only; no BEAM validity is claimed."""
        calls = []
        previous = (self.seed / "Elixir.Probe.beam").read_bytes()

        def run(command, *args, **kwargs):
            nonlocal previous
            if command[0] == "cp":
                return self.real_run(command, *args, **kwargs)
            if command[0] == "elixir":
                env = kwargs["env"]
                target = Path(env["BL_GENERATION_OUTPUT"])
                label = target.name
                image = Path(kwargs["cwd"])
                self.assertEqual(previous, (image / "priv/bootstrap/seed/Elixir.Probe.beam").read_bytes())
                calls.append(("produce", label))
                target.mkdir()
                payload = b"preparation" if label == "P" else b"current"
                if mismatch and label == "C":
                    payload = b"different"
                (target / "Elixir.Probe.beam").write_bytes(payload)
                (target / "manifest.term").write_bytes(b"inert manifest")
                Path(env["BL_GENERATION_BOOTSTRAP_RECEIPT"]).write_text("{}")
                previous = payload
                return subprocess.CompletedProcess(command, 0, "")
            self.assertEqual("python3", command[0])
            label = Path(command[command.index("--seed") + 1]).name
            calls.append(("boot", label))
            return subprocess.CompletedProcess(command, int(fail_preparation and label == "P"), "")

        diagnostic = io.StringIO()
        with patch.object(sys, "argv", self.arguments), \
                patch.object(subprocess, "run", side_effect=run), \
                contextlib.redirect_stderr(diagnostic), contextlib.redirect_stdout(io.StringIO()):
            result = self.module["main"]()
        return result, json.loads((self.output / "result.json").read_text()), calls, diagnostic.getvalue()

    def test_preparation_is_separate_from_exact_two_generation_reproduction(self):
        result, report, calls, _ = self.run_staged_fixture()
        self.assertEqual(0, result)
        self.assertEqual([(kind, stage) for stage in ("P", "B", "C")
                          for kind in ("produce", "boot")], calls)
        self.assertTrue(report["preparation"]["fresh_boot_qualified"])
        self.assertEqual(["B", "C"], [stage["generation"] for stage in report["stages"]])
        self.assertNotEqual(report["preparation"]["files"], report["stages"][0]["files"])
        self.assertTrue(report["self_reproduction_qualified"])

    def test_preparation_does_not_excuse_a_b_c_difference(self):
        result, report, _, diagnostic = self.run_staged_fixture(mismatch=True)
        self.assertEqual(1, result)
        self.assertFalse(report["self_reproduction_qualified"])
        self.assertEqual(["Elixir.Probe.beam"], report["changed_files"])
        self.assertIn("B and C differ", diagnostic)

    def test_preparation_boot_failure_stops_before_reproduction(self):
        result, report, calls, diagnostic = self.run_staged_fixture(fail_preparation=True)
        self.assertEqual(1, result)
        self.assertEqual([("produce", "P"), ("boot", "P")], calls)
        self.assertFalse(report["preparation"]["fresh_boot_qualified"])
        self.assertEqual([], report["stages"])
        self.assertFalse(report["self_reproduction_qualified"])
        self.assertIn("generation P fresh boot failed", diagnostic)

    def assert_seed_rejected(self):
        with patch.object(sys, "argv", self.arguments), \
                patch.object(subprocess, "run", side_effect=self.run_without_native), \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                self.module["main"]()
        self.assertEqual(2, error.exception.code)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.native_started)

    def test_untracked_recording_is_not_a_compiler_input(self):
        (self.seed / "recording.webm").write_bytes(b"recording")
        self.assert_seed_rejected()

    def test_symlink_is_not_a_regular_compiler_input(self):
        (self.seed / "linked.beam").symlink_to(self.seed / "Elixir.Probe.beam")
        self.assert_seed_rejected()


if __name__ == "__main__":
    unittest.main()
