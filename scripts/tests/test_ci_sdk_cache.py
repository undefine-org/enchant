import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('ci_sdk_cache', ROOT / 'scripts/ci-sdk-cache.py')
CACHE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CACHE)


class SDKCacheSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'checkout'
        self.cache = Path(self.temporary.name) / 'cache'
        self.root.mkdir()
        self.cache.mkdir()
        # A receipt fixture exercises selection transport only. describe_sdk's
        # real store registration/admission checks are never replaced in CI.
        self.record = {'version': 1, 'kind': 'ci-sdk-cache-hint',
                       'sdk': '/nix/store/' + 'a' * 32 + '-retained-sdk',
                       'engine_source': '/nix/store/' + 'e' * 32 + '-engine-source',
                       'engine_fingerprint': 'b' * 64,
                       'descriptor_sha256': 'c' * 64, 'unit_index_sha256': 'd' * 64}

    def write_hint(self, record=None):
        (self.cache / 'selection.json').write_text(json.dumps(record or self.record))

    def test_cold_producer_can_start_but_exact_consumer_cannot(self):
        self.assertEqual('', CACHE.restore(self.root, self.cache))
        with self.assertRaisesRegex(ValueError, 'rerun production'):
            CACHE.restore(self.root, self.cache, required=True)
        self.assertFalse((self.root / '.bl').exists())

    def test_predecessor_retains_its_real_fingerprint_and_gc_root(self):
        self.write_hint()
        with patch.object(CACHE, 'verify_record', return_value=self.record), \
                patch.object(CACHE.subprocess, 'run') as run:
            self.assertEqual(self.record['sdk'], CACHE.restore(self.root, self.cache))
        exact = self.root / '.bl/sdks' / self.record['engine_fingerprint'] / 'result-sdk'
        self.assertEqual(self.record['sdk'], str(exact.readlink()))
        self.assertEqual(self.record['sdk'], str((self.root / '.bl/sdks/current-sdk').readlink()))
        self.assertEqual(['nix-store', '--add-root', str(self.cache / 'sdk-root'),
                          '--indirect', '--realise', self.record['sdk']], run.call_args_list[0].args[0])
        self.assertEqual(['nix-store', '--add-root', str(self.cache / 'engine-root'),
                          '--indirect', '--realise', self.record['engine_source']], run.call_args_list[1].args[0])
        self.assertEqual([self.record['engine_fingerprint'], 'current-sdk'],
                         sorted(path.name for path in (self.root / '.bl/sdks').iterdir()))

    def test_changed_receipt_is_rejected_before_checkout_or_gc_mutation(self):
        for field in ('sdk', 'engine_fingerprint', 'descriptor_sha256', 'unit_index_sha256'):
            with self.subTest(field=field):
                edited = copy.deepcopy(self.record)
                edited[field] += '0'
                self.write_hint(edited)
                description = {key: value for key, value in self.record.items()
                               if key not in ('engine_source', 'engine_fingerprint')}
                with patch.object(CACHE, 'describe_sdk', return_value=description), \
                        patch.object(CACHE, 'store_path', return_value=Path(self.record['engine_source'])), \
                        patch.object(CACHE, 'retained_source_fingerprint', return_value=self.record['engine_fingerprint']), \
                        patch.object(CACHE.subprocess, 'run'), patch.object(CACHE, 'retain') as retain:
                    with self.assertRaisesRegex(ValueError, 'no longer matches'):
                        CACHE.restore(self.root, self.cache, required=True)
                    retain.assert_not_called()

    def test_optional_invalid_predecessor_allows_cold_production_but_exact_consumers_refuse(self):
        for exact in ({'required': True}, {'expected': self.root}, {}):
            with self.subTest(exact=exact):
                self.write_hint()
                for name in ('sdk-root', 'engine-root'):
                    (self.cache / name).symlink_to(self.record['sdk'])
                with patch.object(CACHE, 'verify_record', side_effect=ValueError('unsupported engine policy')), \
                        patch.object(CACHE, 'retain') as retain:
                    if exact:
                        with self.assertRaisesRegex(ValueError, 'unsupported engine policy'):
                            CACHE.restore(self.root, self.cache, **exact)
                        self.assertTrue((self.cache / 'selection.json').is_file())
                    else:
                        self.assertEqual('', CACHE.restore(self.root, self.cache))
                        self.assertEqual([], list(self.cache.iterdir()))
                    retain.assert_not_called()
                self.assertFalse((self.root / '.bl').exists())
                for path in self.cache.iterdir():
                    path.unlink()

    def test_capture_refuses_sdk_for_other_engine_without_relabeling_it(self):
        self.write_hint()
        with patch.object(CACHE, 'describe_sdk', return_value=self.record), \
                patch.object(CACHE, 'verify_record', return_value=self.record), \
                patch.object(CACHE, 'source_fingerprint', return_value='e' * 64), \
                patch.object(CACHE, 'retain') as retain:
            with self.assertRaisesRegex(ValueError, 'this checkout engine'):
                CACHE.capture(self.root, self.cache, Path(self.record['sdk']))
            retain.assert_not_called()
        self.assertEqual(self.record, json.loads((self.cache / 'selection.json').read_text()))

    def test_store_paths_cannot_escape_or_point_to_mutable_directories(self):
        for path in (str(self.root), '/nix/store/nope', '/nix/store/' + 'a' * 32 + '-sdk/../other'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                CACHE.store_path(path)

    def test_selector_requires_the_successful_run_and_exact_artifact_identity(self):
        selector = {'version': 1, 'kind': 'ci-sdk-selection', 'cache_key': 'enchant-nix-v1-Linux-X64-abcd-12-1-prepare-linux',
                    'sdk': self.record['sdk'], 'sdk_descriptor_sha256': 'c' * 64,
                    'candidate_sha256': 'f' * 64, 'engine_fingerprint': 'b' * 64,
                    'models': '/nix/store/' + '9' * 32 + '-models', 'model_pins_sha256': 'e' * 64,
                    'revision': '1' * 40, 'run_id': '12'}
        path = self.cache / 'public-selector.json'
        path.write_text(json.dumps(selector))
        self.assertEqual(selector, CACHE.read_selector(path, '1' * 40, '12'))
        for field, value in (('revision', '2' * 40), ('run_id', '13'),
                             ('cache_key', selector['cache_key'] + '\nother=bad'),
                             ('sdk', '/mutable/sdk'), ('candidate_sha256', 'f' * 63),
                             ('unreviewed_field', True)):
            with self.subTest(field=field):
                changed = dict(selector, **{field: value})
                path.write_text(json.dumps(changed))
                with self.assertRaisesRegex(ValueError, 'requested successful CI'):
                    CACHE.read_selector(path, '1' * 40, '12')

    def test_exact_consumer_rejects_other_producer_before_recreating_roots(self):
        self.write_hint()
        with patch.object(CACHE, 'verify_record', return_value=self.record), \
                patch.object(CACHE, 'retain') as retain:
            with self.assertRaisesRegex(ValueError, 'this run.s producer'):
                CACHE.restore(self.root, self.cache, expected=self.root, required=True)
            retain.assert_not_called()

    def test_canonical_source_fingerprint_ignores_receipt_and_detects_engine_edit(self):
        # Exercise the actual canonical implementation with a small declared
        # tree; restore/capture must never obtain a fingerprint from cache JSON.
        policy = {'version': 1, 'roots': ['bin'], 'excluded': ['bin/generated'],
                  'reserved': ['.git', '.bl'], 'targetRoots': ['bin'],
                  'limits': {'entries': 100, 'fileBytes': 1000, 'totalBytes': 10000, 'depth': 10}}
        (self.root / 'bin').mkdir()
        source = self.root / 'bin/bl'
        source.write_text('engine revision one')
        with patch.object(CACHE, 'ROOT', self.root):
            (self.root / 'scripts').mkdir()
            (self.root / 'scripts/sdk-inputs').symlink_to(ROOT / 'scripts/sdk-inputs')
            (self.root / 'nix').mkdir()
            (self.root / 'nix/engine-inputs.json').write_text(json.dumps(policy))
            before = CACHE.source_fingerprint(self.root)
            (self.root / '.bl').mkdir()
            (self.root / '.bl/cache-receipt.json').write_text('previous checkout selection')
            self.assertEqual(before, CACHE.source_fingerprint(self.root))
            source.write_text('engine revision two')
            self.assertNotEqual(before, CACHE.source_fingerprint(self.root))
