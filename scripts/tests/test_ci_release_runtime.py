import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class PinnedRuntimePathTests(unittest.TestCase):
    def test_actual_adapter_path_prevents_host_tools_and_keeps_sdk_elixir(self):
        source = (ROOT / 'nix/ci-release-runtime.nix').read_text()
        prefix = '    export PATH=${toolsPath}:"$PATH"'
        self.assertEqual(1, source.count(prefix))
        bash = shutil.which('bash')
        self.assertIsNotNone(bash)
        # Execute the actual adapter assignment with isolated tool directories;
        # the station smoke checks the real pinned binaries and PRoot loader.
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
            environment = dict(os.environ, PATH=str(sdk) + os.pathsep + str(host))
            assignment = prefix.strip().replace('${toolsPath}', str(pinned))
            commands = '\ndirname /a/b\nbasename /a/b\nelixir\n'
            result = subprocess.run([bash, '-eu', '-c', assignment + commands], env=environment,
                                    text=True, capture_output=True)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(['pinned-dirname', 'pinned-basename', 'selected-sdk-elixir'],
                             result.stdout.splitlines())
            original = subprocess.run([bash, '-eu', '-c', commands], env=environment,
                                      text=True, capture_output=True)
            self.assertEqual(91, original.returncode)
            self.assertIn('host loader library missing', original.stderr)
