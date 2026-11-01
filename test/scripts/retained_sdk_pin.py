"""Read-only Nix admission controls using the actually pinned SDK product."""
from pathlib import Path
import json
import os
import hashlib
import shutil
import subprocess
import tempfile
import unittest
import argparse
import sys


ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "nix/retained-sdk.nix"
SDK_REFERENCE = None


class RetainedSdkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sdk = SDK_REFERENCE
        cls.descriptor = hashlib.sha256((cls.sdk / "artifact.json").read_bytes()).hexdigest()
        metadata = json.loads((cls.sdk / "artifact.json").read_text())
        cls.source = Path(metadata["source"])
        cls.image = Path(metadata["image"])
        cls.contract = json.loads((cls.sdk / "image/priv/android/native-contract.json").read_text())

    def evaluate(self, source, descriptor=None, sdk_source=None):
        return subprocess.run([
            "nix", "eval", "--impure", "--raw", "--file", str(HELPER),
            "--apply", 'f: f { sdk = builtins.getEnv "QUALIFIED_SDK"; '
            'sdkReference = builtins.getEnv "QUALIFIED_SDK"; '
            'sdkSource = builtins.getEnv "QUALIFIED_SDK_SOURCE"; '
            'source = builtins.getEnv "QUALIFIED_SOURCE"; '
            'descriptorSha256 = builtins.getEnv "QUALIFIED_DESCRIPTOR"; }',
        ], env={**os.environ, "QUALIFIED_SDK": str(self.sdk),
                "QUALIFIED_SDK_SOURCE": str(sdk_source or self.source),
                "QUALIFIED_SOURCE": str(source),
                "QUALIFIED_DESCRIPTOR": descriptor or self.descriptor},
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def private_source(self):
        temp = tempfile.TemporaryDirectory(prefix="qualified-sdk-source-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        names = ["native/lazy_memo/" + n for n in self.contract["source_files"]]
        names.append("priv/host/lazy_memo.bl")
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.source / name, target)
        self.assertEqual(self.evaluate(root).returncode, 0)
        return root

    def test_real_product_and_source_pass_but_wrong_descriptor_refuses(self):
        positive = self.evaluate(self.source)
        self.assertEqual(positive.returncode, 0, positive.stderr)
        self.assertEqual(positive.stdout.strip(), str(self.sdk))
        negative = self.evaluate(self.source, "0" * 64)
        self.assertNotEqual(negative.returncode, 0)
        self.assertIn("qualified artifact descriptor changed", negative.stderr)
        wrong_source = self.evaluate(self.source, sdk_source=self.sdk)
        self.assertNotEqual(wrong_source.returncode, 0)
        self.assertIn("SDK Source does not match", wrong_source.stderr)

    def test_actual_native_source_changes_additions_and_removals_refuse(self):
        source = self.private_source()
        member = source / "native/lazy_memo/src/lib.rs"
        original = member.read_bytes()
        member.write_bytes(original + b"\n// changed native Source\n")
        changed = self.evaluate(source)
        self.assertNotEqual(changed.returncode, 0)
        self.assertIn("Android native Source differ", changed.stderr)
        member.write_bytes(original)
        extra = source / "native/lazy_memo/src/new_member.rs"
        extra.write_text("// new native Source\n")
        self.assertNotEqual(self.evaluate(source).returncode, 0)
        extra.unlink()
        member.unlink()
        self.assertNotEqual(self.evaluate(source).returncode, 0)

    def test_actual_native_api_source_drift_refuses(self):
        source = self.private_source()
        facade = source / "priv/host/lazy_memo.bl"
        facade.write_bytes(facade.read_bytes() + b"\n; changed native API Source\n")
        result = self.evaluate(source)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("native API declarations differ", result.stderr)

    def test_pure_flake_uses_the_declared_input_context(self):
        temp = tempfile.TemporaryDirectory(prefix="qualified-sdk-flake-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        helper = root / "qualified.nix"
        original = HELPER.read_text()
        helper.write_text(original)
        (root / "flake.nix").write_text(
            '{ inputs.sdk = { url = "path:' + str(self.sdk) + '"; flake = false; }; '
            'inputs.source = { url = "path:' + str(self.source) + '"; flake = false; }; '
            'outputs = { self, sdk, source }: let verified = import ./qualified.nix { '
            'sdk = sdk.outPath; sdkReference = "' + str(self.sdk) + '"; '
            'sdkSource = source.outPath; source = source.outPath; descriptorSha256 = "'
            + self.descriptor + '"; }; in { verified = { path = verified; '
            'references = builtins.attrNames (builtins.getContext verified); }; }; }\n')
        command = ["nix", "eval", "--offline", "--no-write-lock-file", "--json",
                   "path:" + str(root) + "#verified"]
        current = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(current.returncode, 0, current.stderr)
        observed = json.loads(current.stdout)
        self.assertEqual(observed["path"], str(self.sdk))
        self.assertIn(str(self.sdk), observed["references"])
        before = 'selected = builtins.appendContext sdkReference { "${sdkReference}" = { path = true; }; };'
        self.assertEqual(original.count(before), 1)
        helper.write_text(original.replace(before,
            "selected = builtins.storePath sdkReference;"))
        historical = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertNotEqual(historical.returncode, 0)
        self.assertIn("not allowed in pure evaluation mode", historical.stderr)
        helper.write_text(original.replace(before, "selected = toString sdk;"))
        alias = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(alias.returncode, 0, alias.stderr)
        alias_result = json.loads(alias.stdout)
        self.assertNotEqual(alias_result["path"], str(self.sdk))
        self.assertNotIn(str(self.sdk), alias_result["references"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, required=True, help="existing genuine SDK selection")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    SDK_REFERENCE = args.sdk
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(RetainedSdkTest))
    if args.out:
        args.out.write_text(json.dumps({
            "status": "passed" if result.wasSuccessful() else "failed",
            "tests": result.testsRun,
            "sdk": str(SDK_REFERENCE),
            "descriptor_sha256": hashlib.sha256((SDK_REFERENCE / "artifact.json").read_bytes()).hexdigest(),
            "producer_sha256": hashlib.sha256(HELPER.read_bytes()).hexdigest(),
            "SDK_production_requested": False,
            "native_production_requested": False,
        }, indent=2) + "\n")
    sys.exit(0 if result.wasSuccessful() else 1)
