"""Real Git source-identity controls, without Nix production or a BEAM."""
from importlib.machinery import SourceFileLoader
import importlib.util
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_loader('committed', SourceFileLoader('committed', str(ROOT / 'scripts/ci-check-committed')))
committed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(committed)


class CommittedSourceTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'repo'
        self.root.mkdir()
        self.git('init', '-q')
        (self.root / 'priv').mkdir()
        (self.root / 'priv/value.bl').write_text('committed bytes\n')
        (self.root / 'bin').mkdir()
        (self.root / 'bin/example').write_text('#!/bin/sh\nexit 0\n')
        (self.root / 'bin/example').chmod(0o755)
        self.commit()

    def git(self, *args):
        return subprocess.check_output(['git', '-c', 'core.autocrlf=false', *args], cwd=self.root,
            env=dict(os.environ, GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1'), text=True).strip()

    def commit(self):
        self.git('add', '--force', '--all')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.test', 'commit', '-qm', 'source')

    def capture(self):
        target = Path(self.temporary.name) / 'snapshot'
        return committed.capture(self.root, 'HEAD', target), target

    def test_commit_bytes_modes_and_internal_links_survive_working_tree_edits(self):
        (self.root / 'priv/alias.bl').symlink_to('value.bl')
        self.commit()
        revision = self.git('rev-parse', 'HEAD')
        (self.root / 'priv/value.bl').write_text('unqualified edit\n')
        (self.root / 'bin/example').unlink()
        (self.root / 'priv/untracked.bl').write_text('unqualified new source\n')
        receipt, target = self.capture()
        self.assertEqual(revision, receipt['revision'])
        self.assertEqual('committed bytes\n', (target / 'priv/value.bl').read_text())
        self.assertEqual('committed bytes\n', (target / 'priv/alias.bl').read_text())
        self.assertEqual(0o755, (target / 'bin/example').stat().st_mode & 0o777)
        self.assertFalse((target / 'priv/untracked.bl').exists())
        self.assertEqual(3, receipt['files'])
        self.assertEqual(64, len(receipt['archive_sha256']))

    def test_export_ignore_cannot_silently_remove_committed_runtime_source(self):
        (self.root / '.gitattributes').write_text('priv/value.bl export-ignore\n')
        self.commit()
        with self.assertRaisesRegex(ValueError, 'omitted committed'):
            self.capture()

    def test_export_substitution_cannot_rewrite_committed_runtime_source(self):
        (self.root / 'priv/value.bl').write_text('$Format:%H$\n')
        (self.root / '.gitattributes').write_text('priv/value.bl export-subst\n')
        self.commit()
        with self.assertRaisesRegex(ValueError, 'changed committed source bytes'):
            self.capture()

    def test_links_cannot_escape_the_private_snapshot(self):
        (self.root / 'priv/outside.bl').symlink_to('/etc/passwd')
        self.commit()
        with self.assertRaises(tarfile.AbsoluteLinkError):
            self.capture()

    def test_forwarded_source_cannot_override_the_verified_snapshot(self):
        for option in ('--source', '--sou', '--source=/tmp'):
            with self.subTest(option=option):
                args = [option] if '=' in option else [option, '/tmp']
                output = Path(self.temporary.name) / 'results'
                result = subprocess.run(['python3', str(ROOT / 'scripts/ci-check-committed'),
                    '--revision', 'not-a-valid-commit', '--out', str(output), *args],
                    text=True, capture_output=True, timeout=5)
                self.assertNotEqual(0, result.returncode)
                self.assertIn('--source cannot override', result.stderr)
                self.assertFalse(Path(str(output) + '.inputs.json').exists())


if __name__ == '__main__':
    unittest.main()
