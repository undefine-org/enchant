#!/usr/bin/env python3
"""Frame admission must keep sparse review distinct from complete film export."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('clock', Path(__file__).resolve().parents[2] / 'examples/scene-renderer/frame_plan.py')
clock = importlib.util.module_from_spec(spec)
spec.loader.exec_module(clock)


def sparse():
    return {'version': 2, 'selection': [0, 990, 3599],
            'frames': [{'frame': k, 'time': k / 60} for k in [0, 990, 3599]]}


class Admission(unittest.TestCase):
    def test_review_uses_only_captured_indices(self):
        frames, requested = clock.select_frames(sparse(), 3600, None, [], False)
        self.assertEqual([0, 990, 3599], requested)
        self.assertEqual(16.5, frames[990]['time'])

    def test_sparse_plan_cannot_export_film(self):
        with self.assertRaises(ValueError):
            clock.select_frames(sparse(), 3600, None, [], True)

    def test_missing_review_frame_refuses(self):
        with self.assertRaises(ValueError):
            clock.select_frames(sparse(), 3600, '1', [], False)

    def test_duplicate_selection_refuses(self):
        plan = sparse()
        plan['selection'][1] = 0
        with self.assertRaises(ValueError):
            clock.validate_clock(plan, 3600)

    def test_partial_dense_plan_refuses(self):
        plan = sparse()
        del plan['selection']
        plan['version'] = 1
        with self.assertRaises(ValueError):
            clock.validate_clock(plan, 3600)

    def test_clock_nan_and_boolean_refuse(self):
        for value in [float('nan'), True]:
            plan = sparse()
            plan['frames'][0]['time'] = value
            with self.assertRaises(ValueError):
                clock.validate_clock(plan, 3600)

    def test_frame_number_must_match_capture(self):
        plan = sparse()
        plan['frames'][1]['frame'] = 991
        with self.assertRaises(ValueError):
            clock.validate_clock(plan, 3600)

    def test_complete_dense_clock_still_exports(self):
        plan = {'version': 1, 'frames': [{'frame': k, 'time': k / 60} for k in range(1800)]}
        frames, requested = clock.select_frames(plan, 1800, None, [0, 1799], True)
        self.assertEqual(1800, len(frames))
        self.assertEqual([0, 1799], requested)


if __name__ == '__main__':
    unittest.main()
