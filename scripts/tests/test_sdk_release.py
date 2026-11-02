import importlib.util
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('sdk_release', ROOT / 'scripts/sdk-release.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PortableSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.sdk, self.portable, self.platform, self.recipes = [self.root / n for n in ('sdk', 'portable', 'platform', 'recipes')]
        for path in (self.sdk, self.portable, self.platform, self.recipes):
            path.mkdir()
        self.selected = dict(version=1, kind='sdk', target='x86_64-linux', compiler='compiler', image='image', platform=str(self.platform))
        (self.portable / 'bl.drop').write_bytes(b'portable of the exact native image')
        self.descriptor = dict(version=1, kind='release', target='x86_64-linux', compiler='compiler', image='image', file='bl.drop',
                               sha256=hashlib.sha256((self.portable / 'bl.drop').read_bytes()).hexdigest())
        self.write()
        (self.platform / 'platform.json').write_text(json.dumps(dict(recipes=str(self.recipes))))
        self.addCleanup(patch.stopall)
        patch.object(MODULE, 'immutable', side_effect=Path).start()
        patch.dict(os.environ, {}, clear=True).start()

    def write(self):
        (self.sdk / 'artifact.json').write_text(json.dumps(self.selected))
        (self.portable / 'artifact.json').write_text(json.dumps(self.descriptor))

    def test_legacy_retained_release_requires_no_evaluation(self):
        self.selected['release'] = str(self.portable)
        self.write()
        with patch.object(MODULE.subprocess, 'check_output') as command:
            self.assertEqual(self.portable, MODULE.release(self.sdk))
            command.assert_not_called()

    def test_bounded_worker_uses_its_declared_input_without_a_daemon(self):
        with patch.dict(os.environ, CI_CHECK_RELEASE=str(self.portable)), patch.object(MODULE.subprocess, 'check_output') as command:
            self.assertEqual(self.portable, MODULE.release(self.sdk))
            command.assert_not_called()
            self.descriptor['image'] = 'different image'
            self.write()
            with self.assertRaisesRegex(ValueError, 'another native image'):
                MODULE.release(self.sdk)

    def test_host_lookup_evaluates_the_sdk_pinned_recipe_without_building(self):
        with patch.object(MODULE.subprocess, 'check_output', return_value=json.dumps(str(self.portable))) as command:
            self.assertEqual(self.portable, MODULE.release(self.sdk))
        argv = command.call_args.args[0]
        self.assertEqual('nix-instantiate', argv[0])
        self.assertIn(str(self.recipes / 'nix/portable-artifact.nix'), argv[argv.index('--expr') + 1])
        self.assertIn('false', argv)
        self.assertNotIn('build', argv)

    def test_changed_product_bytes_are_refused(self):
        with patch.dict(os.environ, CI_CHECK_RELEASE=str(self.portable)):
            (self.portable / 'bl.drop').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'bytes differ'):
                MODULE.release(self.sdk)


if __name__ == '__main__':
    unittest.main()
