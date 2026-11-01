"""Platform preparation requires the station and preserves its CPU policy."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class PlatformHostPolicy(unittest.TestCase):
    def test_preparation_requires_the_station_without_replacing_its_cpu_policy(self):
        with tempfile.TemporaryDirectory(prefix='bl-platform-policy-') as temporary:
            project = Path(temporary) / 'source'
            for name in ('scripts', 'nix', 'native', 'tooling/drop', 'tools'):
                (project / name).mkdir(parents=True)
            for name in ('flake.nix', 'flake.lock'):
                (project / name).write_text('{}\n')
            shutil.copyfile(ROOT / 'scripts/prepare-checkout-platform',
                            project / 'scripts/prepare-checkout-platform')
            manager = project / 'tools/systemd-run'
            manager.write_text('''#!/usr/bin/env python3
import os, sys
start = sys.argv.index('nix-build')
os.execvp('nix-build', sys.argv[start:])
''')
            manager.chmod(0o755)
            builder = project / 'tools/nix-build'
            builder.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
pathlib.Path(os.environ['PLATFORM_CAPTURE']).write_text(json.dumps({
    'argv': sys.argv[1:], 'config': os.environ['NIX_CONFIG']}))
target = pathlib.Path(sys.argv[sys.argv.index('--out-link') + 1])
target.mkdir(parents=True)
(target / 'platform.json').write_text('{}')
''')
            builder.chmod(0o755)
            capture = project / 'capture.json'
            policy = 'max-jobs = 0\ncores = 4\n'
            env = dict(os.environ, PATH=str(project / 'tools') + os.pathsep + os.environ['PATH'],
                       PLATFORM_CAPTURE=str(capture), NIX_CONFIG=policy)
            subprocess.run(['bash', str(project / 'scripts/prepare-checkout-platform')],
                           env=env, check=True, capture_output=True, text=True)
            actual = json.loads(capture.read_text())
            self.assertNotIn('--cores', actual['argv'])
            self.assertEqual('0', actual['argv'][actual['argv'].index('--max-jobs') + 1])
            self.assertEqual(policy, actual['config'])


if __name__ == '__main__':
    unittest.main()
