import os
from pathlib import Path
import re
import subprocess
import json
import stat
import sys
import tempfile
import unittest


class ExactCacheRestoreTests(unittest.TestCase):
    def ownership_step(self):
        source = (Path(__file__).resolve().parents[2] / '.github/actions/nix-sdk-cache/action.yml').read_text()
        restore = source.index('    - name: Restore registered Nix products')
        repair = source.index('    - name: Restore runner ownership of the Nix client cache')
        consumer = source.index('    - name: Require the exact producer cache')
        self.assertLess(restore, repair)
        self.assertLess(repair, consumer)
        block = source[repair:consumer]
        body = re.search(r'      run: \|\n((?:        .*\n)+)', block)[1]
        return '\n'.join(line[8:] for line in body.splitlines())

    def test_restored_client_cache_becomes_writable_without_touching_daemon_paths(self):
        if os.geteuid() == 0:
            self.skipTest('Permission refusal requires the unprivileged runner user')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / 'runner'
            cache = home / '.cache/nix'
            cache.mkdir(parents=True)
            cache.chmod(0o500)
            with self.assertRaises(PermissionError):
                (cache / 'fetcher-locks').mkdir()
            # Fake the privileged cache restore in a controlled fixture. sudo
            # executes real filesystem commands as this fixture's owner; the
            # captured chown arguments establish the production UID/GID target.
            cache.chmod(0o700)
            daemon = root / 'nix/store/db'
            daemon.mkdir(parents=True)
            sentinel = daemon / 'daemon-owned'
            sentinel.write_bytes(b'daemon database untouched')
            sentinel.chmod(0o400)
            before = (sentinel.stat().st_uid, sentinel.stat().st_gid, stat.S_IMODE(sentinel.stat().st_mode), sentinel.read_bytes())
            (cache / 'store-link').symlink_to(daemon, target_is_directory=True)
            cache.chmod(0o500)
            tools = root / 'tools'
            tools.mkdir()
            log = root / 'sudo.jsonl'
            sudo = tools / 'sudo'
            sudo.write_text('#!' + sys.executable + '\n'
                'import json,os,subprocess,sys\n'
                'with open(os.environ["RESTORE_SUDO_LOG"],"a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n'
                'raise SystemExit(subprocess.run(sys.argv[1:]).returncode)\n')
            sudo.chmod(0o755)
            result = subprocess.run(['bash', '-eu', '-c', self.ownership_step()], text=True, capture_output=True,
                                    env=dict(os.environ, HOME=str(home), RESTORE_SUDO_LOG=str(log),
                                             PATH=str(tools) + os.pathsep + os.environ['PATH']))
            cache.chmod(0o700)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            (cache / 'fetcher-locks').mkdir()
            calls = [json.loads(line) for line in log.read_text().splitlines()]
            self.assertEqual([['mkdir', '-p', '--', str(cache)],
                              ['chown', '-R', '--no-dereference', '--',
                               f'{os.getuid()}:{os.getgid()}', str(cache)]], calls)
            self.assertEqual(before, (sentinel.stat().st_uid, sentinel.stat().st_gid,
                                     stat.S_IMODE(sentinel.stat().st_mode), sentinel.read_bytes()))

    def test_client_cache_symlink_cannot_redirect_ownership_to_a_store(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / 'runner'
            (home / '.cache').mkdir(parents=True)
            store = root / 'nix-store'
            store.mkdir()
            (home / '.cache/nix').symlink_to(store, target_is_directory=True)
            before = store.stat()
            result = subprocess.run(['bash', '-eu', '-c', self.ownership_step()], text=True, capture_output=True,
                                    env=dict(os.environ, HOME=str(home)))
            self.assertEqual(69, result.returncode, result.stdout + result.stderr)
            self.assertEqual((before.st_uid, before.st_gid, before.st_mode),
                             (store.stat().st_uid, store.stat().st_gid, store.stat().st_mode))

    def test_actual_consumer_gate_requires_a_completed_exact_restore(self):
        source = (Path(__file__).resolve().parents[2] / '.github/actions/nix-sdk-cache/action.yml').read_text()
        block = source.split('    - name: Require the exact producer cache for qualification consumers\n', 1)[1]
        block = block.split('    - name:', 1)[0]
        body = re.search(r'      run: \|\n((?:        .*\n)+)', block)[1]
        body = '\n'.join(line[8:] for line in body.splitlines())
        for restored, hit, expected in (('producer-12', 'true', 0), ('', 'false', 69),
                                        ('producer-11', 'false', 69), ('producer-12', 'false', 69),
                                        ('', 'true', 69)):
            with self.subTest(restored=restored, hit=hit):
                result = subprocess.run(['bash', '-eu', '-c', body], capture_output=True, text=True,
                                        env=dict(os.environ, REQUESTED_KEY='producer-12',
                                                 RESTORED_KEY=restored, PRIMARY_HIT=hit))
                self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
