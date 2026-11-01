"""Run the device installer on disposable files, including legacy user data."""
import hashlib
import io
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'priv/android/install-runtime.sh'
RECEIPT = '.bl-runtime-files'


def inventory(files):
    return ''.join(hashlib.sha256(data).hexdigest() + '  ' + name + '\n'
                   for name, data in sorted(files.items())).encode()


class RuntimeInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.files = self.root / 'files'
        self.otp = self.files / 'otp'
        self.otp.mkdir(parents=True)
        self.archive = self.root / 'runtime.tar'

    def write(self, name, data):
        destination = self.otp / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)

    def pack(self, files, *, receipt=None, extra=None):
        payload = {'otp/' + name: data for name, data in files.items()}
        payload['otp/' + RECEIPT] = inventory(files) if receipt is None else receipt
        if extra:
            payload.update(extra)
        with tarfile.open(self.archive, 'w') as tar:
            for name, data in payload.items():
                entry = tarfile.TarInfo(name)
                entry.mode = 0o644
                entry.size = len(data)
                tar.addfile(entry, io.BytesIO(data))

    def install(self):
        return subprocess.run(['sh', str(SCRIPT), str(self.archive), str(self.files)],
                              capture_output=True, text=True)

    def test_prunes_only_unchanged_owned_files_and_preserves_live_user_data(self):
        old = {'lib/obsolete.beam': b'old code', 'changed.beam': b'original',
               'lib/current.beam': b'previous'}
        for name, data in old.items():
            self.write(name, data)
        self.write(RECEIPT, inventory(old))
        self.write('changed.beam', b'user changed this file')
        self.write('business/store', b'live database')
        self.write('lib/other-data', b'also live')
        self.pack({'lib/current.beam': b'new', 'new.beam': b'next'})
        result = self.install()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse((self.otp / 'lib/obsolete.beam').exists())
        self.assertEqual(b'user changed this file', (self.otp / 'changed.beam').read_bytes())
        self.assertEqual(b'live database', (self.otp / 'business/store').read_bytes())
        self.assertEqual(b'also live', (self.otp / 'lib/other-data').read_bytes())
        self.assertEqual(b'new', (self.otp / 'lib/current.beam').read_bytes())

    def test_legacy_and_modified_conflicts_are_backed_up_before_replacement(self):
        self.write('runtime.beam', b'legacy runtime or data')
        self.write('business/store', b'keep in place')
        self.pack({'runtime.beam': b'new runtime'})
        result = self.install()
        self.assertEqual(0, result.returncode, result.stderr)
        backups = list(self.files.glob('.bl-runtime-preserved.*/runtime.beam'))
        self.assertEqual([b'legacy runtime or data'], [path.read_bytes() for path in backups])
        self.assertEqual(b'keep in place', (self.otp / 'business/store').read_bytes())
        self.write('runtime.beam', b'edited runtime')
        self.pack({'runtime.beam': b'newer runtime'})
        result = self.install()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(b'edited runtime', [path.read_bytes() for path in
                      self.files.glob('.bl-runtime-preserved.*/runtime.beam')])

    def test_unchanged_install_preserves_mtime_and_creates_no_backup(self):
        self.pack({'same.beam': b'same'})
        self.assertEqual(0, self.install().returncode)
        file = self.otp / 'same.beam'
        before = file.stat().st_mtime_ns
        self.assertEqual(0, self.install().returncode)
        self.assertEqual(before, file.stat().st_mtime_ns)
        self.assertFalse(list(self.files.glob('.bl-runtime-preserved.*')))

    def test_changed_owned_path_replaced_without_deleting_new_member(self):
        self.write('same.beam', b'one')
        self.write(RECEIPT, inventory({'same.beam': b'one'}))
        self.pack({'same.beam': b'two'})
        result = self.install()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(b'two', (self.otp / 'same.beam').read_bytes())

    def test_changed_payload_or_unlisted_member_refuses_before_writes(self):
        self.write('first.beam', b'original')
        self.pack({'first.beam': b'next'}, receipt=inventory({'first.beam': b'wrong'}))
        self.assertNotEqual(0, self.install().returncode)
        self.assertEqual(b'original', (self.otp / 'first.beam').read_bytes())
        self.pack({'first.beam': b'next'}, extra={'otp/unlisted': b'extra'})
        self.assertNotEqual(0, self.install().returncode)
        self.assertEqual(b'original', (self.otp / 'first.beam').read_bytes())

    def test_traversal_and_archive_symlinks_refuse_before_extraction(self):
        self.pack({'okay': b'next'}, extra={'../escaped': b'escape'})
        self.assertNotEqual(0, self.install().returncode)
        self.assertFalse((self.files / 'escaped').exists())
        self.assertFalse((self.root / 'escaped').exists())
        self.pack({'okay': b'next'})
        with tarfile.open(self.archive, 'a') as tar:
            entry = tarfile.TarInfo('otp/link')
            entry.type = tarfile.SYMTYPE
            entry.linkname = str(self.root / 'outside')
            tar.addfile(entry)
        self.assertNotEqual(0, self.install().returncode)
        self.assertFalse((self.otp / 'okay').exists())

    def test_destination_symlinks_and_directories_refuse_without_data_changes(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / 'data').write_bytes(b'private data')
        (self.otp / 'linked').symlink_to(outside, target_is_directory=True)
        self.pack({'linked/data': b'new'})
        self.assertNotEqual(0, self.install().returncode)
        self.assertEqual(b'private data', (outside / 'data').read_bytes())
        self.pack({'linked': b'new file'})
        self.assertNotEqual(0, self.install().returncode)
        (self.otp / 'directory').mkdir()
        (self.otp / 'directory/data').write_bytes(b'keep')
        self.pack({'directory': b'new file'})
        self.assertNotEqual(0, self.install().returncode)
        self.assertEqual(b'keep', (self.otp / 'directory/data').read_bytes())

    def test_existing_install_lock_is_never_stolen_or_deleted(self):
        lock = self.files / '.bl-runtime-install.lock'
        lock.mkdir()
        (lock / 'owner-data').write_bytes(b'active or operator-owned')
        self.pack({'next.beam': b'next'})
        self.assertNotEqual(0, self.install().returncode)
        self.assertEqual(b'active or operator-owned', (lock / 'owner-data').read_bytes())
        self.assertFalse((self.otp / 'next.beam').exists())

    def test_obsolete_launcher_links_are_preserved_and_drop_old_ownership(self):
        helpers = ['erts-17.0/bin/' + name for name in
                   ['erl_child_setup', 'inet_gethost', 'epmd']]
        helpers += ['lib/exqlite-0.37.0/priv/sqlite3_nif.so']
        old = {name: b'old runtime binary' for name in helpers}
        self.write(RECEIPT, inventory(old))
        targets = self.root / 'native-libraries'
        targets.mkdir()
        for i, name in enumerate(helpers):
            target = targets / str(i)
            target.write_bytes(b'actual APK native library')
            link = self.otp / name
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(target)
        self.write('proof-data/token', b'keep inside runtime')
        self.pack({'app/new.beam': b'new code'})
        result = self.install()
        self.assertEqual(0, result.returncode, result.stderr)
        for name in helpers:
            self.assertTrue((self.otp / name).is_symlink())
            self.assertNotIn(name.encode(), (self.otp / RECEIPT).read_bytes())
        self.assertEqual(b'keep inside runtime', (self.otp / 'proof-data/token').read_bytes())

    def test_obsolete_member_under_changed_parent_is_not_followed(self):
        self.write(RECEIPT, inventory({'replaced/old.beam': b'same bytes'}))
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / 'old.beam').write_bytes(b'same bytes')
        (self.otp / 'replaced').symlink_to(outside, target_is_directory=True)
        self.pack({'app/new.beam': b'new code'})
        result = self.install()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(b'same bytes', (outside / 'old.beam').read_bytes())
        self.assertTrue((self.otp / 'replaced').is_symlink())
        self.assertNotIn(b'replaced/old.beam', (self.otp / RECEIPT).read_bytes())


if __name__ == '__main__':
    unittest.main()
