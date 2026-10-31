import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('ci_model_input', ROOT / 'scripts/ci-model-input.py')
MODEL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODEL)


class PinnedModelInputTests(unittest.TestCase):
    def test_actual_declared_pin_inventory_has_one_model_and_three_files(self):
        name, pins, identity = MODEL.pins()
        self.assertEqual('potion-code-16M-v2', name)
        self.assertEqual({'config.json', 'model.safetensors', 'tokenizer.json'}, set(pins))
        self.assertEqual(64, len(identity))
        # A malformed Source pin must not silently disappear from a regex match.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / 'priv/build/embed-asset.bl'
            path.parent.mkdir(parents=True)
            source = (ROOT / 'priv/build/embed-asset.bl').read_text()
            path.write_text(source.replace(pins['config.json'], 'a' * 63))
            with self.assertRaisesRegex(ValueError, 'inventory'):
                MODEL.pins(root)

    def test_all_pinned_files_and_completion_digest_are_required_before_capture(self):
        with tempfile.TemporaryDirectory() as temporary:
            models = Path(temporary)
            directory = models / 'small-fixture'
            directory.mkdir()
            pins = {name: hashlib.sha256(name.encode()).hexdigest()
                    for name in ('config.json', 'model.safetensors', 'tokenizer.json')}
            for name in pins:
                (directory / name).write_text(name)
            (directory / 'DIGEST').write_text(pins['model.safetensors'])
            with patch.object(MODEL, 'pins', return_value=('small-fixture', pins, 'a' * 64)):
                self.assertEqual('a' * 64, MODEL.verify(models))
                for name in (*pins, 'DIGEST'):
                    with self.subTest(name=name):
                        original = (directory / name).read_bytes()
                        (directory / name).write_bytes(b'corrupt download')
                        with self.assertRaisesRegex(ValueError, 'pin mismatch|DIGEST differs'):
                            MODEL.verify(models)
                        (directory / name).write_bytes(original)
                (directory / 'config.json').unlink()
                with self.assertRaises(FileNotFoundError):
                    MODEL.verify(models)
