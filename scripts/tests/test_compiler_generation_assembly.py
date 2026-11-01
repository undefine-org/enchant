import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('assembly', ROOT / 'scripts/assemble-compiler-generations.py')
ASSEMBLY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ASSEMBLY)


class CompilerGenerationAssemblyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.products = []
        for label in 'PBC':
            product = self.root / ('product-' + label)
            seed = product / label
            seed.mkdir(parents=True)
            (seed / 'manifest.term').write_text('inert metadata\n')
            (seed / 'fixture.beam').write_bytes(b'preparation' if label == 'P' else b'reproduction')
            (product / 'unit-store').mkdir()
            inputs = {'priv/boot/compiler.bl': 'a' * 64, 'priv/bootstrap/seed/fixture.beam': label * 64}
            (product / 'inputs.json').write_text(json.dumps(inputs))
            stage = {'generation': label, 'produced': True, 'fresh_boot_qualified': True,
                     'files': ASSEMBLY.inventory(seed)}
            report = {'kind': 'artifact-generation-stage', 'generation': stage,
                      'initial_seed': '/inert/seed', 'initial_seed_files': {'fixture.beam': 'a' * 64}}
            (product / 'result.json').write_text(json.dumps(report))
            for suffix in ('bootstrap.json', 'boot.log', 'producer.log'):
                (product / f'{label}.{suffix}').write_text('inert receipt\n')
            self.products.append(product)
        self.output = self.root / 'assembled'

    def test_assembly_retains_stage_provenance_and_does_no_compilation(self):
        ASSEMBLY.assemble(self.products, self.output)
        report = json.loads((self.output / 'qualification/result.json').read_text())
        self.assertEqual(dict(zip('PBC', map(str, self.products))), report['generation_products'])
        self.assertTrue(report['self_reproduction_qualified'])
        self.assertEqual(ASSEMBLY.inventory(self.products[2] / 'C'), ASSEMBLY.inventory(self.output / 'seed'))
        self.assertEqual((self.products[2] / 'unit-store').resolve(), (self.output / 'unit-store').resolve())
        for label, product in zip('PBC', self.products):
            self.assertEqual(product.resolve(), (self.output / 'generations' / label).resolve())

    def test_actual_stage_bytes_are_rechecked(self):
        (self.products[1] / 'B/fixture.beam').write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'Incomplete compiler generation B'):
            ASSEMBLY.assemble(self.products, self.output)

    def test_unequal_reproductions_are_not_published(self):
        product = self.products[2]
        (product / 'C/fixture.beam').write_bytes(b'different')
        report = json.loads((product / 'result.json').read_text())
        report['generation']['files'] = ASSEMBLY.inventory(product / 'C')
        (product / 'result.json').write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, 'B and C byte inventories differ'):
            ASSEMBLY.assemble(self.products, self.output)
        self.assertFalse((self.output / 'seed').exists())

    def test_equal_beams_from_different_sources_are_refused(self):
        path = self.products[2] / 'inputs.json'
        inputs = json.loads(path.read_text())
        inputs['priv/boot/compiler.bl'] = 'b' * 64
        path.write_text(json.dumps(inputs))
        with self.assertRaisesRegex(ValueError, 'source inputs changed'):
            ASSEMBLY.assemble(self.products, self.output)

    def test_a_missing_fresh_boot_is_not_excused_by_equal_output(self):
        path = self.products[2] / 'result.json'
        report = json.loads(path.read_text())
        report['generation']['fresh_boot_qualified'] = False
        path.write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, 'Incomplete compiler generation C'):
            ASSEMBLY.assemble(self.products, self.output)


if __name__ == '__main__':
    unittest.main()
