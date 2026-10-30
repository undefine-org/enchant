import copy
import json
from pathlib import Path
import runpy
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
PROFILE = runpy.run_path(str(ROOT / 'scripts/sdk_sealed_profiles.py'))


class SealedProfiles(unittest.TestCase):
    def test_existing_test_timings_keep_namespace_and_exclude_startup(self):
        slowest = runpy.run_path(str(ROOT / 'scripts/test_timings.py'))['slowest']
        self.assertEqual([{'namespace': 'two', 'test': 'slow', 'milliseconds': 12},
                          {'namespace': 'one', 'test': 'fast', 'milliseconds': 0}],
                         slowest('startup 4000ms\nTesting one\n  fast  0ms\nTesting two\n  slow  12ms\n'))

    def test_default_complete_mode_keeps_every_prior_check_and_new_custody_checks(self):
        selection = PROFILE['plan']()
        matrix = json.loads((ROOT / 'research/phase-compiler/sdk-boundary-consumers.json').read_text())
        self.assertEqual({b['id'] for b in matrix['boundaries']}, set(selection['boundaries']))
        self.assertEqual(list(PROFILE['GROUPS']), [g['id'] for g in selection['groups']])
        # Two added fixture-fill assertions observe capacity under its native fence.
        # One export assertion now explicitly checks raw factory refusal.
        # Twelve assertions cover bootstrap Source-function selection.
        # Sixteen assertions cover literal SDK values across phase instances.
        # Ten assertions cover bounded vector conversion and finite-stream join adapters.
        # Four assertions retain primitive value ABI overloads over direct-link rows.
        # Phase resolution metadata34 is Source-free; Source binding tests stay ordinary-only.
        # SDK phase functions22 and constructor sessions50 retain shared ownership/fuel checks.
        # SDK datum macros49 and syntax43 keep their distinct conversion/hygiene protocols.
        # Native macro binding22 reuses the same callable/session owner for computed recipes.
        # Source macros62 include hygienic backticks, private/archive/higher-phase references and bounded splices.
        self.assertEqual(1010 + 92 + 71 + 60 + 30 + 5 + 2 + 32 + 16 + 106 + 34 + 24 + 1 + 24 + 107 + 41 + 40 + 150 + 105 + 4 + 12 + 75 + 82 + 16 + 4 + 14 + 4 + 7 + 19 + 18 + 27 + 18 + 13 + 71 + 19 + 14 + 4 + 5 + 2 + 2 + 19 + 78 + 13 + 66 + 14 + 103 + 56 + 9 + 16 + 62 + 101 + 47 + 51 + 174 + 47 + 20 + 32 + 16 + 29 + 9 + 25 + 7 + 3 + 23 + 27 + 32 + 29 + 68 + 1 + 20 + 2 + 29 + 16 + 32 + 32 + 43 + 25 + 11 + 6 + 58 + 12 + 22 + 28 + 3 + 1 + 16 + 26 + 43 + 22 + 40 + 34 + 4 + 10 + 7 + 6 + 2 + 3 + 3 + 10 + 22 + 23 + 62, selection['assertions'])
        self.assertEqual('complete', selection['mode'])
        self.assertTrue(selection['pipeline'])
        self.assertTrue(selection['solver'])
        self.assertTrue(selection['sdk-initialization'])
        self.assertIn('proc.reg', selection['roots'])

    def test_focused_custody_avoids_unrelated_analyses_and_retains_universal_integrity(self):
        selection = PROFILE['plan'](['filesystem-custody'])
        self.assertEqual(['filesystem', 'filesystem-operations', 'filesystem-refresh', 'filesystem-regressions'], [g['id'] for g in selection['groups']])
        self.assertFalse(selection['pipeline'])
        self.assertFalse(selection['solver'])
        self.assertFalse(selection['sdk-initialization'])
        self.assertEqual(['selfbuild', 'vm.native', 'build', 'artifact', 'bl.artifacts', 'deps-compile'], selection['roots'])
        self.assertEqual(PROFILE['UNIVERSAL'], selection['universal'])
        self.assertEqual('focused', selection['mode'])

    def test_lexical_catch_selection_includes_dynamic_class_manifest(self):
        selection = PROFILE['plan'](['unit-metadata'])
        self.assertIn('java.manifest', selection['roots'])
        source = '\n'.join((ROOT / path).read_text() for path in
                           ['priv/boot/compiler.bl', 'priv/boot/anf.bl',
                            'priv/boot/lower.bl', 'priv/boot/expand.bl'])
        fixed = set(re.findall(r'BeamLisp.Loader/ensure_loaded "([^"]+)"', source))
        self.assertTrue(fixed)
        self.assertTrue(fixed.issubset(selection['roots']))
        self.assertNotIn('java.manifest', PROFILE['plan'](['filesystem-custody'])['roots'])

    def test_factory_profile_carries_actual_sealed_fixture_helpers(self):
        selection = PROFILE['plan'](['sealed-loader'])
        self.assertIn('test.support.source-fixtures', selection['roots'])
        self.assertTrue({'vm.core', 'vm.manager', 'vm.realm', 'vm.session', 'vm.client'}.issubset(selection['roots']))
        self.assertIn(('test/bl/contextual_profile_recovery_test.bl', 11),
                      PROFILE['GROUPS']['factory-admission'][0])
        self.assertIn(('test/bl/contextual_allocation_custody_test.bl', 25),
                      PROFILE['GROUPS']['factory-admission'][0])
        self.assertIn(('test/bl/contextual_session_retirement_test.bl', 43),
                      PROFILE['GROUPS']['factory-admission'][0])
        self.assertIn(('test/bl/contextual_realm_retirement_test.bl', 32),
                      PROFILE['GROUPS']['factory-admission'][0])
        self.assertIn(('test/bl/contextual_parent_admission_test.bl', 16),
                      PROFILE['GROUPS']['factory-admission'][0])
        self.assertIn(('test/bl/contextual_loader_failure_test.bl', 29),
                      PROFILE['GROUPS']['factory-admission'][0])
        producer = (ROOT / 'scripts/demo-sdk-artifacts').read_text()
        for name in ['source_effect_observer.bl', 'source_instance_guard.bl', 'unit_instance_observer.bl']:
            self.assertIn("root / 'test/fixtures/" + name + "'", producer)

    def test_empty_duplicate_and_unknown_boundaries_refuse(self):
        for requested in [[], ['missing'], ['sealed-loader', 'sealed-loader']]:
            with self.subTest(requested=requested), self.assertRaises(ValueError):
                PROFILE['plan'](requested)

    def test_first_sdk_initialization_is_required_only_for_affected_boundaries(self):
        affected = PROFILE['plan'](['unit-metadata'])
        unrelated = PROFILE['plan'](['filesystem-custody'])
        self.assertIn('proc.reg', affected['roots'])
        self.assertIn('reload.source-guard', affected['roots'])
        # These fixed lazy loads avoid require cycles. Keep the initialization
        # receiver closed over every such generation preparation provider.
        source = (ROOT / 'priv/std/reload/generation.bl').read_text()
        fixed = re.findall(r'BeamLisp.Loader/ensure_loaded "([^"]+)"', source)
        self.assertTrue(fixed)
        self.assertTrue(set(fixed).issubset(affected['roots']))
        good = {'status': 'passed', 'fresh-receiver': True, 'source-free': True, 'sdk-source-compiles': 0}
        PROFILE['validate_initialization'](affected, good)
        PROFILE['validate_initialization'](unrelated, None)
        with self.assertRaises(ValueError):
            PROFILE['validate_initialization'](unrelated, good)
        for edit in [None, {}, dict(good, status='failed'), dict(good, **{'fresh-receiver': False}),
                     dict(good, **{'source-free': False}), dict(good, **{'sdk-source-compiles': 1}),
                     dict(good, **{'sdk-source-compiles': False})]:
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                PROFILE['validate_initialization'](affected, edit)

    def test_receipt_must_have_exact_requested_nonempty_files_and_actual_counts(self):
        selection = PROFILE['plan'](['vector-lookup-default'])
        good = {'status': 'passed', 'source-free': True, 'mode': 'focused',
                'boundaries': selection['boundaries'], 'pipeline': False, 'assertions': 65,
                'files': [{'group': 'vectors', 'path': 'test/bl/vector_get_default_test.bl',
                           'pass': 65, 'fail': 0, 'error': 0, 'tests': 2}]}
        PROFILE['validate'](selection, good)
        edits = [{'files': []}, {'mode': 'complete'}, {'boundaries': []}, {'pipeline': True}, {'assertions': 0}]
        for edit in edits:
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                PROFILE['validate'](selection, dict(good, **edit))
        for edit in [{'pass': 0}, {'fail': 1}, {'error': False}, {'tests': 0}, {'group': 'unrelated'}]:
            bad = copy.deepcopy(good)
            bad['files'][0].update(edit)
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                PROFILE['validate'](selection, bad)

    def test_each_universal_integrity_control_is_required_even_for_focused_mode(self):
        good = {'status': 'passed', 'source_free_sdk': True,
                'tampering_refused_before_initialization': True, 'missing_unit_refused_before_initialization': True,
                'sealed_source_consumers': {'status': 'passed'},
                'consumer': {'status': 'passed', 'legacy-compiles': 0, 'actual-sealed-image': True,
                             'class-image-proof': True, 'packaged-macro-new-project': True, 'sdk-source-absent': True}}
        PROFILE['validate_universal'](good)
        for key in good:
            bad = copy.deepcopy(good)
            bad.pop(key)
            with self.subTest(key=key), self.assertRaises(ValueError):
                PROFILE['validate_universal'](bad)


if __name__ == '__main__':
    unittest.main()
