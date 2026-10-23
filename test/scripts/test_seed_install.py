"""Reject a real floor's changed bytes without modifying the installed image.

Run against a coherent checkout image, under the usual process-tree cap.
The candidate is data to the existing installer, never a code path for the VM.
"""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


def snapshot(directory):
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in directory.iterdir() if path.is_file()}


class SeedInstallationTest(unittest.TestCase):
    def test_changed_candidate_is_refused_before_any_installed_file_changes(self):
        installed = ROOT / "priv/bootstrap/seed"
        before = snapshot(installed)
        with tempfile.TemporaryDirectory(prefix="bl-rejected-seed-") as temporary:
            candidate = Path(temporary) / "seed"
            shutil.copytree(installed, candidate)
            beam = next(candidate.glob("*.beam"))
            # Retain its attributes and declared chunks; the complete-file
            # digest is nevertheless different from the genuine manifest.
            with beam.open("ab") as output:
                output.write(b"changed candidate bytes")
            result = subprocess.run([str(ROOT / "scripts/install-seed"), str(candidate)],
                                    cwd=ROOT, env=os.environ.copy(), text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=90)
        self.assertNotEqual(0, result.returncode, result.stdout)
        self.assertTrue(any(message in result.stdout for message in (
            "Generated floor no longer matches current sources",
            "Generated floor digest mismatch")), result.stdout)
        self.assertEqual(before, snapshot(installed))


if __name__ == "__main__":
    unittest.main()
