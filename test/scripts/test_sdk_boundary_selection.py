#!/usr/bin/env python3
"""Focused qualification may not silently omit requested boundary coverage."""
import runpy
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
select = runpy.run_path(str(ROOT / 'scripts/preflight-sdk-boundaries'))['select_boundaries']


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


if __name__ == '__main__':
    unittest.main()
