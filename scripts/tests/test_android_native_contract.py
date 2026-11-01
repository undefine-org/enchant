"""Native/SDK compatibility changes when source or exported declarations change."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("android_native_contract", ROOT / "nix/android-native-contract.py")
CONTRACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTRACT)


class AndroidNativeContractTests(unittest.TestCase):
    def test_sdk_contract_tracks_native_source_and_interface_independently(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(ROOT / "native/lazy_memo", root / "native/lazy_memo",
                            ignore=shutil.ignore_patterns("target"))
            (root / "priv/host").mkdir(parents=True)
            facade = root / "priv/host/lazy_memo.bl"
            shutil.copy2(ROOT / "priv/host/lazy_memo.bl", facade)
            original = CONTRACT.contract(root)
            self.assertIn(["nif_runtime_identity", 0], original["nifs"])
            self.assertIn(["nif_file_claim_owned", 3], original["nifs"])
            # Ordinary facade implementation changes preserve native identity.
            facade.write_text(facade.read_text() + "\n; runtime policy comment\n")
            self.assertEqual(original, CONTRACT.contract(root))
            facade.write_text(facade.read_text().replace("(defn nif_file_unlock [handle]",
                                                       "(defn nif_file_unlock [handle scope]"))
            interface_changed = CONTRACT.contract(root)
            self.assertEqual(original["source_sha256"], interface_changed["source_sha256"])
            self.assertNotEqual(original["nifs"], interface_changed["nifs"])
            source = root / "native/lazy_memo/src/lib.rs"
            source.write_text(source.read_text() + "\n// changed native implementation\n")
            self.assertNotEqual(original["source_sha256"], CONTRACT.contract(root)["source_sha256"])
            # Paths are relative, so store relocation never changes identity.
            moved = root / "relocated"
            shutil.copytree(root / "native", moved / "native")
            shutil.copytree(root / "priv", moved / "priv")
            self.assertEqual(CONTRACT.contract(root), CONTRACT.contract(moved))

    def test_missing_native_declarations_refuse_a_compatibility_claim(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(ROOT / "native/lazy_memo", root / "native/lazy_memo",
                            ignore=shutil.ignore_patterns("target"))
            (root / "priv/host").mkdir(parents=True)
            (root / "priv/host/lazy_memo.bl").write_text("(ns host.lazy-memo)\n")
            with self.assertRaisesRegex(ValueError, "missing or duplicate"):
                CONTRACT.contract(root)
