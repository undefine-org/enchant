import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('failure_sdk_cache', ROOT / 'scripts/ci-sdk-cache.py')
CACHE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CACHE)


class FailureCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'checkout'
        self.cache = Path(self.temporary.name) / 'cache'
        self.root.mkdir()
        self.cache.mkdir()
        model = patch.object(CACHE, 'model_input', return_value=SimpleNamespace(restore=lambda _: None))
        model.start()
        self.addCleanup(model.stop)

    def test_failure_before_sdk_allows_store_only_save_without_a_selector(self):
        with patch.object(CACHE, 'capture') as capture, patch.object(CACHE, 'retain') as retain:
            self.assertEqual('', CACHE.capture_completed(self.root, self.cache))
        capture.assert_not_called()
        retain.assert_not_called()
        self.assertEqual([], list(self.cache.iterdir()))
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/ci-sdk-cache.py'), 'save-products',
                                 '--root', str(self.root), '--cache', str(self.cache)],
                                text=True, capture_output=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('', result.stdout.strip())
        self.assertFalse((self.cache / 'selection.json').exists())

    def test_complete_sdk_uses_the_existing_source_bound_capture_without_models(self):
        # A transport fixture only: the real capture function remains the
        # admission boundary and its source-binding controls run separately.
        sdk = self.root / 'fixture-sdk'
        sdk.mkdir()
        (sdk / 'artifact.json').write_text('{}')
        selected = self.root / '.bl/sdks/current-sdk'
        selected.parent.mkdir(parents=True)
        selected.symlink_to(sdk)
        with patch.object(CACHE, 'capture', return_value='/nix/store/verified-sdk') as capture:
            self.assertEqual('/nix/store/verified-sdk', CACHE.capture_completed(self.root, self.cache))
        capture.assert_called_once_with(self.root, self.cache, sdk)
        self.assertFalse((self.cache / 'ci-sdk-selection.json').exists())

    def test_rejected_current_sdk_preserves_the_verified_predecessor(self):
        previous = {'sdk': '/nix/store/previous-sdk', 'engine_fingerprint': 'a' * 64}
        hint = self.cache / 'selection.json'
        hint.write_text(json.dumps(previous))
        before = hint.read_bytes()
        sdk = self.root / 'rejected-sdk'
        sdk.mkdir()
        (sdk / 'artifact.json').write_text('{}')
        with patch.object(CACHE, 'verify_record', return_value=previous) as verify, \
                patch.object(CACHE, 'capture', side_effect=ValueError('engine binding refused')) as capture, \
                patch.object(CACHE, 'retain') as retain:
            self.assertEqual(previous['sdk'], CACHE.capture_completed(self.root, self.cache, sdk))
        verify.assert_called_once_with(previous)
        capture.assert_called_once_with(self.root, self.cache, sdk)
        retain.assert_called_once_with(self.root, self.cache, previous)
        self.assertEqual(before, hint.read_bytes())

    def test_invalid_optional_hints_cannot_block_caching_valid_dependencies(self):
        (self.cache / 'selection.json').write_text('{}')
        (self.cache / 'models.json').write_text('{}')
        kept = self.cache / 'unrelated-completed-product'
        kept.write_text('preserve')
        with patch.object(CACHE, 'verify_record', side_effect=ValueError('invalid SDK hint')), \
                patch.object(CACHE, 'model_input', return_value=SimpleNamespace(
                    restore=lambda _: (_ for _ in ()).throw(ValueError('incomplete models')))):
            self.assertEqual('', CACHE.capture_completed(self.root, self.cache))
        self.assertFalse((self.cache / 'selection.json').exists())
        self.assertFalse((self.cache / 'models.json').exists())
        self.assertEqual('preserve', kept.read_text())

    def test_actual_workflow_conditions_never_save_twice_or_publish_from_a_consumer(self):
        for filename in ('ci.yml', 'build-drop.yml'):
            source = (ROOT / '.github/workflows' / filename).read_text()
            block = source.split('      - name: Preserve completed Nix products after producer failure\n', 1)[1]
            condition = re.search(r'        if: \$\{\{ (.*?) \}\}', block)[1]
            expression = (condition.replace('failure()', 'failed').replace('!cancelled()', 'not cancelled')
                          .replace('steps.sdk-cache.outcome', 'restored')
                          .replace('steps.save-sdk.outcome', 'saved').replace('inputs.runtime_run', 'runtime_run')
                          .replace('&&', 'and'))
            for failed, cancelled, restored, saved, reuse, expected in (
                    (True, False, 'success', 'skipped', '', True),
                    (True, False, 'success', 'failure', '', True),
                    (True, False, 'success', 'success', '', False),
                    (False, False, 'success', 'skipped', '', False),
                    (True, True, 'success', 'skipped', '', False),
                    (True, False, 'failure', 'skipped', '', False)):
                with self.subTest(workflow=filename, failed=failed, cancelled=cancelled, saved=saved):
                    actual = eval(expression, {'__builtins__': {}}, dict(
                        failed=failed, cancelled=cancelled, restored=restored, saved=saved, runtime_run=reuse))
                    self.assertEqual(expected, actual)
            if filename == 'build-drop.yml':
                self.assertFalse(eval(expression, {'__builtins__': {}}, dict(
                    failed=True, cancelled=False, restored='success', saved='skipped', runtime_run='123')))
            self.assertIn('operation: save-products', block)
            self.assertIn('key: ${{ steps.sdk-cache.outputs.key }}', block)
