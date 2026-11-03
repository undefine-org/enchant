"""Exercise the generated coordinator wrapper with a separate manager environment."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
NAMES = ('NIX_CONFIG', 'NIX_SSHOPTS', 'NIX_USER_CONF_FILES', 'NIX_CONF_DIR', 'SSH_AUTH_SOCK', 'XDG_CONFIG_HOME')


class CoordinatorHostPolicy(unittest.TestCase):
    @unittest.skipUnless(shutil.which('nix-instantiate'), 'Nix evaluator unavailable')
    def test_generated_worker_preserves_only_operator_nix_policy_across_both_boundaries(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            platform, runtime = root / 'platform', root / 'runtime'
            for path in (platform / 'bin', runtime / 'bin', runtime / 'foundry'):
                path.mkdir(parents=True)
            (platform / 'bin/python3').symlink_to(shutil.which('python3'))
            # Evaluate the actual recipe without realizing a compiler or SDK.
            expression = '''import %s {
              pkgs = {
                runCommand = name: attrs: body: body;
                lib.fileset.toSource = args: "/qualified/foundry";
                runtimeShell = "/bin/bash"; coreutils = "/usr";
              };
              platform = %s; compiler = "/qualified/compiler";
              source = "/qualified/source"; dependencies = "/qualified/dependencies";
              foundry = "/qualified/foundry";
            }''' % (ROOT / 'nix/coordinator-runtime.nix', json.dumps(str(platform)))
            rendered = json.loads(subprocess.check_output(
                ['nix-instantiate', '--eval', '--strict', '--json', '--expr', expression], text=True))
            fragment = re.search(r'cat > "\$out/bin/worker" <<EOF_WORKER\n.*?\nEOF_WORKER', rendered, re.S)
            self.assertIsNotNone(fragment)
            subprocess.run(['bash', '-eu', '-c', fragment[0]], env=dict(os.environ, out=str(runtime)), check=True)
            manager = platform / 'bin/systemd-run'
            manager.write_text('''#!/usr/bin/env python3
import os, sys
argv = sys.argv[1:]
assert '--expand-environment=no' in argv
end = argv.index('--')
env = {'PATH': os.environ['PATH']}
for arg in argv[:end]:
    if arg.startswith('--setenv='):
        name = arg.removeprefix('--setenv=')
        env[name] = os.environ[name]
os.execvpe(argv[end+1], argv[end+1:], env)
''')
            manager.chmod(0o755)
            client = runtime / 'bin/bl'
            client.write_text('''#!/usr/bin/env python3
import json, os, sys
print(json.dumps({'env': dict(os.environ), 'argv': sys.argv[1:]}))
''')
            client.chmod(0o755)
            clean = {name: value for name, value in os.environ.items() if name not in NAMES}
            for settings in ({}, {'NIX_CONFIG': 'include /operator/nix-$literal.conf\nmax-jobs = 0\n',
                                  'NIX_SSHOPTS': '-F/operator/ssh config', 'SSH_AUTH_SOCK': '/operator/agent'}):
                with self.subTest(settings=settings):
                    result = json.loads(subprocess.check_output(
                        ['bash', str(runtime / 'bin/worker'), '--id', 'job_fixture'], text=True,
                        env={**clean, **settings, 'UNRELATED_SECRET': 'must-stay-out'}))
                    self.assertEqual(settings, {name: result['env'][name] for name in NAMES if name in result['env']})
                    self.assertNotIn('UNRELATED_SECRET', result['env'])
                    self.assertEqual(['--cold', '--id', 'job_fixture'], result['argv'])


if __name__ == '__main__':
    unittest.main()
