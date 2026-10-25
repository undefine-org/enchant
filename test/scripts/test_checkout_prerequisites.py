"""Pre-BEAM publication uses real immutable bytes and independent OS custody."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class CheckoutPrerequisites(unittest.TestCase):
    def test_preboot_selection_retains_custody_and_noop_preserves_cohort(self):
        platform = Path(os.environ['BL_TEST_CHECKOUT_PLATFORM'])
        launcher = platform / 'bin/drop-launcher'
        descriptor = json.loads((platform / 'platform.json').read_text())
        native = Path(descriptor['native'])
        products = json.loads((platform / 'native-products/artifacts.json').read_text())['products']
        with tempfile.TemporaryDirectory(prefix='checkout-prerequisites-') as temporary:
            root = Path(temporary)
            seed = root / 'priv/bootstrap/seed'
            seed.mkdir(parents=True)
            (seed / 'manifest.term').write_text('fixture: never starts a VM')

            def prepare(selected=platform):
                return subprocess.run([str(launcher), '--checkout-prerequisites', str(root), str(selected)],
                                      text=True, capture_output=True, timeout=10)

            result = prepare()
            self.assertEqual(0, result.returncode, result.stderr)
            destination = root / 'priv/native/lazy_memo.so'
            self.assertEqual(native / 'lib/lazy_memo.so', destination.readlink())
            self.assertEqual((native / 'lib/lazy_memo.so').read_bytes(), destination.read_bytes())
            for name, product in products.items():
                self.assertEqual(Path(product['output']) / 'lib' / f'{name}.so',
                                 (root / 'priv/native' / f'{name}.so').readlink())
            scope = root / 'priv/native/.bl/artifact-custody/lazy_memo.so'
            claim = scope / '.claim'
            claim.write_text('existing-reader-cohort')
            self.assertEqual(0, prepare().returncode)
            self.assertEqual('existing-reader-cohort', claim.read_text())

            destination.unlink()
            destination.write_bytes(b'previous-selection')
            anchor = scope.parent / '.bl/locks/lazy_memo.so'
            with anchor.open('r+') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                refused = prepare()
                self.assertNotEqual(0, refused.returncode)
                self.assertIn('custody held', refused.stderr)
                self.assertEqual(b'previous-selection', destination.read_bytes())
                self.assertEqual('existing-reader-cohort', claim.read_text())
            self.assertEqual(0, prepare().returncode)
            self.assertFalse(claim.exists())
            mutable = root / 'mutable-platform'
            mutable.mkdir()
            (mutable / 'platform.json').write_text(json.dumps(descriptor))
            refused = prepare(mutable)
            self.assertNotEqual(0, refused.returncode)
            self.assertIn('immutable store object', refused.stderr)


if __name__ == '__main__':
    unittest.main()
