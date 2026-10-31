"""Adversarial publication checks against a real application product."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("inventory", ROOT / "nix/application-inventory.py")
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)
PRODUCT = Path(sys.argv.pop()) if len(sys.argv) == 2 else None


@unittest.skipUnless(PRODUCT is not None, "pass an actual Nix application output")
class ApplicationInventory(unittest.TestCase):
    def test_rejects_tampering_missing_additional_entries_and_wrong_identity(self):
        descriptor = json.loads((PRODUCT / "artifact.json").read_text())
        sdk, source = descriptor["sdk"], descriptor["source"]
        self.assertFalse(inventory.verify(PRODUCT, sdk, source)["errors"])
        with self.assertRaisesRegex(ValueError, "identity"):
            inventory.verify(PRODUCT, sdk + "-different", source)
        with tempfile.TemporaryDirectory(prefix="bl-application-inventory-") as temporary:
            copied = Path(temporary) / "product"
            shutil.copytree(PRODUCT, copied, symlinks=True)
            copied.chmod(copied.stat().st_mode | 0o200)
            for path in copied.rglob("*"):
                if not path.is_symlink():
                    path.chmod(path.stat().st_mode | 0o200)
            beam = next((copied / "units").rglob("*.beam"))
            original = beam.read_bytes()
            beam.write_bytes(original + b"tampered")
            with self.assertRaisesRegex(ValueError, "inventory"):
                inventory.verify(copied, sdk, source)
            beam.write_bytes(original)
            beam.unlink()
            with self.assertRaisesRegex(ValueError, "inventory"):
                inventory.verify(copied, sdk, source)
            beam.write_bytes(original)
            # Restore the original executable bit after recreating the file.
            beam.chmod((PRODUCT / beam.relative_to(copied)).stat().st_mode | 0o200)
            added = copied / "unrecorded.beam"
            added.write_bytes(b"unexpected")
            with self.assertRaisesRegex(ValueError, "inventory"):
                inventory.verify(copied, sdk, source)
            added.unlink()
            beam.unlink()
            beam.symlink_to("/etc/passwd")
            with self.assertRaisesRegex(ValueError, "unsupported product link"):
                inventory.verify(copied, sdk, source)


if __name__ == "__main__":
    unittest.main()
