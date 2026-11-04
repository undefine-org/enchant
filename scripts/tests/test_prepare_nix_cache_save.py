"""Cache permission repair leaves payloads, lock ownership and links intact."""
import fcntl
import importlib.util
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('cache_save', Path(__file__).resolve().parents[1] / 'prepare-nix-cache-save.py')
CACHE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CACHE)


class CacheSaveTest(unittest.TestCase):
    def test_permission_repair_does_not_release_another_process_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / ('d' * 32 + '-active.lock')
            lock.touch(mode=0o600)
            code = 'import fcntl,sys; f=open(sys.argv[1],"r"); fcntl.flock(f,fcntl.LOCK_EX); print("ready",flush=True); sys.stdin.read()'
            child = subprocess.Popen([sys.executable, '-c', code, str(lock)], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
            try:
                self.assertEqual(b'ready\n', child.stdout.readline())
                self.assertEqual(1, CACHE.prepare(Path(directory)))
                with lock.open('r') as contender:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                child.stdin.close()
                child.wait(timeout=5)
                child.stdout.close()

    def test_active_lock_remains_the_same_file_with_the_same_bytes_and_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory)
            lock = store / ('a' * 32 + '-native.lock')
            lock.write_bytes(b'lock state')
            lock.chmod(0o600)
            before = lock.stat()
            self.assertEqual(1, CACHE.prepare(store))
            after = lock.stat()
            self.assertEqual((before.st_ino, before.st_uid, before.st_gid), (after.st_ino, after.st_uid, after.st_gid))
            self.assertEqual(b'lock state', lock.read_bytes())
            self.assertEqual(0o644, stat.S_IMODE(after.st_mode))
            self.assertEqual(0, CACHE.prepare(store))

    def test_payloads_and_symlink_targets_are_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory)
            payload = store / ('b' * 32 + '-payload')
            payload.write_bytes(b'payload')
            payload.chmod(0o400)
            link = store / ('c' * 32 + '-linked.lock')
            link.symlink_to(payload)
            before = payload.stat()
            self.assertEqual(0, CACHE.prepare(store))
            self.assertEqual(before.st_mode, payload.stat().st_mode)
            self.assertEqual(b'payload', payload.read_bytes())
            self.assertTrue(link.is_symlink())
