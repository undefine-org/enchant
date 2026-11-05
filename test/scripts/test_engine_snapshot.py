#!/usr/bin/env python3
"""Compare the actual native engine snapshot with the independent producer.

Runs in the bounded drop-tools derivation, before its launcher is admitted.
No BEAM, Nix daemon, external services, or timing thresholds are needed.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest


parser = argparse.ArgumentParser()
parser.add_argument('--launcher', required=True, type=Path)
parser.add_argument('--reference', required=True, type=Path)
parser.add_argument('--checkout', type=Path)
args = parser.parse_args()
launcher = args.launcher.resolve(strict=True)
fingerprint = runpy.run_path(str(args.reference))['fingerprint']


class NativeEngineSnapshot(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='engine-snapshot-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / 'nix').mkdir()
        (self.root / 'priv').mkdir()
        (self.root / 'native').mkdir()
        self.policy = dict(version=1, roots=['priv', 'nix', 'native'],
                           excluded=['priv/generated'], reserved=['.git', '__pycache__'],
                           targetRoots=['native'],
                           limits=dict(entries=200, fileBytes=65536, totalBytes=262144, depth=10))
        self.write_policy()
        (self.root / 'priv/value.bl').write_bytes(b'(ns value)\n')

    def write_policy(self):
        (self.root / 'nix/engine-inputs.json').write_text(json.dumps(self.policy))

    def agree(self, accepted=True):
        try:
            expected = fingerprint(self.root, self.policy)
        except (OSError, ValueError):
            expected = None
        native = subprocess.run([str(launcher), '--engine-inputs', str(self.root)],
                                text=True, capture_output=True, timeout=10)
        if accepted:
            self.assertIsNotNone(expected)
            self.assertEqual(0, native.returncode, native.stderr)
            self.assertEqual(expected + '\n', native.stdout)
        else:
            self.assertIsNone(expected)
            self.assertNotEqual(0, native.returncode)
        return expected

    def test_byte_changes_names_empty_directories_and_modes(self):
        first = self.agree()
        source = self.root / 'priv/value.bl'
        source.write_bytes(b'(ns value)\n(def value 42)\n')
        changed = self.agree()
        self.assertNotEqual(first, changed)
        source.chmod(0o755)
        executable = self.agree()
        self.assertNotEqual(changed, executable)
        source.chmod(0o744)
        self.assertEqual(executable, self.agree(), 'only owner execute enters NAR identity')
        source.rename(self.root / 'priv/renamed.bl')
        renamed = self.agree()
        self.assertNotEqual(executable, renamed)
        (self.root / 'priv/empty').mkdir()
        self.assertNotEqual(renamed, self.agree())

    def test_unicode_escaping_order_and_surrogateescaped_unix_names(self):
        for name in ['quote".bl', 'back\\slash.bl', 'line\nfeed.bl', '\x7f.bl',
                     'é.bl', 'Ā.bl', '𝄞.bl', '\udcff.bl', '\udc80.bl']:
            with self.subTest(name=ascii(name)):
                (self.root / 'priv' / name).write_bytes(b'input')
                self.agree()

    def test_exclusions_reserved_names_and_target_roots(self):
        before = self.agree()
        for name in ['priv/generated/output.beam', 'priv/__pycache__/cache.pyc',
                     '.git/index', 'native/crate/target/debug/native.so', 'research/note.bl']:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'ignored')
        # The selected native/crate directory is itself semantic.
        with_crate = self.agree()
        self.assertNotEqual(before, with_crate)
        for path in self.root.rglob('*'):
            if path.is_file() and path.name != 'engine-inputs.json' and path.name != 'value.bl':
                path.write_bytes(b'changed ignored bytes')
        self.assertEqual(with_crate, self.agree())
        (self.root / 'priv/target').mkdir()
        self.assertNotEqual(with_crate, self.agree(), 'target outside targetRoots stays semantic')

    def test_missing_root_and_selected_symlinks_and_special_files_refuse(self):
        self.policy['roots'].append('absent')
        self.write_policy()
        self.agree(False)
        self.policy['roots'].pop()
        self.write_policy()
        path = self.root / 'priv/link.bl'
        path.symlink_to('value.bl')
        self.agree(False)
        path.unlink()
        os.mkfifo(path)
        self.agree(False)

    def test_all_declared_limits_refuse_without_starting_a_runtime(self):
        base = copy.deepcopy(self.policy)
        (self.root / 'priv/deep/more').mkdir(parents=True)
        (self.root / 'priv/deep/more/value.bl').write_bytes(b'x' * 1024)
        for name, value in [('entries', 2), ('fileBytes', 512), ('totalBytes', 512), ('depth', 1)]:
            with self.subTest(limit=name):
                self.policy = copy.deepcopy(base)
                self.policy['limits'][name] = value
                self.write_policy()
                self.agree(False)
        self.policy = base
        self.write_policy()
        self.agree()

    def test_policy_shape_and_relative_paths(self):
        base = copy.deepcopy(self.policy)
        for field, value in [('version', 2), ('roots', []), ('roots', ['/priv']),
                             ('roots', ['priv/../nix']), ('excluded', []),
                             ('reserved', ['a/b']), ('targetRoots', []), ('unexpected', True)]:
            with self.subTest(field=field, value=value):
                self.policy = copy.deepcopy(base)
                self.policy[field] = value
                self.write_policy()
                self.agree(False)

    @unittest.skipUnless(args.checkout, 'full checkout comparison requested separately')
    def test_full_checkout(self):
        self.root = args.checkout.resolve(strict=True)
        self.policy = json.loads((self.root / 'nix/engine-inputs.json').read_text())
        self.agree()


if __name__ == '__main__':
    unittest.main(argv=[__file__])
