import os
from pathlib import Path
import shutil
import shlex
import sys
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class PinnedRuntimePathTests(unittest.TestCase):
    def test_actual_adapter_path_prevents_host_tools_and_keeps_sdk_elixir(self):
        source = (ROOT / 'nix/ci-release-runtime.nix').read_text()
        prefix = '      export PATH=${toolsPath}:"$BL_CI_RELEASE_CALLER_PATH"'
        self.assertEqual(1, source.count(prefix))
        bash = shutil.which('bash')
        self.assertIsNotNone(bash)
        # Execute the actual adapter assignment with isolated tool directories;
        # the station smoke checks the real pinned FHS mount namespace.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pinned, sdk, host = [root / name for name in ('pinned', 'sdk', 'host')]
            for directory in (pinned, sdk, host):
                directory.mkdir()
            for name in ('dirname', 'basename'):
                good = pinned / name
                good.write_text('#!/bin/sh\nprintf "pinned-' + name + '\\n"\n')
                good.chmod(0o755)
                bad = host / name
                bad.write_text('#!/bin/sh\necho "host loader library missing" >&2\nexit 91\n')
                bad.chmod(0o755)
            elixir = sdk / 'elixir'
            elixir.write_text('#!/bin/sh\nprintf "selected-sdk-elixir\\n"\n')
            elixir.chmod(0o755)
            caller = str(sdk) + os.pathsep + str(host)
            environment = dict(os.environ, PATH=str(host), BL_CI_RELEASE_CALLER_PATH=caller)
            assignment = prefix.strip().replace('${toolsPath}', str(pinned))
            commands = '\ndirname /a/b\nbasename /a/b\nelixir\n'
            result = subprocess.run([bash, '-eu', '-c', assignment + commands], env=environment,
                                    text=True, capture_output=True)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(['pinned-dirname', 'pinned-basename', 'selected-sdk-elixir'],
                             result.stdout.splitlines())
            reset_path = assignment.replace('$BL_CI_RELEASE_CALLER_PATH', '$PATH')
            reset = subprocess.run([bash, '-eu', '-c', reset_path + commands], env=environment,
                                   text=True, capture_output=True)
            self.assertEqual(127, reset.returncode)
            self.assertIn('elixir: command not found', reset.stderr)
            original = subprocess.run([bash, '-eu', '-c', commands], env=environment,
                                      text=True, capture_output=True)
            self.assertEqual(91, original.returncode)
            self.assertIn('host loader library missing', original.stderr)


class WorkflowShellPathTests(unittest.TestCase):
    def test_release_adapters_resolve_outside_the_workspace_and_with_spaces(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / 'checkout with spaces'
            (workspace / 'scripts').mkdir(parents=True)
            adapter = workspace / 'scripts/with-release-runtime'
            shutil.copy2(ROOT / 'scripts/with-release-runtime', adapter)
            unrelated = Path(temporary) / 'nix-profile/bin'
            unrelated.mkdir(parents=True)
            count = 0
            for name in ('build-drop.yml', 'release.yml'):
                for line in (ROOT / '.github/workflows' / name).read_text().splitlines():
                    if 'shell:' not in line or 'with-release-runtime' not in line:
                        continue
                    scalar = line.split('shell:', 1)[1].strip()
                    self.assertTrue(scalar.startswith("'") and scalar.endswith("'"))
                    command = scalar[1:-1].replace('${{ github.workspace }}', str(workspace))
                    executable = shlex.split(command)[0]
                    self.assertEqual(str(adapter), executable)
                    self.assertTrue(Path(executable).is_absolute())
                    environment = dict(os.environ, PATH=str(Path(sys.executable).parent))
                    result = subprocess.run([executable, '--help'], cwd=unrelated, env=environment,
                                            text=True, capture_output=True)
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertIn('pinned FHS loader', result.stdout)
                    count += 1
            self.assertEqual(6, count)
