"""Actual Nix identity controls; no native compiler or BEAM is launched."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
NAMES = {'bl_json', 'bl_nix', 'code_embed', 'datom_datalog', 'datom_fjall', 'datom_vector', 'lazy_memo'}


class NativeProductIdentities(unittest.TestCase):
    def test_each_crate_owns_its_complete_input_identity(self):
        if not shutil.which('nix'):
            self.fail('Nix is required for the native product identity control')
        with tempfile.TemporaryDirectory(prefix='bl-native-identities-') as temporary:
            project = Path(temporary)
            for name in NAMES:
                shutil.copytree(ROOT / 'native' / name, project / 'native' / name,
                                ignore=shutil.ignore_patterns('target', '.git', '.bl'))

            def identities():
                result = subprocess.run(['nix-instantiate', '--eval', '--strict', '--json', '--read-write-mode',
                    str(ROOT / 'test/nix/native-product-identities.nix'), '--argstr', 'root', str(project)],
                    cwd=ROOT, text=True, capture_output=True, timeout=90)
                self.assertEqual(0, result.returncode, result.stderr)
                return json.loads(result.stdout)

            original = identities()
            self.assertEqual(NAMES, set(original))
            (project / 'app.bl').write_text('(ns app) (def value 42)\n')
            (project / 'native/bl_json/target').mkdir()
            (project / 'native/bl_json/target/old.so').write_text('stale output')
            self.assertEqual(original, identities())
            source = project / 'native/bl_json/src/lib.rs'
            source.write_text(source.read_text() + '\n// identity perturbation\n')
            changed = identities()
            self.assertEqual(['bl_json'], [name for name in sorted(NAMES) if original[name] != changed[name]])
            (project / 'native/datom_vector/additional-build-input').write_text('supporting input\n')
            added = identities()
            self.assertEqual(['datom_vector'], [name for name in sorted(NAMES) if changed[name] != added[name]])


if __name__ == '__main__':
    unittest.main()
