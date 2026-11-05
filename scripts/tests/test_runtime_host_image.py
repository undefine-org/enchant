"""Private host-check images must be editable without altering SDK symlinks."""
from pathlib import Path
import runpy
import tempfile
import unittest

CHECKER = runpy.run_path(str(Path(__file__).resolve().parents[1] / "check-runtime-hosts"))


class RuntimeHostImageTests(unittest.TestCase):
    def test_read_only_inputs_become_owned_writable_copies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "source", root / "image"
            source.mkdir()
            (source / "metadata").write_bytes(b"original")
            (source / "metadata").chmod(0o444)
            source.chmod(0o555)
            try:
                CHECKER["writable_copy"](source, output)
                (output / "metadata").write_bytes(b"edited")
                (output / "new").write_bytes(b"owned")
                self.assertEqual(b"original", (source / "metadata").read_bytes())
                self.assertEqual(0o444, (source / "metadata").stat().st_mode & 0o777)
            finally:
                source.chmod(0o755)

    def test_native_symlinks_keep_their_external_targets_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output, external = root / "source", root / "image", root / "native"
            source.mkdir()
            external.mkdir()
            library = external / "runtime.so"
            library.write_bytes(b"immutable")
            library.chmod(0o444)
            external.chmod(0o555)
            (source / "native").symlink_to(external, target_is_directory=True)
            (source / "runtime.so").symlink_to(library)
            try:
                CHECKER["writable_copy"](source, output)
                self.assertTrue((output / "native").is_symlink())
                self.assertTrue((output / "runtime.so").is_symlink())
                self.assertEqual(0o555, external.stat().st_mode & 0o777)
                self.assertEqual(0o444, library.stat().st_mode & 0o777)
                self.assertEqual(b"immutable", library.read_bytes())
            finally:
                external.chmod(0o755)
