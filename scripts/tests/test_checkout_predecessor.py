"""Observe real checkout-wrapper argv and crash recovery with inert executors."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class CheckoutPredecessorTests(unittest.TestCase):
    def test_coordinator_gets_the_frozen_predecessor_before_any_target_compilation(self):
        self.check_predecessor(False)

    def test_recovered_preparation_is_frozen_alongside_the_qualified_predecessor(self):
        self.check_predecessor(True)

    def check_predecessor(self, with_preparation):
        with tempfile.TemporaryDirectory(prefix='checkout-predecessor-') as temporary:
            base = Path(temporary)
            checkout, tools, engine = [base / name for name in ('checkout', 'tools', 'engine')]
            for path in (checkout / 'scripts', tools, engine):
                path.mkdir(parents=True)
            wrapper = checkout / 'scripts/prepare-checkout-sdk'
            shutil.copy2(ROOT / 'scripts/prepare-checkout-sdk', wrapper)
            (checkout / 'scripts/sdk-inputs').write_text('print("f" * 64)\n')
            selection = checkout / '.bl/sdks/current-sdk'
            selection.parent.mkdir(parents=True)
            predecessors = []
            for name in ('previous', 'newer'):
                sdk = base / name
                (sdk / 'unit-store').mkdir(parents=True)
                (sdk / 'unit-store/unit-index.json').write_text('{}')
                predecessors.append(sdk)
            selection.symlink_to(predecessors[0], target_is_directory=True)
            preparations = [base / 'prepared', base / 'newer-preparation']
            hint = selection.parent / 'previous-preparation'
            if with_preparation:
                for item in preparations:
                    (item / 'unit-store').mkdir(parents=True)
                hint.symlink_to(preparations[0], target_is_directory=True)
            systemd = tools / 'systemd-run'
            systemd.write_text('''#!/usr/bin/env python3
import os, sys
argv = sys.argv[1:]
while argv[0].startswith('--'): argv.pop(0)
os.execvp(argv[0], argv)
''')
            nix = tools / 'nix-build'
            nix.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
argv = sys.argv[1:]
with open(os.environ['CAPTURE'], 'a') as stream: stream.write(json.dumps(argv) + '\\n')
if 'coordinator' in argv: raise SystemExit(1)
pathlib.Path(argv[argv.index('--out-link') + 1]).symlink_to(os.environ['ENGINE'], target_is_directory=True)
''')
            systemd.chmod(0o755)
            nix.chmod(0o755)
            capture = base / 'argv.jsonl'
            env = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ['PATH'],
                       CAPTURE=str(capture), ENGINE=str(engine))

            def invoke():
                result = subprocess.run([str(wrapper)], env=env, text=True, capture_output=True, timeout=15)
                self.assertEqual(69, result.returncode, result.stderr)
                rows = [json.loads(line) for line in capture.read_text().splitlines()]
                for row in rows:
                    self.assertNotIn('--max-jobs', row)
                coordinator = rows[-1]
                self.assertIn('coordinator', coordinator)
                self.assertEqual(str(predecessors[0]), coordinator[coordinator.index('previous') + 1])
                jobs = list((selection.parent / ('f' * 64)).glob('job-*'))
                self.assertEqual(1, len(jobs))
                operation = json.loads((jobs[0] / 'operation.json').read_text())
                self.assertEqual(str(predecessors[0]), operation['previous'])
                self.assertEqual(3 if with_preparation else 2, operation['version'])
                if with_preparation:
                    self.assertEqual(str(preparations[0]), operation['preparation'])
                return jobs[0]

            job = invoke()
            if with_preparation:
                hint.unlink()
                hint.symlink_to(preparations[1], target_is_directory=True)
            selection.unlink()
            selection.symlink_to(predecessors[1], target_is_directory=True)
            self.assertEqual(job, invoke())
            # Simulate interruption after retaining the predecessor, before
            # publishing operation.json. Recovery must keep that same baseline.
            (job / 'operation.json').unlink()
            self.assertEqual(job, invoke())


if __name__ == '__main__':
    unittest.main()
