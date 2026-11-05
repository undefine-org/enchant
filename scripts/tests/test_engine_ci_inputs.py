"""Generated state and CI recipes cannot invalidate SDKs or relabel old inputs."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import py_compile
import re
import shutil
import subprocess
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
        for name in (*CACHE.CI_ONLY_EXCLUSIONS, CACHE.DATOM_CHECK_EXCLUSION, 'bin/bl', 'priv/boot/compiler.bl',
                     'native/lazy_memo/src/lib.rs', 'native/lazy_memo/Cargo.lock',
                     'nix/bl-drop.nix', 'nix/compiler-product.nix', 'nix/native-compile.nix',
                     'nix/coordinator-runtime.nix'):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('original source: ' + name)
        self.write_policy(self.root, self.policy)
        self.engine = self.base / 'retained-engine'
        shutil.copytree(self.root, self.engine)
        shutil.copytree(self.engine / 'packages/job-runner', self.engine / 'vendor/foundry-ledger')
        self.before_datom = dict(self.policy, excluded=[name for name in self.policy['excluded']
                                                        if name != CACHE.DATOM_CHECK_EXCLUSION])
        self.legacy_policy = dict(self.before_datom, roots=[
            'vendor/foundry-ledger' if name == 'packages/job-runner' else name
            for name in self.policy['roots']])
        self.bytecode_previous = dict(self.legacy_policy, reserved=[name for name in self.policy['reserved']
                                                            if name != '__pycache__'])
        self.previous = dict(self.bytecode_previous, excluded=[name for name in self.bytecode_previous['excluded']
                                                             if name not in CACHE.CI_ONLY_EXCLUSIONS])
        self.write_policy(self.engine, self.previous)

    def write_policy(self, source, policy):
        (source / 'nix/engine-inputs.json').write_text(json.dumps(policy, sort_keys=True) + '\n')

    def capture(self):
        # Evaluate the actual canonical capture filter and derivation identity;
        # build no snapshot derivation, SDK, compiler or VM.
        expression = 'let product = import ' + json.dumps(str(ROOT / 'nix/sdk-source.nix')) + \
                     ' { source = ' + json.dumps(str(self.root)) + '; }; in ' + \
                     '{ derivation = product.drvPath; command = product.buildCommand; }'
        data = json.loads(subprocess.check_output(
            ['nix-instantiate', '--eval', '--strict', '--json', '--read-write-mode',
             '--expr', expression, '--option', 'experimental-features', 'nix-command flakes'],
            text=True, timeout=60))
        match = re.search(r'python3 (/nix/store/[a-z0-9]{32}-beam-lisp-engine-source)/scripts/sdk-inputs',
                          data['command'])
        self.assertIsNotNone(match, data['command'])
        return Path(match.group(1)), data['derivation']

    def test_generated_cache_and_backend_data_never_change_engine_capture(self):
        source = self.root / 'nix/application-inventory.py'
        source.write_text('VERSION = 1\n')
        before = CACHE.source_fingerprint(self.root)
        captured = self.capture()
        self.assertEqual(source.read_bytes(), (captured[0] / source.relative_to(self.root)).read_bytes())
        bytecode = Path(py_compile.compile(str(source), doraise=True))
        self.assertEqual('__pycache__', bytecode.parent.name)
        self.assertEqual(before, CACHE.source_fingerprint(self.root))
        self.assertEqual(captured, self.capture())
        self.assertFalse((captured[0] / 'nix/__pycache__').exists())
        for name in ('tooling/build-backends/ci.bl', 'tooling/build-backends/ci.nix'):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('operator-owned backend policy')
            self.assertEqual(before, CACHE.source_fingerprint(self.root))
            self.assertEqual(captured, self.capture())
        self.assertFalse((captured[0] / 'tooling/build-backends').exists())
        bytecode.write_bytes(bytecode.read_bytes() + b'edited generated cache')
        self.assertEqual(before, CACHE.source_fingerprint(self.root))
        self.assertEqual(captured, self.capture())
        bytecode.unlink()
        bytecode.parent.rmdir()
        self.assertEqual(before, CACHE.source_fingerprint(self.root))
        self.assertEqual(captured, self.capture())
        source.write_text('VERSION = 2\n')
        self.assertNotEqual(before, CACHE.source_fingerprint(self.root))
        changed = self.capture()
        self.assertNotEqual(captured[0], changed[0])
        self.assertNotEqual(captured[1], changed[1])
        self.assertEqual(source.read_bytes(), (changed[0] / source.relative_to(self.root)).read_bytes())

    def test_bytecode_predecessor_retains_its_own_cache_bytes_and_fingerprint(self):
        self.write_policy(self.engine, self.bytecode_previous)
        cache = self.engine / 'nix/__pycache__/application-inventory.pyc'
        cache.parent.mkdir()
        cache.write_bytes(b'actual retained bytecode bytes')
        original = CACHE.source_fingerprint(self.engine, self.bytecode_previous)
        self.assertEqual(original, CACHE.retained_source_fingerprint(self.engine))
        self.assertNotEqual(original, CACHE.source_fingerprint(self.engine))
        cache.write_bytes(b'changed retained bytecode bytes')
        self.assertNotEqual(original, CACHE.retained_source_fingerprint(self.engine))
        self.assertEqual(CACHE.source_fingerprint(self.engine, self.bytecode_previous),
                         CACHE.retained_source_fingerprint(self.engine))

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
                     'nix/native-compile.nix', 'nix/coordinator-runtime.nix',
                     'nix/engine-inputs.json', 'flake.lock'):
            with self.subTest(name=name):
                path = self.root / name
                original = path.read_bytes()
                path.write_bytes(original + b'\nchanged producer input\n')
                self.assertNotEqual(before, CACHE.source_fingerprint(self.root))
                path.write_bytes(original)

    def test_datom_death_recipe_stays_in_ci_but_not_the_sdk_snapshot(self):
        path = self.root / CACHE.DATOM_CHECK_EXCLUSION
        self.assertIn(CACHE.DATOM_CHECK_EXCLUSION, self.policy['excluded'])
        before, captured = CACHE.source_fingerprint(self.root), self.capture()
        self.assertFalse((captured[0] / CACHE.DATOM_CHECK_EXCLUSION).exists())
        spec = importlib.util.spec_from_file_location('ci_full_source', ROOT / 'scripts/ci-source.py')
        ci = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ci)
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        ci.capture(self.root, self.base / 'ci-before')
        original = path.read_bytes()
        path.write_bytes(original + b'\nchanged CI death fixture\n')
        self.assertEqual(before, CACHE.source_fingerprint(self.root))
        self.assertEqual(captured, self.capture())
        ci.capture(self.root, self.base / 'ci-after')
        self.assertEqual(original, (self.base / 'ci-before' / CACHE.DATOM_CHECK_EXCLUSION).read_bytes())
        self.assertEqual(path.read_bytes(), (self.base / 'ci-after' / CACHE.DATOM_CHECK_EXCLUSION).read_bytes())

    def test_before_datom_policy_hashes_its_own_fixture_bytes(self):
        self.write_policy(self.engine, self.before_datom)
        expected = CACHE.source_fingerprint(self.engine, self.before_datom)
        self.assertEqual(expected, CACHE.retained_source_fingerprint(self.engine))
        self.assertNotEqual(expected, CACHE.source_fingerprint(self.engine))
        path = self.engine / CACHE.DATOM_CHECK_EXCLUSION
        current = CACHE.source_fingerprint(self.engine)
        path.write_text('changed bytes under the original captured policy')
        self.assertNotEqual(expected, CACHE.retained_source_fingerprint(self.engine))
        self.assertEqual(current, CACHE.source_fingerprint(self.engine))

    def test_platform_cache_ignores_ci_but_recaptures_native_policy_and_selector_edits(self):
        script = self.root / 'scripts/prepare-checkout-platform'
        shutil.copy2(ROOT / 'scripts/prepare-checkout-platform', script)
        tools, output, calls = self.base / 'tools', self.base / 'platform', self.base / 'calls'
        tools.mkdir(); output.mkdir()
        (output / 'platform.json').write_text('{}')
        # Mock only realization/manager transport; execute the actual selector
        # and its complete filesystem hashing on each invocation.
        manager = tools / 'systemd-run'
        manager.write_text('#!/usr/bin/env python3\nimport os,sys\ni=sys.argv.index("nix-build")\nos.execvp(sys.argv[i],sys.argv[i:])\n')
        builder = tools / 'nix-build'
        builder.write_text('#!/usr/bin/env python3\nimport os,sys\nfrom pathlib import Path\n'
            'link=Path(sys.argv[sys.argv.index("--out-link")+1])\n'
            'link.symlink_to(os.environ["PLATFORM_FIXTURE_OUTPUT"])\n'
            'with open(os.environ["PLATFORM_FIXTURE_CALLS"],"a") as f:f.write(link.name+"\\n")\n')
        manager.chmod(0o755); builder.chmod(0o755)
        env = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ['PATH'],
                   PLATFORM_FIXTURE_OUTPUT=str(output), PLATFORM_FIXTURE_CALLS=str(calls))

        def select():
            self.assertEqual(str(output), subprocess.check_output([str(script)], cwd=self.base,
                                                                  env=env, text=True).strip())
            return calls.read_text().splitlines()

        first = select()
        self.assertEqual(1, len(first))
        for name in (*CACHE.CI_ONLY_EXCLUSIONS, CACHE.DATOM_CHECK_EXCLUSION):
            path = self.root / name
            path.write_text('changed CI recipe')
            self.assertEqual(first, select())
            path.unlink()
            self.assertEqual(first, select())
            path.write_text('recreated CI recipe')
            self.assertEqual(first, select())
        for count, path in enumerate((self.root / 'native/lazy_memo/src/lib.rs',
                                      self.root / 'nix/engine-inputs.json', script), start=2):
            path.write_bytes(path.read_bytes() + b'\n# changed producer input\n')
            self.assertEqual(count, len(select()))

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

    def test_compiler_preparation_root_additions_keep_exact_old_identities(self):
        policy = copy.deepcopy(self.legacy_policy)
        for additions in (
                ('scripts/retain-producer.bl',),
                ('scripts/restore-producer.exs',),
                ('scripts/retain-compiler-preparation.py',),
                ('scripts/assemble-compiler-generations.py',
                 'scripts/compiler-unit-baseline.py', 'scripts/check-produced-compiler.py')):
            policy['roots'] = [name for name in policy['roots'] if name not in additions]
            self.write_policy(self.engine, policy)
            expected = CACHE.source_fingerprint(self.engine, policy)
            self.assertEqual(expected, CACHE.retained_source_fingerprint(self.engine))
            self.assertNotEqual(CACHE.source_fingerprint(self.root), expected)
            # Existing declared compiler bytes remain part of the old identity.
            source = self.engine / 'priv/boot/compiler.bl'
            source.write_text(source.read_text() + '\nchanged compiler')
            self.assertNotEqual(expected, CACHE.retained_source_fingerprint(self.engine))

    def test_no_other_historical_policy_or_weaker_boundaries_are_accepted(self):
        variants = []
        value = copy.deepcopy(self.previous); value['excluded'].append('priv/boot'); variants.append(value)
        value = copy.deepcopy(self.previous); value['excluded'].remove('priv/native'); variants.append(value)
        value = copy.deepcopy(self.previous); value['excluded'].append(CACHE.CI_ONLY_EXCLUSIONS[0]); variants.append(value)
        value = copy.deepcopy(self.previous); value['roots'].remove('priv'); variants.append(value)
        value = copy.deepcopy(self.previous); value['limits']['depth'] += 1; variants.append(value)
        value = copy.deepcopy(self.previous); value['version'] = True; variants.append(value)
        value = copy.deepcopy(self.previous); value['reserved'].append('other'); variants.append(value)
        # This cross-product never existed: excluding bytecode was introduced
        # after the three CI-only exclusions, not before them.
        value = copy.deepcopy(self.previous); value['reserved'].append('__pycache__'); variants.append(value)
        # The Datom exclusion did not exist with the old framework root.
        value = copy.deepcopy(self.legacy_policy); value['excluded'].append(CACHE.DATOM_CHECK_EXCLUSION); variants.append(value)
        for policy in variants:
            with self.subTest(policy=policy):
                self.write_policy(self.engine, policy)
                with self.assertRaisesRegex(ValueError, 'exact supported predecessor'):
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
