import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('ci_model_input', ROOT / 'scripts/ci-model-input.py')
MODEL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODEL)


class PinnedModelInputTests(unittest.TestCase):
    def provision_fixture(self, mode):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        sdk, models, cache = root / 'selected-sdk', root / 'explicit-models', root / 'cache'
        (sdk / 'bin').mkdir(parents=True)
        launcher = sdk / 'bin/bl'
        launcher.write_text('#!' + sys.executable + '\n' + '''
import json, os, pathlib, sys
root = pathlib.Path(os.environ['FAKE_INSTALL_RECEIPT'])
root.write_text(json.dumps({'argv':sys.argv[1:], 'daemon':os.environ.get('BL_DAEMON'),
                           'models':os.environ.get('BEAM_LISP_MODEL_DIR')}))
mode = os.environ['FAKE_INSTALL_MODE']
if mode == 'failure': sys.exit(7)
if mode == 'false-zero':
    print('double free or corruption (out)', file=sys.stderr); sys.exit(0)
directory = pathlib.Path(os.environ['BEAM_LISP_MODEL_DIR']) / 'small-fixture'
directory.mkdir(parents=True)
for name in ('config.json','model.safetensors','tokenizer.json'):
    (directory / name).write_text(name)
(directory / 'DIGEST').write_text(__import__('hashlib').sha256(b'model.safetensors').hexdigest())
(directory / 'PROVENANCE').write_text('verified fixture download')
''')
        launcher.chmod(0o755)
        files = {name: hashlib.sha256(name.encode()).hexdigest()
                 for name in ('config.json', 'model.safetensors', 'tokenizer.json')}
        pins = ('small-fixture', files, 'b' * 64)
        receipt = root / 'invocation.json'
        self.addCleanup(patch.stopall)
        patch.object(MODEL, 'selected_sdk', return_value=sdk).start()
        patch.object(MODEL, 'pins', return_value=pins).start()
        patch.dict(os.environ, FAKE_INSTALL_MODE=mode, FAKE_INSTALL_RECEIPT=str(receipt),
                   BL_DAEMON='on', BEAM_LISP_MODEL_DIR='/foreign-models').start()
        return sdk, models, cache, receipt

    def test_provision_uses_exact_sdk_cold_then_verifies_before_publishing(self):
        sdk, models, cache, receipt = self.provision_fixture('success')
        record = {'version': 1, 'kind': 'ci-model-input',
                  'path': '/nix/store/' + 'a' * 32 + '-models', 'pins_sha256': 'b' * 64}
        cache.mkdir()
        with patch.object(MODEL, 'restore', return_value=None), \
                patch.object(MODEL, 'register', return_value=record), \
                patch.object(MODEL.subprocess, 'check_output', return_value=record['path'] + '\n'):
            self.assertEqual(record, MODEL.provision(sdk, models, cache))
        self.assertEqual({'argv': ['--cold', 'install', 'embed'], 'daemon': 'off', 'models': str(models)},
                         json.loads(receipt.read_text()))
        self.assertEqual(record, json.loads((cache / 'models.json').read_text()))

    def test_false_zero_without_model_files_cannot_publish_a_ready_hint(self):
        sdk, models, cache, _ = self.provision_fixture('false-zero')
        with patch.object(MODEL, 'restore') as restore, \
                patch.object(MODEL, 'register') as register:
            with self.assertRaises(FileNotFoundError):
                MODEL.provision(sdk, models, cache)
            restore.assert_not_called()
            register.assert_not_called()
        self.assertFalse((cache / 'models.json').exists())

    def test_nonzero_provisioning_is_not_captured(self):
        sdk, models, cache, _ = self.provision_fixture('failure')
        with patch.object(MODEL, 'capture') as capture:
            with self.assertRaises(subprocess.CalledProcessError) as error:
                MODEL.provision(sdk, models, cache)
            self.assertEqual(7, error.exception.returncode)
            capture.assert_not_called()

    def test_capture_reuses_verified_immutable_models_without_a_second_store_copy(self):
        retained = {'version': 1, 'kind': 'ci-model-input',
                    'path': '/nix/store/' + 'a' * 32 + '-models', 'pins_sha256': 'b' * 64}
        models, cache = Path('/explicit/downloaded/models'), Path('/private/ci-cache')
        with patch.object(MODEL, 'verify') as verify, \
                patch.object(MODEL, 'restore', return_value=retained), \
                patch.object(MODEL.subprocess, 'check_output') as add:
            self.assertEqual(retained, MODEL.capture(models, cache))
            verify.assert_called_once_with(models)
            add.assert_not_called()

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
