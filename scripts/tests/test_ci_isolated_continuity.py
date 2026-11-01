"""Exercise the actual workflow shell boundary without launching a worker."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class IsolatedContinuity(unittest.TestCase):
    def test_exact_retained_candidate_gets_one_file_and_one_fresh_worker(self):
        workflow = (ROOT / '.github/workflows/ci.yml').read_text()
        host = workflow.split('\n  test-nix:\n', 1)[1].split('\n  qualify-linux:\n', 1)[0]
        step = host.split('      - name: Qualify complex continuity in a fresh VM\n', 1)[1]
        step = step.split('      - name:', 1)[0]
        self.assertIn("!cancelled() && steps.sdk-cache.outcome == 'success'", step)
        body = re.search(r'        run: \|\n((?:          .*\n)+)', step)[1]
        body = '\n'.join(line[10:] for line in body.splitlines())
        body = body.replace('${{ steps.sdk-cache.outputs.sdk }}', '/nix/store/retained-selection')
        with tempfile.TemporaryDirectory(prefix='isolated-continuity-shell-') as temporary:
            root = Path(temporary)
            (root / 'scripts').mkdir()
            command = root / 'scripts/ci-check'
            command.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$CAPTURE_ARGV"\n')
            command.chmod(0o755)
            receipt = root / 'arguments'
            subprocess.run(['bash', '-eu', '-o', 'pipefail', '-c', body], cwd=root,
                           env=dict(os.environ, RUNNER_TEMP=str(root), CAPTURE_ARGV=str(receipt)),
                           check=True)
            self.assertEqual(receipt.read_text().splitlines(), [
                '--local', '--sdk', '/nix/store/retained-selection', '--out',
                str(root / 'check-isolated-continuity'), 'test/bl/reload/continuity_demo_test.bl'])


if __name__ == '__main__':
    unittest.main()
