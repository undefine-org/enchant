import os
from pathlib import Path
import re
import subprocess
import unittest


class ExactCacheRestoreTests(unittest.TestCase):
    def test_actual_consumer_gate_requires_a_completed_exact_restore(self):
        source = (Path(__file__).resolve().parents[2] / '.github/actions/nix-sdk-cache/action.yml').read_text()
        block = source.split('    - name: Require the exact producer cache for qualification consumers\n', 1)[1]
        block = block.split('    - name:', 1)[0]
        body = re.search(r'      run: \|\n((?:        .*\n)+)', block)[1]
        body = '\n'.join(line[8:] for line in body.splitlines())
        for restored, hit, expected in (('producer-12', 'true', 0), ('', 'false', 69),
                                        ('producer-11', 'false', 69), ('producer-12', 'false', 69),
                                        ('', 'true', 69)):
            with self.subTest(restored=restored, hit=hit):
                result = subprocess.run(['bash', '-eu', '-c', body], capture_output=True, text=True,
                                        env=dict(os.environ, REQUESTED_KEY='producer-12',
                                                 RESTORED_KEY=restored, PRIMARY_HIT=hit))
                self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
