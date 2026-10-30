"""Fail-closed controls for the exact Python-unittest/TestRT adapter."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('qualification_driver',
    Path(__file__).with_name('execution-qualification-driver.py'))
DRIVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DRIVER)


class AdapterControls(unittest.TestCase):
    def execute(self, body, names=('Probe.test_case',)):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / 'fixture.py'
            path.write_text('import unittest\nclass Probe(unittest.TestCase):\n' + body)
            return DRIVER.execute(root, path, list(names))

    def test_exact_nonempty_execution(self):
        report = self.execute(' def test_case(self): self.assertEqual(42, 42)\n')
        self.assertTrue(report['complete'])
        self.assertEqual(['Probe.test_case'], report['passed'])
        self.assertEqual(1, report['tests_run'])

    def test_missing_empty_duplicate_and_import_failure_refuse(self):
        for names in [(), ('Probe.missing',), ('Probe.test_case',) * 2]:
            with self.subTest(names=names), self.assertRaises(ValueError):
                self.execute(' def test_case(self): pass\n', names)
        with self.assertRaises(SyntaxError):
            self.execute(' invalid Python !\n')

    def test_failure_and_error_never_pass(self):
        for body in [' self.fail("original failure")', ' raise RuntimeError("load body")']:
            with self.subTest(body=body):
                report = self.execute(' def test_case(self):' + body + '\n')
                self.assertFalse(report['complete'])
                self.assertEqual([], report['passed'])

    def test_skip_and_expected_failure_never_pass(self):
        for decorator, body in [('@unittest.skip("missing prerequisite")', 'pass'),
                                ('@unittest.expectedFailure', 'self.fail("expected")')]:
            with self.subTest(decorator=decorator):
                report = self.execute(' ' + decorator + '\n def test_case(self): ' + body + '\n')
                self.assertFalse(report['complete'])

    def test_selection_does_not_run_unselected_methods(self):
        report = self.execute(' def test_case(self): self.assertTrue(True)\n'
                              ' def test_other(self): self.fail("not selected")\n')
        self.assertTrue(report['complete'])
        self.assertEqual(1, report['tests_run'])

    def test_setup_failure_never_counts_as_selected_success(self):
        report = self.execute(' @classmethod\n def setUpClass(cls): raise RuntimeError("setup")\n'
                              ' def test_case(self): self.assertTrue(True)\n')
        self.assertFalse(report['complete'])
        self.assertEqual(0, report['tests_run'])

    def test_path_outside_snapshot_refuses(self):
        with self.assertRaises(ValueError):
            DRIVER.execute(Path('/definitely-not-this-tree'), Path(__file__), ['anything'])


if __name__ == '__main__':
    unittest.main()
