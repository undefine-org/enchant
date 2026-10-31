import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('release_requirements', ROOT / 'scripts/release-requirements.py')
REQUIREMENTS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REQUIREMENTS)


class ReleaseRequirementsTests(unittest.TestCase):
    def test_receipt_rejects_changed_binary_and_wrong_release_commit(self):
        with tempfile.TemporaryDirectory() as temporary:
            candidate = Path(temporary) / 'bl'
            candidate.write_bytes(b'qualified immutable release')
            receipt = {'version': 1, 'kind': 'release-requirements', 'target': 'x86_64-linux',
                       'candidate_sha256': REQUIREMENTS.digest(candidate),
                       'revision': 'a' * 40, 'minimum_glibc': '2.44'}
            self.assertEqual(receipt, REQUIREMENTS.verify(candidate, receipt, 'a' * 40))
            with self.assertRaisesRegex(ValueError, 'revision differs'):
                REQUIREMENTS.verify(candidate, receipt, 'b' * 40)
            candidate.write_bytes(b'a replacement is not qualified')
            with self.assertRaisesRegex(ValueError, 'bytes differ'):
                REQUIREMENTS.verify(candidate, receipt)

    def test_absent_floor_and_unsupported_platform_cannot_be_published(self):
        with tempfile.TemporaryDirectory() as temporary:
            candidate = Path(temporary) / 'bl'
            candidate.write_bytes(b'release')
            receipt = {'version': 1, 'kind': 'release-requirements', 'target': 'x86_64-linux',
                       'candidate_sha256': REQUIREMENTS.digest(candidate),
                       'revision': 'a' * 40, 'minimum_glibc': '0.0'}
            with self.assertRaisesRegex(ValueError, 'no measured'):
                REQUIREMENTS.verify(candidate, receipt)
            receipt.update(target='aarch64-linux', minimum_glibc='2.44')
            with self.assertRaisesRegex(ValueError, 'Unsupported'):
                REQUIREMENTS.verify(candidate, receipt)


class GlibcMeasurementTests(unittest.TestCase):
    def measure(self, files, *, launcher=None, broken=False):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = root / 'payload with spaces'
            payload.mkdir()
            for name, versions in files.items():
                target = payload / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b'\x7fELF' + json.dumps(versions).encode())
            readelf = root / 'readelf'
            readelf.write_text('''#!/usr/bin/env python3
import json, pathlib, sys
if '--version' in sys.argv:
    print('GNU readelf test fixture')
    sys.exit(0)
if BROKEN:
    print('cannot inspect ELF', file=sys.stderr)
    sys.exit(2)
entry = json.loads(pathlib.Path(sys.argv[-1]).read_bytes()[4:])
print('Version definition section:')
print('  Name: GLIBC_99.0')
print('Version needs section:')
for version in entry:
    print('  Name: GLIBC_' + version)
'''.replace('BROKEN', repr(broken)))
            readelf.chmod(0o755)
            target = payload
            env = dict(os.environ, READELF=str(readelf))
            if launcher is not None:
                target = root / 'release.drop'
                target.write_bytes(b'\x7fELF' + json.dumps(launcher).encode())
                unpack = root / 'drop'
                unpack.write_text('''#!/usr/bin/env python3
import shutil, sys
shutil.copytree(SOURCE, sys.argv[sys.argv.index('--dir') + 1])
'''.replace('SOURCE', repr(str(payload))))
                unpack.chmod(0o755)
                env['DROP_BIN'] = str(unpack)
            return subprocess.run(['sh', str(ROOT / 'tooling/drop/glibc-floor.sh'), str(target)],
                                  env=env, text=True, capture_output=True)

    def test_requirements_only_and_spaced_names_are_measured(self):
        result = self.measure({'nested directory/beam.smp': ['2.2.5', '2.44'], 'nif.so': ['2.39']})
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('2.44  nested directory/beam.smp', result.stdout.strip())

    def test_outer_launcher_can_raise_payload_floor(self):
        result = self.measure({'beam.smp': ['2.39']}, launcher=['2.44'])
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('2.44  (launcher)', result.stdout.strip())

    def test_failed_elf_inspection_is_not_approved_as_zero(self):
        result = self.measure({'beam.smp': ['2.44']}, broken=True)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual('', result.stdout)


if __name__ == '__main__':
    unittest.main()
