import contextlib
import fcntl
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('materializer', ROOT / 'scripts/ci-materialize-candidate.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MaterializationTests(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root, sdk, payload, executor, platform = [base / name for name in
                                                       ('checkout', 'sdk', 'payload', 'executor', 'platform')]
            root.mkdir()
            app = payload / 'lib/beam_lisp-0.1.0'
            files = {'ebin/runtime.beam': b'qualified compiled module',
                     'priv/bootstrap/seed/manifest.term': b'sealed manifest',
                     'priv/precompiled.term': b'sealed precompiled',
                     'priv/sdk-code.term': b'sealed inventory',
                     'priv/native/lazy_memo.so': b'portable native ELF',
                     'priv/native/datom_fjall.so': b'portable datom ELF',
                     'priv/z3/bin/z3': b'portable solver ELF',
                     'priv/z3/LICENSE.txt': b'solver license'}
            for name, data in files.items():
                path = app / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                if path.suffix == '.so' or path.name == 'z3':
                    path.chmod(0o755)
            shutil.copytree(app, sdk / 'image')
            (sdk / 'image/priv/native/lazy_memo.so').write_bytes(b'Nix-linked native ELF')
            (sdk / 'image/priv/z3/bin/z3').write_bytes(b'Nix-linked solver ELF')
            (sdk / 'artifact.json').write_text('{}')
            (executor / 'bin').mkdir(parents=True)
            (executor / 'bin/drop-launcher').write_bytes(b'authenticated stock launcher')
            (executor / 'bin/drop-launcher').chmod(0o755)
            (platform / 'native-products').mkdir(parents=True)
            candidate = base / 'candidate'
            candidate.write_bytes(b'authenticated exact drop')
            selected = (sdk, {}, platform, {'executor': str(executor)}, base / 'coordinator', MODULE.digest(candidate))

            def unpack(command, **kwargs):
                self.assertEqual([str(executor / 'bin/drop'), 'unpack', str(candidate), '--dir'], command[:4])
                shutil.copytree(payload, command[4])

            with patch.object(MODULE, 'selection', return_value=selected), \
                    patch.object(MODULE, 'immutable', side_effect=Path), \
                    patch.object(MODULE.subprocess, 'run', side_effect=unpack):
                yield root, candidate, sdk, app

    def test_normal_startup_sdk_natives_and_solver_are_retained_verbatim(self):
        with self.fixture() as (root, candidate, sdk, app):
            native = root / 'priv/native'
            native.mkdir(parents=True)
            original = native / 'lazy_memo.so'
            original.symlink_to(sdk / 'image/priv/native/lazy_memo.so')
            anchor = native / '.bl/artifact-custody/.bl/locks/lazy_memo.so'
            anchor.parent.mkdir(parents=True)
            anchor.touch()
            before = original.lstat().st_ino, anchor.stat().st_ino, MODULE.digest(candidate)
            shutil.copytree(sdk / 'image/priv/z3', root / 'priv/z3')
            MODULE.materialize(root, candidate, sdk)
            self.assertEqual(before, (original.lstat().st_ino, anchor.stat().st_ino, MODULE.digest(candidate)))
            self.assertEqual(b'Nix-linked native ELF', original.read_bytes())
            self.assertEqual(b'Nix-linked solver ELF', (root / 'priv/z3/bin/z3').read_bytes())
            self.assertEqual(b'portable datom ELF', (native / 'datom_fjall.so').read_bytes())
            self.assertEqual(app.joinpath('priv/sdk-code.term').read_bytes(),
                             (root / '.bl/ci-image/priv/sdk-code.term').read_bytes())

    def test_completed_projection_is_idempotent(self):
        with self.fixture() as (root, candidate, sdk, _):
            receipt = MODULE.materialize(root, candidate, sdk)
            record = root / '.bl/ci-sdk.json'
            before = record.stat().st_ino, record.stat().st_mtime_ns, MODULE.tree_identity(root / '.bl/ci-runtime')
            self.assertEqual(receipt, MODULE.materialize(root, candidate, sdk))
            self.assertEqual(before, (record.stat().st_ino, record.stat().st_mtime_ns,
                                      MODULE.tree_identity(root / '.bl/ci-runtime')))

    def test_foreign_native_and_solver_files_refuse_without_replacement(self):
        for relative in ('priv/native/lazy_memo.so', 'priv/z3/bin/z3'):
            with self.subTest(relative=relative), self.fixture() as (root, candidate, sdk, _):
                path = root / relative
                path.parent.mkdir(parents=True)
                path.write_bytes(b'foreign modified runtime')
                before = path.stat().st_ino, path.read_bytes(), MODULE.digest(candidate)
                with self.assertRaisesRegex(ValueError, 'Modified or foreign runtime fixture'):
                    MODULE.materialize(root, candidate, sdk)
                self.assertEqual(before, (path.stat().st_ino, path.read_bytes(), MODULE.digest(candidate)))
                self.assertFalse((root / '.bl/ci-runtime').exists())
                self.assertFalse((root / '.bl/ci-sdk.json').exists())

    def test_modified_extracted_file_is_not_hidden_by_a_valid_receipt(self):
        with self.fixture() as (root, candidate, sdk, _):
            MODULE.materialize(root, candidate, sdk)
            path = root / '.bl/ci-image/ebin/runtime.beam'
            path.write_bytes(b'modified executable bytes')
            before = (root / '.bl/ci-sdk.json').read_bytes(), MODULE.digest(candidate)
            with self.assertRaisesRegex(ValueError, 'extracted candidate files were modified'):
                MODULE.materialize(root, candidate, sdk)
            self.assertEqual(b'modified executable bytes', path.read_bytes())
            self.assertEqual(before, ((root / '.bl/ci-sdk.json').read_bytes(), MODULE.digest(candidate)))

    def test_active_native_custody_and_mutable_aliases_remain_refused(self):
        with self.fixture() as (root, candidate, sdk, _):
            anchor = root / 'priv/native/.bl/artifact-custody/.bl/locks/lazy_memo.so'
            anchor.parent.mkdir(parents=True)
            with anchor.open('w') as owner:
                fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaises(BlockingIOError):
                    MODULE.materialize(root, candidate, sdk)
                self.assertFalse((root / '.bl/ci-runtime').exists())
            foreign = root / 'mutable-library.so'
            foreign.write_bytes((sdk / 'image/priv/native/lazy_memo.so').read_bytes())
            foreign.chmod(0o755)
            (root / 'priv/native/lazy_memo.so').symlink_to(foreign)
            with self.assertRaisesRegex(ValueError, 'Modified or foreign runtime fixture'):
                MODULE.materialize(root, candidate, sdk)


if __name__ == '__main__':
    unittest.main()
