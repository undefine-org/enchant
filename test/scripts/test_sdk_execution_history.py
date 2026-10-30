"""Exact SDK selector handovers cannot invent, skip or reorder a test file."""
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location('sdk_history', Path(__file__).with_name('sdk_execution_history.py'))
history = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(history)


class HandoverControls(unittest.TestCase):
    def setUp(self):
        self.pending = [{'path': 'one.bl', 'selectors': []}, {'path': 'two.bl', 'selectors': []}]

    def test_only_exact_progressing_prefix_can_hand_over(self):
        files = [{'path': 'one.bl', 'status': 'passed'}]
        execution = {'files': files, 'remaining': self.pending[1:], 'handover': 'native-lifetime-budget'}
        self.assertEqual(history.accept_partial(execution, self.pending), (files, self.pending[1:]))
        complete = {'files': files + [{'path': 'two.bl'}], 'remaining': []}
        self.assertEqual(history.accept_partial(complete, self.pending)[1], [])

    def test_empty_duplicate_reordered_missing_or_unannounced_handover_refuses(self):
        for execution in [
            {'files': [], 'remaining': self.pending, 'handover': 'budget'},
            {'files': [{'path': 'two.bl'}], 'remaining': self.pending[1:], 'handover': 'budget'},
            {'files': [{'path': 'one.bl'}, {'path': 'one.bl'}], 'remaining': []},
            {'files': [{'path': 'one.bl'}], 'remaining': []},
            {'files': [{'path': 'one.bl'}], 'remaining': self.pending[1:]},
        ]:
            with self.subTest(execution=execution), self.assertRaises(ValueError):
                history.accept_partial(execution, self.pending)
