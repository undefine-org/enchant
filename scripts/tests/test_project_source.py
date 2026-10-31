"""Real source-closure controls; no compiler, native build or BEAM starts."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ProjectSource(unittest.TestCase):
    def test_declared_roots_are_complete_and_generated_outputs_are_excluded(self):
        with tempfile.TemporaryDirectory(prefix='bl-project-source-') as temporary:
            project = Path(temporary)
            (project / 'src').mkdir()
            (project / 'native/example').mkdir(parents=True)
            (project / 'src/main.bl').write_text('(ns example) (def value 42)\n')
            (project / 'env.bl').write_text('{:paths ["src"]}\n')
            roots = ['src', 'native', 'env.bl']

            def snapshot(selected=roots, success=True):
                result = subprocess.run(['nix-instantiate', '--eval', '--strict', '--json', '--read-write-mode',
                    str(ROOT / 'nix/project-source.nix'), '--argstr', 'source', str(project),
                    '--argstr', 'rootsJson', json.dumps(selected)],
                    capture_output=True, text=True, timeout=60)
                self.assertEqual(success, result.returncode == 0, result.stderr)
                return json.loads(result.stdout) if success else result.stderr

            original = snapshot()
            (project / 'runtime.env').write_text('unselected runtime input')
            (project / 'native/example/target').mkdir()
            (project / 'native/example/target/stale.so').write_text('generated')
            (project / '.bl').mkdir()
            (project / '.bl/state').write_text('generated')
            self.assertEqual(original, snapshot())
            self.assertFalse((Path(original) / 'runtime.env').exists())
            (project / 'src/schema.json').write_text('{"supportingInput":true}\n')
            added = snapshot()
            self.assertNotEqual(original, added)
            (project / 'src/schema.json').chmod(0o755)
            mode = snapshot()
            self.assertNotEqual(added, mode)
            (project / 'src/empty').mkdir()
            self.assertNotEqual(mode, snapshot())
            (project / 'src/escape').symlink_to(project / 'runtime.env')
            self.assertIn('self-contained source closure', snapshot(success=False))
            self.assertIn('assertion', snapshot(['../outside'], success=False))
            self.assertIn('assertion', snapshot(['missing'], success=False))


if __name__ == '__main__':
    unittest.main()
