import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class CheckHostPolicyTests(unittest.TestCase):
    def test_configured_routing_and_explicit_overrides_reach_actual_nix_argv(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / 'source'
            source.mkdir()
            (source / 'test').mkdir()
            (source / 'test/finite_test.bl').write_text('(ns finite-test)\n')
            subprocess.run(['git', 'init', '-q', str(source)], check=True)
            subprocess.run(['git', 'add', '.'], cwd=source, check=True)
            tools = base / 'tools'
            tools.mkdir()
            nix = tools / 'nix-build'
            nix.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
argv = sys.argv[1:]
pathlib.Path(os.environ['CHECK_CAPTURE']).write_text(json.dumps(argv))
request = json.loads(pathlib.Path(argv[argv.index('request') + 1]).read_text())
out = pathlib.Path(argv[argv.index('--out-link') + 1]); out.mkdir()
receipt = dict(status='passed', request=request, frozen_inputs_unchanged=True, assertions=1)
receipt.update({name: '0' * 64 for name in ['sdk_descriptor_sha256', 'candidate_sha256', 'compiler_manifest_sha256', 'source_sha256']})
(out / 'result.json').write_text(json.dumps(receipt))
''')
            nix.chmod(0o755)
            capture = base / 'nix-argv.json'
            env = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ['PATH'], CHECK_CAPTURE=str(capture),
                       NIX_CONFIG='builders = ssh://provider.example.invalid x86_64-linux\nmax-jobs = 0\n')
            for index, (flags, expected) in enumerate((([], None), (['--local'], '1'), (['--remote'], '0'))):
                with self.subTest(flags=flags):
                    out = base / str(index)
                    subprocess.run([str(ROOT / 'scripts/ci-check'), *flags, '--source', str(source),
                                    '--out', str(out), 'test/finite_test.bl'], env=env,
                                   check=True, stdout=subprocess.DEVNULL)
                    argv = json.loads(capture.read_text())
                    if expected is None:
                        self.assertNotIn('--max-jobs', argv)
                    else:
                        self.assertEqual(expected, argv[argv.index('--max-jobs') + 1])
                    self.assertIn('--out-link', argv)
                    self.assertNotIn('builders', argv)
