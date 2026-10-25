#!/usr/bin/env python3
"""Receipt/manifest failure controls; no BEAM processes are started here."""
import copy
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
loader = importlib.machinery.SourceFileLoader('execution_history', str(ROOT / 'scripts/check-execution-history'))
spec = importlib.util.spec_from_loader(loader.name, loader)
history = importlib.util.module_from_spec(spec)
loader.exec_module(history)


class ReceiptControls(unittest.TestCase):
    def setUp(self):
        self.plan = [{'path': 'one.bl', 'selectors': [{'namespace': 'one', 'test': 'real'}]}]
        self.files = [{'path': 'one.bl', 'status': 'passed', 'tests': [
            {'namespace': 'one', 'test': 'real', 'pass': 2, 'fail': 0, 'error': 0}]}]

    def test_nonempty_exact_test_is_accepted(self):
        actual = history.validate_execution(self.files, self.plan)
        self.assertEqual(actual[('one.bl', 'one', 'real')]['pass'], 2)

    def test_missing_duplicate_or_extra_file_is_rejected(self):
        for files in [[], self.files * 2, [dict(self.files[0], path='other.bl')]]:
            with self.subTest(files=files), self.assertRaises(ValueError):
                history.validate_execution(files, self.plan)

    def test_missing_duplicate_or_extra_selector_is_rejected(self):
        for tests in [[], self.files[0]['tests'] * 2,
                      [dict(self.files[0]['tests'][0], test='other')]]:
            with self.subTest(tests=tests), self.assertRaises(ValueError):
                history.validate_execution([dict(self.files[0], tests=tests)], self.plan)

    def test_zero_negative_boolean_failed_and_missing_counters_are_rejected(self):
        for edit in [{'pass': 0}, {'pass': -1}, {'pass': True}, {'fail': 1},
                     {'error': 1}, {'fail': None}, {'error': None}, {'fail': False}, {'error': False}]:
            files = copy.deepcopy(self.files)
            files[0]['tests'][0].update(edit)
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                history.validate_execution(files, self.plan)

    def test_file_load_failure_cannot_be_a_green_receipt(self):
        with self.assertRaises(ValueError):
            history.validate_execution([dict(self.files[0], status='failed')], self.plan)

    def test_child_identity_must_match_the_captured_root_and_floor(self):
        frozen = {'floor': {'manifest.term': 'floor'}}
        image = {'priv-root': str(ROOT / 'priv'), 'manifest-sha256': 'floor', 'compiler-key': 'a' * 64}
        history.validate_identity(image, ROOT, frozen)
        for edit in [{'priv-root': '/another/tree'}, {'manifest-sha256': 'old'}, {'compiler-key': None}]:
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                history.validate_identity(dict(image, **edit), ROOT, frozen)


class CaptureControls(unittest.TestCase):
    def test_solver_override_bytes_path_and_disappearance_invalidate_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundled = root / 'priv/z3/bin/z3'
            bundled.parent.mkdir(parents=True)
            bundled.write_bytes(b'bundled solver')
            override = root / 'other-z3'
            override.write_bytes(b'override solver')
            with mock.patch.dict(history.os.environ, {'BEAM_LISP_Z3': str(override)}):
                before = history.capture_tools(root)
                self.assertEqual(before['z3']['selected']['sha256'], history.digest(override))
                override.write_bytes(b'changed solver')
                self.assertNotEqual(before, history.capture_tools(root))
                override.write_bytes(b'override solver')
                override.unlink()
                self.assertEqual(history.capture_tools(root)['z3']['selected']['sha256'], history.digest(bundled))
            with mock.patch.dict(history.os.environ, {}, clear=True):
                selected = history.capture_tools(root)
                self.assertEqual(selected['z3']['selected']['sha256'], history.digest(bundled))
                self.assertNotEqual(before, selected)

    def test_child_solver_receipt_must_match_the_captured_bytes_and_path(self):
        expected = {'resolved': str(ROOT / 'solver'), 'sha256': 'exact'}
        frozen = {'floor': {'manifest.term': 'floor'}, 'tools': {'z3': {'selected': expected}}}
        image = {'priv-root': str(ROOT / 'priv'), 'manifest-sha256': 'floor', 'compiler-key': 'a' * 64,
                 'tools': {'z3': {'path': str(ROOT / 'solver'), 'sha256': 'exact'}}}
        history.validate_identity(image, ROOT, frozen)
        for actual in [None, {'path': '/another/solver', 'sha256': 'exact'},
                       {'path': str(ROOT / 'solver'), 'sha256': 'changed'}]:
            with self.subTest(actual=actual), self.assertRaises(ValueError):
                history.validate_identity(dict(image, tools={'z3': actual}), ROOT, frozen)

    def test_workflow_launcher_and_toolchain_edits_invalidate_the_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for directory in ['priv/bootstrap/seed', 'test/scripts', 'scripts',
                              'native', 'bin', '.github/workflows']:
                (root / directory).mkdir(parents=True)
            manifest = root / history.MANIFEST
            manifest.parent.mkdir(parents=True)
            for path in ['env.bl', history.FINDINGS, history.MANIFEST, history.DRIVER,
                         'scripts/check-execution-history', 'bin/bl', 'flake.nix',
                         'flake.lock', '.github/workflows/ci.yml']:
                (root / path).write_text('original')
            before = history.capture(root, manifest)
            for path in ['bin/bl', 'flake.nix', 'flake.lock', '.github/workflows/ci.yml']:
                with self.subTest(path=path):
                    file = root / path
                    file.write_text('changed')
                    self.assertNotEqual(before, history.capture(root, manifest))
                    file.write_text('original')
                    self.assertEqual(before, history.capture(root, manifest))
            workflow = root / '.github/workflows/new.yml'
            workflow.write_text('new required gate')
            self.assertNotEqual(before, history.capture(root, manifest))
            workflow.unlink()
            (root / 'flake.lock').unlink()
            self.assertNotEqual(before, history.capture(root, manifest))


