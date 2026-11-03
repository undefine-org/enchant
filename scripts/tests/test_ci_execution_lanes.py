import importlib.machinery
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    path = ROOT / 'scripts' / name
    loader = importlib.machinery.SourceFileLoader(name.replace('-', '_'), str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class ExecutionLaneTests(unittest.TestCase):
    def test_host_and_vm_cover_the_original_inventory_exactly_once(self):
        inventory = load('ci-test-shard.py')
        original = [name for group in inventory.partitions(ROOT, 4) for name in group]
        bounded = [name for group in inventory.partitions(ROOT, 4, lane='bounded') for name in group]
        host = inventory.partitions(ROOT, 1, lane='host-nix')[0]
        self.assertEqual({'test/bl/native_test.bl', 'test/bl/native_runtime_custody_test.bl',
                          'test/bl/build_session_test.bl', 'test/bl/contextual_build_test.bl',
                          'test/bl/android/managed_build_test.bl',
                          'test/bl/retained_sdk_pin_test.bl'}, set(host))
        self.assertEqual(set(original), set(bounded + host))
        self.assertEqual(len(original), len(bounded + host))
        self.assertFalse(set(host) & set(bounded))
        self.assertIn('test/scripts/artifact-provider-driver.bl', inventory.host_nix_files(ROOT))
        self.assertNotIn('test/scripts/artifact-provider-driver.bl', original)

    def test_explicit_real_nix_request_refuses_before_a_vm_or_nix_job(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tools = root / 'tools'
            tools.mkdir()
            marker = root / 'unexpected-nix-job'
            executable = tools / 'nix-build'
            executable.write_text('#!/bin/sh\ntouch "' + str(marker) + '"\nexit 99\n')
            executable.chmod(0o755)
            out = root / 'receipt'
            result = subprocess.run([str(ROOT / 'scripts/ci-check'), '--out', str(out),
                                     'test/bl/native_test.bl'],
                                    env=dict(os.environ, PATH=str(tools) + os.pathsep + os.environ['PATH']),
                                    text=True, capture_output=True)
            self.assertEqual(2, result.returncode)
            self.assertIn('require scripts/ci-host-nix-check', result.stderr)
            self.assertFalse(out.exists())
            self.assertFalse(marker.exists())

    def test_invalid_file_requests_refuse_before_capture_or_nix(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            tools = directory / 'tools'
            tools.mkdir()
            marker = directory / 'unexpected-nix-job'
            executable = tools / 'nix-build'
            executable.write_text('#!/bin/sh\ntouch "' + str(marker) + '"\nexit 99\n')
            executable.chmod(0o755)
            cases = [
                ['test/scripts/artifact-provider-driver.bl'],
                ['test/bl/no_such_test.bl'],
                ['test/bl/native_test.bl', 'test/bl/native_test.bl'],
                [str(ROOT / 'test/bl/native_test.bl')],
                ['../outside_test.bl'],
            ]
            for index, files in enumerate(cases):
                with self.subTest(files=files):
                    out = directory / str(index) / 'receipt'
                    result = subprocess.run(
                        [str(ROOT / 'scripts/ci-check'), '--out', str(out), *files],
                        env=dict(os.environ, PATH=str(tools) + os.pathsep + os.environ['PATH']),
                        text=True, capture_output=True)
                    self.assertEqual(2, result.returncode, result.stderr)
                    self.assertFalse(out.parent.exists())
                    self.assertFalse(marker.exists())

    def test_loader_prefix_executes_inside_the_actual_manager_unit(self):
        host = load('ci-host-nix-check')
        root = Path('/frozen/source')
        command = host.unit_command(root, Path('/nix/store/sdk'), Path('/nix/store/runtime'),
                                    Path('/request.json'), Path('/receipts'), '/run/user/1/private',
                                    {'PATH': '/bin', 'HOME': '/home/runner',
                                     'NIX_CONFIG': 'include /operator/nix.conf',
                                     'NIX_SSHOPTS': '-F/operator/ssh-$literal',
                                     'UNRELATED_SECRET': 'must-stay-out'}, python='/bin/python3')
        delimiter = command.index('--')
        prefix = command.index(str(root / 'scripts/with-release-runtime'))
        worker = command.index(str(root / 'scripts/ci-check-worker.py'))
        self.assertLess(delimiter, prefix)
        self.assertLess(prefix, worker)
        self.assertIn('--property=MemoryMax=6G', command[:delimiter])
        self.assertIn('--property=MemorySwapMax=0', command[:delimiter])
        self.assertIn('--property=KillMode=control-group', command[:delimiter])
        self.assertIn('--setenv=NIX_CONFIG=include /operator/nix.conf', command[:delimiter])
        self.assertIn('--setenv=NIX_SSHOPTS=-F/operator/ssh-$literal', command[:delimiter])
        self.assertIn('--expand-environment=no', command[:delimiter])
        self.assertFalse(any('UNRELATED_SECRET' in value for value in command))

    def test_both_execution_lanes_keep_real_example_and_literate_fixture_inputs(self):
        source = load('ci-source.py')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'project'
            root.mkdir()
            for name in ['env.bl', 'examples/real.bl', 'README.bl.org',
                         'tooling/build-backends/ci.bl', 'tooling/build-backends/ci.nix', 'ignored.secret']:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(name)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            subprocess.run(['git', 'add', '.'], cwd=root, check=True)
            snapshot = Path(temporary) / 'snapshot'
            source.capture(root, snapshot)
            self.assertEqual('examples/real.bl', (snapshot / 'examples/real.bl').read_text())
            self.assertEqual('README.bl.org', (snapshot / 'README.bl.org').read_text())
            self.assertEqual('tooling/build-backends/ci.bl', (snapshot / 'tooling/build-backends/ci.bl').read_text())
            self.assertFalse((snapshot / 'ignored.secret').exists())


if __name__ == '__main__':
    unittest.main()
