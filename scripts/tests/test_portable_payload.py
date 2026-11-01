"""Exercise the production payload pass on real ELF bytes and shell scripts."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[2]
PATCHER = os.environ.get('BL_TEST_PATCHELF') or shutil.which('patchelf')


@unittest.skipUnless(PATCHER, 'Set BL_TEST_PATCHELF to the pinned patchelf executable')
class PortablePayloadTests(unittest.TestCase):
    def run_pass(self, directory):
        recipe = (ROOT / 'nix/bl-drop.nix').read_text()
        program = textwrap.dedent(recipe.split("<<'PORTABLE'\n", 1)[1].split('\n      PORTABLE', 1)[0])
        program = program.replace('${pkgs.patchelf}/bin/patchelf', PATCHER)
        return subprocess.run(['python3', '-c', program],
                              env=dict(os.environ, TMPDIR=str(directory)),
                              capture_output=True, text=True, timeout=30)

    def test_actual_elf_and_shells_are_portable_without_touching_symlink_targets(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            payload = base / 'payload'
            payload.mkdir()
            executable = payload / 'true'
            shutil.copyfile(shutil.which('true'), executable)
            executable.chmod(0o755)
            original_mode = executable.stat().st_mode
            self.assertEqual(b'\x7fELF', executable.read_bytes()[:4])
            for shell in ('bash', 'sh', 'dash'):
                (payload / shell).write_bytes(f'#!/nix/store/pinned-shell/bin/{shell}\nprintf ready\n'.encode())
            (payload / 'ordinary').write_bytes(b'ordinary data\n')
            foreign = base / 'foreign'
            foreign.write_bytes(b'#!/nix/store/pinned-python/bin/python3\npass\n')
            (payload / 'link').symlink_to(foreign)
            result = self.run_pass(base)
            self.assertEqual(0, result.returncode, result.stderr)
            counts = json.loads(result.stdout.split('PORTABLE-PAYLOAD ', 1)[1])
            self.assertEqual(1, counts['elf'])
            self.assertEqual(3, counts['interpreters'])
            self.assertEqual('/lib64/ld-linux-x86-64.so.2', subprocess.check_output(
                [PATCHER, '--print-interpreter', executable], text=True).strip())
            self.assertEqual('', subprocess.check_output([PATCHER, '--print-rpath', executable], text=True).strip())
            self.assertEqual(original_mode, executable.stat().st_mode)
            self.assertEqual(b'#!/bin/bash\nprintf ready\n', (payload / 'bash').read_bytes())
            for shell in ('sh', 'dash'):
                self.assertEqual(b'#!/bin/sh\nprintf ready\n', (payload / shell).read_bytes())
            self.assertEqual(b'ordinary data\n', (payload / 'ordinary').read_bytes())
            self.assertTrue((payload / 'link').is_symlink())
            self.assertEqual(b'#!/nix/store/pinned-python/bin/python3\npass\n', foreign.read_bytes())

    def test_an_undeclared_portable_interpreter_still_blocks_packaging(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            (base / 'payload').mkdir()
            (base / 'payload/script').write_bytes(b'#!/nix/store/pinned-python/bin/python3\npass\n')
            result = self.run_pass(base)
            self.assertNotEqual(0, result.returncode)
            self.assertIn('undeclared portable interpreter', result.stderr)


if __name__ == '__main__':
    unittest.main()
