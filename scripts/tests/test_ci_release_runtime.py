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
    def test_release_adapters_run_inside_standard_bash_steps_with_space_in_cwd(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / 'checkout with spaces'
            (workspace / 'scripts').mkdir(parents=True)
            adapter = workspace / 'scripts/with-release-runtime'
            shutil.copy2(ROOT / 'scripts/with-release-runtime', adapter)
            bash = shutil.which('bash')
            count = 0
            for name in ('build-drop.yml', 'release.yml'):
                lines = (ROOT / '.github/workflows' / name).read_text().splitlines()
                for index, line in enumerate(lines):
                    if 'shell:' in line:
                        self.assertNotIn('with-release-runtime', line)
                        self.assertNotIn('${{ github.workspace }}', line)
                    if "<<'BL_PINNED_RELEASE_CHECK'" not in line:
                        continue
                    self.assertEqual('shell: bash', lines[index - 2].strip())
                    self.assertEqual('run: |', lines[index - 1].strip())
                    command = line.split('<<', 1)[0].strip()
                    executable = shlex.split(command)[0]
                    self.assertEqual('./scripts/with-release-runtime', executable)
                    environment = dict(os.environ, PATH=str(Path(sys.executable).parent))
                    result = subprocess.run([bash, '--noprofile', '--norc', '-e', '-o', 'pipefail',
                                             '-c', executable + ' --help'], cwd=workspace,
                                            env=environment, text=True, capture_output=True)
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertIn('pinned FHS loader', result.stdout)
                    count += 1
            self.assertEqual(6, count)
