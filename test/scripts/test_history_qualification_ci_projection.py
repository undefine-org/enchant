"""Cause controls for the actual one-producer CI projection; no BEAM starts."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
OBSERVATIONS = []


def source_probe(relative, before=None, after=None):
    path = ROOT / relative
    source = path.read_text()
    original = hashlib.sha256(source.encode()).hexdigest()
    if before is not None:
        if source.count(before) != 1:
            raise ValueError('Ambiguous actual Source mutation')
        source = source.replace(before, after)
    namespace = {'__file__': str(path), '__name__': 'qualification_ci_private_probe'}
    exec(compile(source, str(path), 'exec'), namespace)
    return namespace, original


class QualificationCIProjection(unittest.TestCase):
    def test_E84_real_candidate_projection_and_launcher_digest_control(self):
        sdk = os.environ.get('BL_HISTORY_SDK') or os.environ.get('BL_SDK_PRODUCT')
        if not sdk:
            self.skipTest('Requires an explicitly selected existing immutable SDK, never prepares one')
        sdk = Path(sdk).resolve(strict=True)
        metadata = json.loads((sdk / 'artifact.json').read_text())
        candidate = Path(metadata['release']) / 'bl.drop'
        current, source_hash = source_probe('scripts/ci-materialize-candidate.py')
        before = 'digest(release / \'bl.drop\') != expected or digest(candidate) != expected'
        mutant, _ = source_probe('scripts/ci-materialize-candidate.py', before,
                                 "digest(release / 'bl.drop') != expected")
        with tempfile.TemporaryDirectory(prefix='qualification-ci-projection-') as temporary:
            base = Path(temporary)
            normal = base / 'normal'; normal.mkdir()
            receipt = current['materialize'](normal, candidate, sdk)
            app = normal / '.bl/ci-image'
            self.assertEqual(receipt['candidate_sha256'], current['digest'](candidate))
            for name in receipt['metadata_sha256']:
                self.assertEqual((sdk / 'image' / name).read_bytes(), (app / name).read_bytes())
            self.assertTrue((normal / 'build/Elixir.BeamLisp.Launcher.beam').is_file())
            self.assertTrue((normal / '.bl/lib').is_dir())
            self.assertFalse((base / 'bl-selfbuild/tree').exists(), 'Historical assembler scratch is absent')
            # Change only a launcher header byte. The payload/trailer remain
            # valid, so the stock unpacker alone cannot authenticate this file.
            changed = base / 'changed-candidate'
            shutil.copyfile(candidate, changed)
            with changed.open('r+b') as stream:
                original = stream.read(1); stream.seek(0); stream.write(bytes([original[0] ^ 1]))
            refused = base / 'refused'; refused.mkdir()
            with self.assertRaisesRegex(ValueError, 'Candidate bytes differ'):
                current['materialize'](refused, changed, sdk)
            self.assertFalse((refused / '.bl/ci-runtime').exists())
            accepted = base / 'mutant'; accepted.mkdir()
            mutant['materialize'](accepted, changed, sdk)
            self.assertTrue((accepted / '.bl/ci-image/priv/sdk-code.term').is_file())
        OBSERVATIONS.append({'case': 'E84', 'producer': 'scripts/ci-materialize-candidate.py',
            'producer_sha256': source_hash, 'candidate_sha256': current['digest'](candidate),
            'before': before, 'after': "digest(release / 'bl.drop') != expected",
            'actual_portable_projection': True, 'current_refuses_changed_launcher': True,
            'mutant_accepts_changed_launcher': True, 'sdk_bytes_modified': False,
            'scope': 'Actual existing portable bytes and stock unpacker; no SDK or hosted-runner production'})

    def test_E83_actual_shard_context_refuses_disagreement_before_a_vm(self):
        sdk = os.environ.get('BL_HISTORY_SDK') or os.environ.get('BL_SDK_PRODUCT')
        if not sdk:
            self.skipTest('Requires an explicitly selected existing immutable SDK')
        current, source_hash = source_probe('scripts/ci-test-shard.py')
        context = current['verified_context']({'BL_SDK_PRODUCT': sdk})
        self.assertEqual(5, len(context))
        self.assertEqual({}, current['verified_context']({}))
        for name in ['BL_ARTIFACT_PLATFORM', 'BL_PREPARATION_COORDINATOR', 'BL_PREPARED_NATIVES', 'BL_TEST_CHECKOUT_PLATFORM']:
            with self.assertRaisesRegex(ValueError, 'disagrees'):
                current['verified_context']({**context, name: sdk})
        self.assertNotIn('BL_INTERNAL_PRODUCER', context)
        OBSERVATIONS.append({'case': 'E83', 'producer': 'scripts/ci-test-shard.py',
            'producer_sha256': source_hash, 'verified_context_keys': sorted(context),
            'four_disagreeing_inputs_refused': True, 'scope': 'Actual context reader; no closure distribution or native build'})


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(QualificationCIProjection))
    print('HISTORY_QUALIFICATION_CI_PROJECTION ' + json.dumps({'passed': result.wasSuccessful(),
          'tests_run': result.testsRun, 'skipped': len(result.skipped), 'observations': OBSERVATIONS}, sort_keys=True))
    raise SystemExit(not result.wasSuccessful())
