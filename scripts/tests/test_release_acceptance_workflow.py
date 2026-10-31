import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PROVIDERS = ('BL_ROOT', 'BL_EBIN', 'BL_BIN', 'BEAM_LISP_PATH', 'BL_SDK_PRODUCT',
             'BL_ARTIFACT_PLATFORM', 'BL_PREPARATION_COORDINATOR', 'BL_PREPARED_NATIVES',
             'BL_NATIVE_PROVIDER', 'BL_TEST_CHECKOUT_PLATFORM', 'BEAM_LISP_Z3', 'ERL_LIBS')


def step(name):
    source = (ROOT / '.github/workflows/build-drop.yml').read_text()
    block = source.split('      - name: ' + name + '\n', 1)[1].split('      - name:', 1)[0]
    body = re.search(r'        run: \|\n((?:          .*\n|\n)+)', block)[1]
    return block, '\n'.join(line[10:] for line in body.splitlines())


class ReleaseAcceptanceWorkflowTests(unittest.TestCase):
    def test_reused_candidate_keeps_all_three_runtime_gates(self):
        for name in ('Verify fresh SDK startup uses compiled units',
                     'Smoke test (concurrent first launch)', 'Smoke test (cold, no warm VM, no checkout)'):
            with self.subTest(step=name):
                block, body = step(name)
                self.assertNotRegex(block, r'(?m)^        if:')
                self.assertNotIn('self-build', body)
                self.assertNotIn('ci-check', body)
                if name.startswith('Verify'):
                    self.assertIn('--samples 1 --runtime-regressions', body)

    def run_control(self, body):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            work, runner, records = [root / name for name in ('checkout', 'runner temp', 'receipts')]
            for path in (work, runner, records):
                path.mkdir()
            candidate = work / 'bl-linux-x86_64'
            candidate.write_text('#!' + sys.executable + '\n' + '''
import json, os, pathlib, sys
providers = PROVIDER_NAMES
if any(os.environ.get(name) for name in providers):
    print('foreign provider leaked', file=sys.stderr); sys.exit(79)
assert sys.argv[1:] == ['--cold', 'version']
root = pathlib.Path(os.environ['DROP_STORE_ROOT'])
assert root.is_absolute() and not (pathlib.Path.cwd() / 'priv').exists()
root.mkdir(exist_ok=True)
row = dict(store=str(root), cwd=os.getcwd(), xdg={name: os.environ[name] for name in
    ['XDG_CACHE_HOME','XDG_DATA_HOME','XDG_STATE_HOME','XDG_CONFIG_HOME','XDG_RUNTIME_DIR']})
(pathlib.Path(os.environ['FAKE_RECEIPTS']) / (str(os.getpid()) + '.json')).write_text(json.dumps(row))
print('beam-lisp fixture')
'''.replace('PROVIDER_NAMES', repr(PROVIDERS)))
            candidate.chmod(0o755)
            before = candidate.read_bytes()
            existing = root / 'already-installed'
            existing.mkdir()
            environment = dict(os.environ, **{name: '/foreign/source-or-provider' for name in PROVIDERS},
                               RUNNER_TEMP=str(runner), FAKE_RECEIPTS=str(records), WARM_STORE=str(existing))
            result = subprocess.run(['bash', '-eu', '-o', 'pipefail', '-c',
                                     body.replace('${{ inputs.artifact }}', 'linux-x86_64')],
                                    cwd=work, env=environment, text=True, capture_output=True)
            rows = [json.loads(path.read_text()) for path in records.glob('*.json')]
            self.assertEqual(before, candidate.read_bytes())
            return result, rows, str(runner)

    def test_actual_concurrent_wave_uses_one_fresh_store_and_no_source_providers(self):
        _, body = step('Smoke test (concurrent first launch)')
        result, rows, runner = self.run_control(body)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(8, len(rows))
        self.assertEqual(1, len({row['store'] for row in rows}))
        self.assertTrue(rows[0]['store'].startswith(runner + '/bl-release-race.'))
        self.assertEqual(1, len({row['cwd'] for row in rows}))
        for row in rows:
            self.assertTrue(row['cwd'].endswith('/project'))
            self.assertTrue(all(value.startswith(str(Path(row['store']).parent) + '/') for value in row['xdg'].values()))
        # A warmed extraction path must fail before launching any child.
        anchor = 'export DROP_STORE_ROOT="$fresh/drop"'
        self.assertEqual(1, body.count(anchor))
        warmed, rows, _ = self.run_control(body.replace(anchor, 'export DROP_STORE_ROOT="$WARM_STORE"'))
        self.assertNotEqual(0, warmed.returncode)
        self.assertEqual([], rows)
        # Keeping the actual SDK native-provider override must also fail.
        leaked, _, _ = self.run_control(body.replace('BL_PREPARED_NATIVES ', '', 1))
        self.assertNotEqual(0, leaked.returncode)
        self.assertIn('foreign provider leaked', leaked.stdout + leaked.stderr)

    def test_actual_cold_native_setup_also_isolates_the_extraction_store(self):
        _, body = step('Smoke test (cold, no warm VM, no checkout)')
        setup = body.split('expect() {', 1)[0]
        result, rows, runner = self.run_control(setup + '\n"$BL" --cold version\n')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(1, len(rows))
        self.assertTrue(rows[0]['store'].startswith(runner + '/bl-release-native.'))
