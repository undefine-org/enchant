"""Transport contracts: preserve identities, refuse SDK links and binary exports."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('ci_receipt', Path(__file__).resolve().parents[2] / 'scripts/ci-receipt.py')
RECEIPT = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RECEIPT)


class ReceiptContracts(unittest.TestCase):
    def test_paths_cannot_retain_sdk_but_content_digests_survive(self):
        sdk = '/nix/store/' + 'a' * 32 + '-sdk'
        image = '/nix/store/' + 'b' * 32 + '-image'
        digest = 'c' * 64
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); raw = root / 'raw'; raw.mkdir()
            (raw / 'result.json').write_text(json.dumps({'sdk': sdk, 'image': image + '/priv', 'sha256': digest}))
            (raw / 'run.log').write_text(sdk + '\n' + image + '/priv/source.bl\n')
            RECEIPT.publish(raw, root / 'out')
            result = json.loads((root / 'out/result.json').read_text())
            self.assertEqual(digest, result['sha256'])
            self.assertEqual(RECEIPT.sanitize(sdk), result['sdk'])
            self.assertNotEqual(result['sdk'], result['image'].removesuffix('/priv'))
            for path in (root / 'out').iterdir():
                self.assertNotIn('/nix/store/', path.read_text())
                self.assertNotIn('a' * 32, path.read_text())
            self.assertTrue(result['image'].endswith('/priv'))

    def test_sdk_symlink_and_binary_cannot_be_exported(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); raw = root / 'raw'; raw.mkdir()
            (raw / 'sdk').symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'symlinks'):
                RECEIPT.publish(raw, root / 'symlink-out')
            (raw / 'sdk').unlink()
            (raw / 'native.so').write_bytes(b'ELF payload')
            with self.assertRaisesRegex(ValueError, 'text records'):
                RECEIPT.publish(raw, root / 'binary-out')


if __name__ == '__main__':
    unittest.main()
