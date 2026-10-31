"""CI-only recipes cannot invalidate SDKs or relabel an older engine selection."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('engine_ci_cache', ROOT / 'scripts/ci-sdk-cache.py')
CACHE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CACHE)


class EngineCIInputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root, self.cache = self.base / 'checkout', self.base / 'cache'
        self.root.mkdir()
        self.cache.mkdir()
        self.policy = json.loads((ROOT / 'nix/engine-inputs.json').read_text())
        for name in self.policy['roots']:
            path = self.root / name
            if (ROOT / name).is_dir():
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('declared engine input: ' + name)
        for name in (*CACHE.CI_ONLY_EXCLUSIONS, 'bin/bl', 'priv/boot/compiler.bl',
                     'native/lazy_memo/src/lib.rs', 'native/lazy_memo/Cargo.lock',
                     'nix/bl-drop.nix', 'nix/compiler-product.nix', 'nix/native-compile.nix'):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('original source: ' + name)
        self.write_policy(self.root, self.policy)
        self.engine = self.base / 'retained-engine'
        shutil.copytree(self.root, self.engine)
        self.previous = dict(self.policy, excluded=[name for name in self.policy['excluded']
                                                  if name not in CACHE.CI_ONLY_EXCLUSIONS])
        self.write_policy(self.engine, self.previous)

    def write_policy(self, source, policy):
        (source / 'nix/engine-inputs.json').write_text(json.dumps(policy, sort_keys=True) + '\n')

    def test_exact_three_ci_recipes_can_change_be_added_or_removed(self):
        self.assertEqual({'nix/ci-check.nix', 'nix/ci-release-runtime.nix', 'nix/ci-sdk-gates.nix'},
                         set(CACHE.CI_ONLY_EXCLUSIONS))
        self.assertTrue(set(CACHE.CI_ONLY_EXCLUSIONS) <= set(self.policy['excluded']))
        before = CACHE.source_fingerprint(self.root)
        for name in CACHE.CI_ONLY_EXCLUSIONS:
            with self.subTest(name=name):
                path = self.root / name
                path.write_text('different CI check recipe')
                self.assertEqual(before, CACHE.source_fingerprint(self.root))
                path.unlink()
                self.assertEqual(before, CACHE.source_fingerprint(self.root))
                path.write_text('new CI check recipe')
                self.assertEqual(before, CACHE.source_fingerprint(self.root))

    def test_runtime_native_and_producer_changes_still_invalidate(self):
        before = CACHE.source_fingerprint(self.root)
        for name in ('bin/bl', 'priv/boot/compiler.bl', 'native/lazy_memo/src/lib.rs',
                     'native/lazy_memo/Cargo.lock', 'nix/bl-drop.nix', 'nix/compiler-product.nix',
                     'nix/native-compile.nix', 'nix/engine-inputs.json', 'flake.lock'):
            with self.subTest(name=name):
                path = self.root / name
                original = path.read_bytes()
                path.write_bytes(original + b'\nchanged producer input\n')
                self.assertNotEqual(before, CACHE.source_fingerprint(self.root))
                path.write_bytes(original)

    def test_exact_predecessor_keeps_its_captured_fingerprint(self):
        expected = CACHE.source_fingerprint(self.engine, self.previous)
        self.assertEqual(expected, CACHE.retained_source_fingerprint(self.engine))
        self.assertNotEqual(expected, CACHE.source_fingerprint(self.engine))
        self.assertNotEqual(expected, CACHE.source_fingerprint(self.root))
        # Old CI bytes remain part of the *old* identity, never ignored and
        # relabeled just because today's policy excludes them.
        (self.engine / CACHE.CI_ONLY_EXCLUSIONS[0]).write_text('mutated retained CI bytes')
        self.assertNotEqual(expected, CACHE.retained_source_fingerprint(self.engine))
        self.assertEqual(CACHE.source_fingerprint(self.root), CACHE.retained_source_fingerprint(self.root))

    def test_no_other_historical_policy_or_weaker_boundaries_are_accepted(self):
        variants = []
        value = copy.deepcopy(self.previous); value['excluded'].append('priv/boot'); variants.append(value)
        value = copy.deepcopy(self.previous); value['excluded'].remove('priv/native'); variants.append(value)
        value = copy.deepcopy(self.previous); value['excluded'].append(CACHE.CI_ONLY_EXCLUSIONS[0]); variants.append(value)
        value = copy.deepcopy(self.previous); value['roots'].remove('priv'); variants.append(value)
        value = copy.deepcopy(self.previous); value['limits']['depth'] += 1; variants.append(value)
        value = copy.deepcopy(self.previous); value['version'] = True; variants.append(value)
        value = copy.deepcopy(self.previous); value['reserved'].append('other'); variants.append(value)
        for policy in variants:
            with self.subTest(policy=policy):
                self.write_policy(self.engine, policy)
                with self.assertRaisesRegex(ValueError, 'exact CI-only predecessor'):
                    CACHE.retained_source_fingerprint(self.engine)

    def test_real_old_digest_is_restored_only_under_its_original_identity(self):
        # Mock only the store/admission transport; policy and Source hashing
        # remain real. Production still requires registered immutable outputs.
        sdk = '/nix/store/' + 'a' * 32 + '-old-sdk'
        description = {'version': 1, 'kind': 'ci-sdk-cache-hint', 'sdk': sdk,
                       'descriptor_sha256': 'c' * 64, 'unit_index_sha256': 'd' * 64}
        old = CACHE.source_fingerprint(self.engine, self.previous)
        record = dict(description, engine_source=str(self.engine), engine_fingerprint=old)
        hint = self.cache / 'selection.json'
        hint.write_text(json.dumps(record))
        original = hint.read_bytes()
        with patch.object(CACHE, 'describe_sdk', return_value=description), \
                patch.object(CACHE, 'store_path', side_effect=Path), \
                patch.object(CACHE.subprocess, 'run'):
            self.assertEqual(sdk, CACHE.restore(self.root, self.cache))
            self.assertEqual(record, CACHE.verify_record(record))
            with self.assertRaisesRegex(ValueError, 'no longer matches'):
                CACHE.verify_record(dict(record, engine_fingerprint=CACHE.source_fingerprint(self.root)))
            # A predecessor cannot produce a current qualification selector.
            selector = self.cache / 'selector.json'
            with self.assertRaisesRegex(ValueError, 'engine differs from this checkout'):
                CACHE.write_selector(self.root, self.cache, selector, 'key', '1' * 40, '12')
            self.assertFalse(selector.exists())
        self.assertEqual(original, hint.read_bytes())
        self.assertEqual(sdk, str((self.root / '.bl/sdks' / old / 'result-sdk').readlink()))
        self.assertFalse((self.root / '.bl/sdks' / CACHE.source_fingerprint(self.root)).exists())


if __name__ == '__main__':
    unittest.main()
