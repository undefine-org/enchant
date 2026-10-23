"""Refuse inconsistent compiler copies before launching a producer VM.

These filesystem-only negative controls use inert placeholder bytes. They never
start code or claim that a placeholder is a valid compiler artifact.
"""
import contextlib
import io
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
        for folder in ("scripts", "test/scripts", "priv/boot", "priv/bootstrap/seed"):
            (self.root / folder).mkdir(parents=True)
        shutil.copy2(SCRIPT, self.root / "scripts/qualify-artifact-generation")
        (self.root / "scripts/demo-artifact-production").write_text("BOOT = ''\n")
        (self.root / "scripts/check-source-floor").write_text("")
        (self.root / "test/scripts/artifact-generation.bl").write_text("nil\n")
        (self.root / "priv/boot/example.bl").write_text("(ns example)\n")
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

        def copytree(source, destination, *args, **kwargs):
            result = real_copytree(source, destination, *args, **kwargs)
            damage(Path(destination))
            return result

        with patch.object(sys, "argv", self.arguments), \
                patch.object(shutil, "copytree", side_effect=copytree), \
                patch.object(subprocess, "run", side_effect=self.run_without_native):
            self.assertEqual(1, self.module["main"]())
        self.assertFalse(self.native_started)
        report = (self.output / "result.json").read_text()
        self.assertIn("copied", report)
        self.assertIn('"self_reproduction_qualified": false', report)

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
