import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('produced_compiler', ROOT / 'scripts/check-produced-compiler.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ProducedCompilerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.compiler, self.floor = self.root / 'compiler', self.root / 'image/priv/bootstrap/seed'
        self.qualification = self.compiler / 'qualification'
        self.qualification.mkdir(parents=True)
        self.floor.mkdir(parents=True)
        seed = self.compiler / 'seed'
        seed.mkdir()
        files = {'manifest.term': b'#{<<"build_key">> => <<"' + b'1' * 64
                 + b'">>, <<"compiler_key">> => <<"' + b'2' * 64 + b'">>}.\n',
                 'beam_lisp.app': b'qualified app', 'Elixir.BeamLisp.Compiler.beam': b'qualified compiler'}
        for name, data in files.items():
            (seed / name).write_bytes(data)
            (self.floor / name).write_bytes(data)
        inventory = MODULE.actual_inventory(seed)
        inputs = {name: '3' * 64 for name in (
            'env.bl', 'scripts/check-source-floor', 'scripts/qualify-artifact-generation',
            'scripts/demo-artifact-production', 'test/scripts/artifact-generation.bl')}
        inputs.update({'priv/bootstrap/seed/' + name: sha for name, sha in inventory.items()})
        self.write('inputs.json', inputs)
        generations = []
        previous = '/build/source/priv/bootstrap/seed'
        for label in 'PBC':
            bootstrap = {'installation': 'current', 'stable_predecessor_unchanged': True,
                         'input_build_key': '1' * 64, 'seed_build_key': '1' * 64,
                         'input_compiler_key': '2' * 64, 'seed_compiler_key': '2' * 64}
            generations.append({'generation': label, 'producer_floor': previous,
                                'produced': True, 'fresh_boot_qualified': True,
                                'bootstrap': bootstrap, 'files': dict(inventory)})
            self.write(f'{label}.bootstrap.json', bootstrap)
            previous = '/build/reproduction/' + label
            (self.qualification / f'{label}.producer.log').write_text(
                'ARTIFACT-GENERATION {:modules 1, :milliseconds 10, :units 1, :producer-unchanged true}\n')
            (self.qualification / f'{label}.boot.log').write_text(
                'preboot diagnostics\n' + json.dumps({'kind': 'fresh-source-floor', 'status': 'passed',
                'seed': previous, 'runtime': 'erts17.0.1-elixir1.20.4', 'tests': []}) + '\n')
        self.report = {'version': 1, 'kind': 'artifact-generation-qualification',
                       'initial_seed': '/build/source/priv/bootstrap/seed',
                       'initial_seed_files': dict(inventory), 'floor_installed': False,
                       'native_execution_admission': False, 'self_reproduction_qualified': True,
                       'changed_files': [], 'preparation': generations[0], 'stages': generations[1:]}
        self.write('result.json', self.report)

    def write(self, name, value):
        (self.qualification / name).write_text(json.dumps(value) + '\n')

    def verify(self):
        return MODULE.verify_proof(self.compiler, self.floor)

    def reject_report(self, message):
        self.write('result.json', self.report)
        with self.assertRaisesRegex(ValueError, message):
            self.verify()

    def test_complete_qualified_seed_is_verified_without_a_runtime(self):
        receipt = self.verify()
        self.assertEqual(('passed', 3, ['P', 'B', 'C']),
                         tuple(receipt[key] for key in ('status', 'files', 'generations')))

    def test_truthy_and_false_success_markers_are_refused(self):
        for marker in (False, 'true', 1):
            with self.subTest(marker=marker):
                self.report['self_reproduction_qualified'] = marker
                self.reject_report('self-reproduction')

    def test_preparation_boot_and_trust_boundaries_are_required(self):
        for key, value in (('produced', False), ('fresh_boot_qualified', 'true')):
            with self.subTest(key=key):
                self.report['preparation'][key] = value
                self.reject_report('Generation P')
                self.report['preparation'][key] = True
        self.report['native_execution_admission'] = True
        self.reject_report('trust boundaries')

    def test_byte_equality_is_recomputed_despite_a_successful_report(self):
        self.report['stages'][0]['files']['Elixir.BeamLisp.Compiler.beam'] = 'f' * 64
        self.reject_report('B and C byte inventories differ')

    def test_consistently_forged_digest_reports_do_not_match_installed_bytes(self):
        for stage in self.report['stages']:
            stage['files']['Elixir.BeamLisp.Compiler.beam'] = 'f' * 64
        self.reject_report('Installed compiler seed')

    def test_changed_missing_extra_and_linked_seed_files_are_refused(self):
        path = self.compiler / 'seed/Elixir.BeamLisp.Compiler.beam'
        original = path.read_bytes()
        path.write_bytes(b'changed installed compiler')
        with self.assertRaisesRegex(ValueError, 'Installed compiler seed'):
            self.verify()
        path.unlink()
        with self.assertRaisesRegex(ValueError, 'Installed compiler seed'):
            self.verify()
        path.symlink_to(self.floor / path.name)
        with self.assertRaisesRegex(ValueError, 'regular file'):
            self.verify()
        path.unlink()
        path.write_bytes(original)
        (path.parent / 'extra.beam').write_bytes(b'undeclared')
        with self.assertRaisesRegex(ValueError, 'Installed compiler seed'):
            self.verify()

    def test_image_floor_must_match_the_selected_compiler(self):
        (self.floor / 'Elixir.BeamLisp.Compiler.beam').write_bytes(b'foreign image compiler')
        with self.assertRaisesRegex(ValueError, 'SDK image floor'):
            self.verify()

    def test_bootstrap_and_boot_receipts_must_be_successful_and_bound(self):
        bootstrap = dict(self.report['stages'][1]['bootstrap'], stable_predecessor_unchanged=False)
        self.write('C.bootstrap.json', bootstrap)
        with self.assertRaisesRegex(ValueError, 'bootstrap trust'):
            self.verify()
        self.report['stages'][1]['bootstrap']['stable_predecessor_unchanged'] = False
        self.reject_report('bootstrap trust')
        self.report['stages'][1]['bootstrap']['stable_predecessor_unchanged'] = True
        self.write('result.json', self.report)
        self.write('C.bootstrap.json', self.report['stages'][1]['bootstrap'])
        self.write('C.boot.log', {'kind': 'fresh-source-floor', 'status': 'failed',
                                'seed': '/build/reproduction/C', 'runtime': 'erts17', 'tests': []})
        with self.assertRaisesRegex(ValueError, 'fresh-boot receipt'):
            self.verify()

    def test_stale_predecessor_chain_and_inputs_are_refused(self):
        self.report['stages'][1]['producer_floor'] = '/other/reproduction/B'
        self.reject_report('predecessor chain')
        self.report['stages'][1]['producer_floor'] = '/build/reproduction/B'
        self.report['initial_seed_files']['manifest.term'] = 'f' * 64
        self.reject_report('recorded producer inputs')

    def test_mutable_report_cannot_be_admitted_as_a_selected_sdk(self):
        with self.assertRaisesRegex(ValueError, 'immutable top-level Nix store'):
            MODULE.check_sdk(self.root)


if __name__ == '__main__':
    unittest.main()
