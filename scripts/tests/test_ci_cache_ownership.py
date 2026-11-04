"""Execute the actual cache repair against readonly caches and store links."""
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[2]


class CacheOwnershipTest(unittest.TestCase):
    def repair(self, home):
        action = (ROOT / '.github/actions/nix-sdk-cache/action.yml').read_text()
        step = action.split('    - name: Restore runner ownership of client and Beam Lisp caches\n', 1)[1].split('    - name:', 1)[0]
        script = textwrap.dedent(step.split('      run: |\n', 1)[1])
        tools = home / 'tools'
        tools.mkdir()
        sudo = tools / 'sudo'
        sudo.write_text('#!/bin/sh\nexec "$@"\n')
        sudo.chmod(0o755)
        return subprocess.run(['bash', '-c', script], env=dict(os.environ, HOME=str(home),
                              PATH=str(tools) + ':' + os.environ['PATH']), capture_output=True, text=True)

    def test_staging_is_writable_and_retained_store_targets_are_untouched(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            for name in ('nix', 'beam_lisp', 'enchant-ci'):
                cache = home / '.cache' / name
                cache.mkdir(parents=True)
                (cache / 'readonly').write_bytes(b'cached bytes')
                (cache / 'readonly').chmod(0o400)
                cache.chmod(0o500)
            store = home / 'immutable-store'
            store.mkdir()
            payload = store / 'sdk'
            payload.write_bytes(b'immutable SDK')
            payload.chmod(0o444)
            (home / '.cache/enchant-ci').chmod(0o700)
            (home / '.cache/enchant-ci/sdk-root').symlink_to(store)
            result = self.repair(home)
            self.assertEqual(0, result.returncode, result.stderr)
            for name in ('nix', 'beam_lisp', 'enchant-ci'):
                cache = home / '.cache' / name
                self.assertTrue(cache.stat().st_mode & stat.S_IWUSR)
                self.assertTrue((cache / 'readonly').stat().st_mode & stat.S_IWUSR)
                self.assertEqual(b'cached bytes', (cache / 'readonly').read_bytes())
            self.assertEqual(0o444, stat.S_IMODE(payload.stat().st_mode))
            self.assertEqual(b'immutable SDK', payload.read_bytes())

    def test_a_top_level_cache_symlink_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            (home / '.cache').mkdir()
            target = home / 'store'
            target.mkdir()
            (home / '.cache/beam_lisp').symlink_to(target)
            result = self.repair(home)
            self.assertNotEqual(0, result.returncode)
            self.assertIn('cache must be a directory: beam_lisp', result.stdout)