class ManifestControls(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / history.MANIFEST
        self.data = json.loads(self.path.read_text())

    def read(self, data):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'cases.json'
            path.write_text(json.dumps(data))
            return history.read_manifest(ROOT, path)

    def test_original_inventory_and_bound_controls_do_not_claim_execution(self):
        cases = self.read(self.data)
        report = history.audit(cases)
        self.assertEqual(len(cases), 86)
        self.assertEqual(len(report['open']), 73)
        self.assertFalse(report['executed'])
        self.assertFalse(report['complete_goal'])

    def test_missing_duplicate_or_renamed_case_is_rejected(self):
        for cases in [self.data['cases'][:-1], self.data['cases'][:-1] + [self.data['cases'][0]]]:
            with self.subTest(), self.assertRaises(ValueError):
                self.read(dict(self.data, cases=cases))

    def test_changed_original_evidence_is_rejected(self):
        with self.assertRaises(ValueError):
            self.read(dict(self.data, findings_sha256='changed'))

    def test_changed_case_identity_is_rejected(self):
        self.data['cases'][0]['issue'] = 'unrelated easier requirement'
        with self.assertRaises(ValueError):
            self.read(self.data)

    def test_stale_producer_or_unbound_causal_selector_is_rejected(self):
        for edit in [{'producer_sha256': 'changed'}, {'selector': {
                'path': 'absent.bl', 'namespace': 'absent', 'test': 'absent'}}]:
            data = copy.deepcopy(self.data)
            case = next(c for c in data['cases'] if c['id'] == 'E02')
            case['baseline'].update(edit)
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                self.read(data)

    def test_noop_or_missing_anchor_causal_mutation_is_rejected(self):
        for edit in [{'after': '(Map/put slots root now)'}, {'before': 'missing anchor'}]:
            data = copy.deepcopy(self.data)
            case = next(c for c in data['cases'] if c['id'] == 'E02')
            case['baseline'].update(edit)
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                self.read(data)

    def test_causal_binding_requires_both_roles_and_no_remaining_variant(self):
        cases = self.read(self.data)
        case = copy.deepcopy(next(c for c in cases if c['id'] == 'E02'))
        self.assertTrue(history.controls_bound(case))
        case['remaining'] = ['a variant still needs proof']
        self.assertFalse(history.controls_bound(case))
        case['remaining'] = []
        case.pop('baseline')
        self.assertFalse(history.controls_bound(case))

    def test_missing_or_escaped_test_path_is_rejected(self):
        for path in ['test/bl/does-not-exist.bl', '../AGENTS.md']:
            data = copy.deepcopy(self.data)
            data['cases'][0]['selectors'][0]['path'] = path
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.read(data)

    def test_duplicate_selector_is_rejected(self):
        self.data['cases'][0]['selectors'] *= 2
        with self.assertRaises(ValueError):
            self.read(self.data)

    def test_positive_only_or_outstanding_baseline_stays_open(self):
        case = {'id': 'E02', 'selectors': [{'roles': ['positive']}], 'remaining': []}
        self.assertEqual(len(history.audit([case])['open']), 1)
        case['selectors'][0]['roles'].append('original-negative')
        case['remaining'] = ['baseline missing']
        self.assertEqual(len(history.audit([case])['open']), 1)


class ParentFailureControls(unittest.TestCase):
    def setUp(self):
        self.case = {'id': 'E02', 'selectors': [{'path': 'one.bl', 'namespace': 'one',
                     'test': 'real', 'roles': ['positive', 'original-negative']}],
                     'remaining': ['baseline missing']}
        self.frozen = {'inputs': {}, 'floor': {'manifest.term': 'floor'}}

    def execute(self, output):
        return history.run(ROOT, ROOT / history.MANIFEST, [self.case], ['E02'], output, 30)

    def test_failed_child_and_timeout_leave_failed_receipts(self):
        failures = [history.subprocess.CompletedProcess([], 9), history.subprocess.TimeoutExpired([], 30)]
        for failure in failures:
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / 'run'
                with mock.patch.object(history, 'capture', return_value=self.frozen), \
                     mock.patch.object(history.subprocess, 'run') as child:
                    if isinstance(failure, Exception):
                        child.side_effect = failure
                    else:
                        child.return_value = failure
                    with self.assertRaises((ValueError, history.subprocess.TimeoutExpired)):
                        self.execute(out)
                self.assertEqual(json.loads((out / 'result.json').read_text())['status'], 'failed')

    def test_input_drift_is_rejected_before_accepting_child_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'run'
            with mock.patch.object(history, 'capture', side_effect=[self.frozen, {'changed': True}]), \
                 mock.patch.object(history.subprocess, 'run', return_value=history.subprocess.CompletedProcess([], 0)):
                with self.assertRaisesRegex(ValueError, 'inputs changed'):
                    self.execute(out)
            self.assertEqual(json.loads((out / 'result.json').read_text())['status'], 'failed')

    def test_existing_receipts_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'run'
            out.mkdir()
            (out / 'result.json').write_text('preserve me')
            with self.assertRaisesRegex(ValueError, 'output must be absent'):
                self.execute(out)
            self.assertEqual((out / 'result.json').read_text(), 'preserve me')

    def test_unbound_case_refuses_before_starting_any_child(self):
        self.case['selectors'] = []
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(history.subprocess, 'run') as child:
            with self.assertRaisesRegex(ValueError, 'no executable selector'):
                self.execute(Path(tmp) / 'run')
            child.assert_not_called()


if __name__ == '__main__':
    unittest.main()
