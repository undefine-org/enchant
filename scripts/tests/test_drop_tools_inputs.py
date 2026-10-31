"""Actual launcher identities exclude inspection scripts and test fixtures."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class DropToolsInputs(unittest.TestCase):
    def test_only_cargo_and_rust_inputs_invalidate_the_launcher(self):
        with tempfile.TemporaryDirectory(prefix='bl-drop-inputs-') as temporary:
            source = Path(temporary) / 'drop'
            shutil.copytree(ROOT / 'tooling/drop', source,
                            ignore=shutil.ignore_patterns('target', '.git', '.bl'))

            def identity():
                result = subprocess.run([
                    'nix-instantiate', '--eval', '--strict', '--json', '--read-write-mode',
                    str(ROOT / 'test/nix/drop-tools-inputs.nix'),
                    '--argstr', 'root', str(source),
                ], cwd=ROOT, text=True, capture_output=True, timeout=90)
                self.assertEqual(0, result.returncode, result.stderr)
                return json.loads(result.stdout)

            original = identity()
            (source / 'glibc-floor.sh').write_text('# changed inspection script\n')
            (source / 'tests').mkdir(exist_ok=True)
            (source / 'tests/new-fixture.py').write_text('# new test fixture\n')
            (source / 'target').mkdir(exist_ok=True)
            (source / 'target/stale').write_text('generated output\n')
            self.assertEqual(original, identity())
            launcher = source / 'src/launcher.rs'
            launcher.write_text(launcher.read_text() + '\n// source identity control\n')
            rust_changed = identity()
            self.assertNotEqual(original['source'], rust_changed['source'])
            self.assertNotEqual(original['derivation'], rust_changed['derivation'])
            manifest = source / 'Cargo.toml'
            manifest.write_text(manifest.read_text() + '\n# manifest identity control\n')
            self.assertNotEqual(rust_changed, identity())


if __name__ == '__main__':
    unittest.main()
