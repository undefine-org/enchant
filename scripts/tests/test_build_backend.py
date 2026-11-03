"""Real Nix bootstrap projections, without a BEAM or native build."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import contextlib
import io
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('build_backend', ROOT / 'scripts/build-backend.py')
BACKEND = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BACKEND)


class BuildBackendTests(unittest.TestCase):
    def test_user_station_install_consumes_the_source_owned_transport(self):
        evaluation = {'storeUri': 'ssh-ng://operator-station', 'transport': ['ssh', 'operator-station', '{endpoint}']}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'station.json'
            argv = ['backend', '--description', 'operator.bl', '--station-out', str(output)]
            with patch.object(sys, 'argv', argv), patch.object(BACKEND, 'load', return_value=(
                    dict(version=1, kind='configured', nix={}, evaluation=evaluation), '')), \
                    contextlib.redirect_stdout(io.StringIO()):
                BACKEND.main()
            self.assertEqual(dict(version=1, **evaluation), json.loads(output.read_text()))
            self.assertEqual(0o600, output.stat().st_mode & 0o777)

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
