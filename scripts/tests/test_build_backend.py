"""Real Nix bootstrap projections, without a BEAM or native build."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('build_backend', ROOT / 'scripts/build-backend.py')
BACKEND = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BACKEND)


class BuildBackendTests(unittest.TestCase):
    def test_source_owned_projections_feed_the_real_nix_client(self):
        with tempfile.TemporaryDirectory() as temporary:
            for name, jobs in [('local', 1), ('configured', None), ('nixbuild', 0), ('ssh', 0)]:
                with self.subTest(name=name):
                    description, config = BACKEND.load(ROOT / f'tooling/build-backends/{name}.bl')
                    self.assertEqual(name, description['kind'])
                    if jobs is None:
                        self.assertEqual('', config)
                        continue
                    path = Path(temporary) / 'nix.conf'
                    path.write_text(config)
                    actual = json.loads(subprocess.check_output(
                        ['nix', '--extra-experimental-features', 'nix-command', 'config', 'show', '--json'],
                        env=dict(os.environ, NIX_CONFIG='include ' + str(path)), text=True, stderr=subprocess.PIPE))
                    self.assertEqual(jobs, actual['max-jobs']['value'])
                    if name == 'nixbuild':
                        self.assertIn('ssh://eu.nixbuild.net', actual['builders']['value'])
                        self.assertIn('kvm,nixos-test,benchmark,big-parallel', actual['builders']['value'])

    def test_changed_source_refuses_a_stale_projection_before_configuration(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'local.bl'
            shutil.copyfile(ROOT / 'tooling/build-backends/local.bl', path)
            shutil.copyfile(ROOT / 'tooling/build-backends/local.nix', path.with_suffix('.nix'))
            path.write_text(path.read_text() + '\n;; new policy requires compilation\n')
            with self.assertRaisesRegex(ValueError, 'Stale backend projection'):
                BACKEND.load(path)

    def test_bootstrap_cli_writes_private_config_and_selects_the_declared_backend(self):
        with tempfile.TemporaryDirectory() as temporary:
            output, config = [Path(temporary) / name for name in ('github-output', 'nix.conf')]
            result = subprocess.check_output([
                'python3', str(ROOT / 'scripts/build-backend.py'), '--description',
                str(ROOT / 'tooling/build-backends/nixbuild.bl'), '--config-out', str(config),
                '--github-output', str(output)], text=True)
            self.assertEqual('nixbuild', json.loads(result)['backend'])
            self.assertEqual(0o600, config.stat().st_mode & 0o777)
            self.assertIn('nixbuild-host<<', output.read_text())
            self.assertIn('eu.nixbuild.net', output.read_text())


if __name__ == '__main__':
    unittest.main()
