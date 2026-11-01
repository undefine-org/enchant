"""Filesystem-only checks of preparation hints; inert bytes never execute."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('retention', ROOT / 'scripts/retain-compiler-preparation.py')
RETENTION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RETENTION)


class RetainedPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        (self.path / 'P').mkdir()
        (self.path / 'unit-store').mkdir()
        files = {'manifest.term': b'inert manifest', 'beam_lisp.app': b'inert app', 'fixture.beam': b'inert unit'}
        for name, value in files.items():
            (self.path / 'P' / name).write_bytes(value)
        self.report = {'kind': 'artifact-generation-stage', 'native_execution_admission': False,
                       'generation': {'generation': 'P', 'produced': True, 'fresh_boot_qualified': True,
                         'files': {name: hashlib.sha256(value).hexdigest() for name, value in files.items()}}}
        self.write_report()
        (self.path / 'P.boot.log').write_text(json.dumps({'kind': 'fresh-source-floor', 'status': 'passed',
                                                       'seed': str(self.path / 'P')}) + '\n')

    def write_report(self):
        (self.path / 'result.json').write_text(json.dumps(self.report))

    def test_only_complete_freshly_booted_preparation_can_be_an_input_hint(self):
        self.assertEqual(self.path, RETENTION.validate_stage(self.path))
        self.report['generation']['fresh_boot_qualified'] = 'true'
        self.write_report()
        with self.assertRaisesRegex(ValueError, 'completed preparation'):
            RETENTION.validate_stage(self.path)

    def test_changed_bytes_or_a_foreign_boot_receipt_are_refused(self):
        (self.path / 'P/fixture.beam').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'bytes differ'):
            RETENTION.validate_stage(self.path)
        (self.path / 'P/fixture.beam').write_bytes(b'inert unit')
        (self.path / 'P.boot.log').write_text('{"kind":"fresh-source-floor","status":"passed","seed":"/foreign/P"}')
        with self.assertRaisesRegex(ValueError, 'receipt differs'):
            RETENTION.validate_stage(self.path)

    def test_log_discovery_does_not_follow_foreign_directories(self):
        with tempfile.TemporaryDirectory() as foreign:
            marker = b'COMPILER-PREPARATION-OUTPUT /nix/store/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-candidate\n'
            (Path(foreign) / 'worker.log').write_bytes(marker)
            (self.path / 'foreign').symlink_to(foreign, target_is_directory=True)
            self.assertEqual([], list(RETENTION.candidates(self.path)))
            (self.path / 'worker.log').write_bytes(marker)
            self.assertEqual([Path('/nix/store/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-candidate')],
                             list(RETENTION.candidates(self.path)))


if __name__ == '__main__':
    unittest.main()
