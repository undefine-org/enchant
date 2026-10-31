#!/usr/bin/env python3
"""Focused qualification may not silently omit requested boundary coverage."""
import runpy
import copy
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
gate = runpy.run_path(str(ROOT / 'scripts/preflight-sdk-boundaries'))
select = gate['select_boundaries']


class BoundarySelectionControls(unittest.TestCase):
    def setUp(self):
        self.boundaries = [{'id': 'record', 'tests': ['record.bl']},
                           {'id': 'preboot', 'tests': ['preboot.bl']}]

    def test_default_keeps_every_boundary(self):
        self.assertEqual(select(self.boundaries, None), self.boundaries)

    def test_focused_selection_retains_only_requested_coverage(self):
        self.assertEqual(select(self.boundaries, ['preboot']), [self.boundaries[1]])
        self.assertEqual(select(self.boundaries, ['preboot', 'record']), self.boundaries)

    def test_unknown_empty_and_duplicate_requests_refuse(self):
        for requested in [['absent'], [], ['record', 'record'], ['preboot', 'absent']]:
            with self.subTest(requested=requested), self.assertRaises(ValueError):
                select(self.boundaries, requested)

    def test_empty_or_duplicate_map_refuses_even_with_default_selection(self):
        for inventory in [[], self.boundaries + [self.boundaries[0]]]:
            with self.subTest(inventory=inventory), self.assertRaises(ValueError):
                select(inventory, None)

    def test_producer_control_keeps_its_context_without_dropping_coverage(self):
        producer = 'test/bl/aot_sdk_constructor_staging_test.bl'
        files = ['one.bl', producer, 'two.bl']
        self.assertEqual(gate['consumer_contexts'](files, True), ([producer], ['one.bl', 'two.bl']))
        self.assertEqual(gate['consumer_contexts'](files, False), ([], files))


class ConsumerReceiptControls(unittest.TestCase):
    def setUp(self):
        identity = {'candidate': 'a' * 64, 'source': 'b' * 64}
        self.events = [
            {'file': 'one.bl', 'status': 'passed', 'tests': 1, 'pass': 2, 'fail': 0, 'error': 0,
             'identity': identity},
            {'type': 'process', 'process_status': 0, 'identity': identity},
            {'type': 'batch', 'process_status': 0, 'identity': identity},
        ]

    def check(self, events, files=('one.bl',)):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'results.jsonl'
            path.write_text(''.join(json.dumps(row) + '\n' for row in events))
            return gate['consumer_receipts'](path, list(files))

    def test_actual_file_and_lifetime_handover_receipts_are_preserved(self):
        handover = {'type': 'handover', 'identity': self.events[0]['identity'],
                    'reason': 'native-lifetime-budget'}
        rows, handovers = self.check([*self.events[:-1], handover, self.events[-1]])
        self.assertEqual(rows[0]['pass'], 2)
        self.assertEqual(handovers, [handover])

    def test_failed_process_or_missing_batch_cannot_hide_behind_passed_files(self):
        for events in [self.events[:-1], [self.events[0], self.events[-1]],
                       [self.events[0], dict(self.events[1], process_status=1), self.events[-1]]]:
            with self.subTest(events=events), self.assertRaises(RuntimeError):
                self.check(events)

    def test_missing_duplicate_or_unrequested_files_refuse(self):
        for events in [self.events[1:], [self.events[0], *self.events],
                       [dict(self.events[0], file='other.bl'), *self.events[1:]]]:
            with self.subTest(events=events), self.assertRaises(RuntimeError):
                self.check(events)

    def test_mixed_identity_or_empty_failed_and_noninteger_coverage_refuses(self):
        for edit in [{'identity': {'candidate': 'c' * 64, 'source': 'b' * 64}},
                     {'pass': 0}, {'tests': 0}, {'pass': True}, {'fail': 1}, {'error': 1}, {'status': 'incoherent'}]:
            events = copy.deepcopy(self.events)
            events[0].update(edit)
            with self.subTest(edit=edit), self.assertRaises(RuntimeError):
                self.check(events)


if __name__ == '__main__':
    unittest.main()
