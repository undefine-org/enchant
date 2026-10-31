"""Actual Rust/Source native publication custody; never builds an SDK or NIF."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location('publication_vm', ROOT / 'test/scripts/test_execution_process_custody.py')
_vm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_vm)


class NativePublicationControls(unittest.TestCase):
    def test_actual_source_and_rust_publishers_share_destination_and_follower_custody(self):
        executable = Path(os.environ['BL_PUBLICATION_TEST_EXECUTABLE'])
        image = Path(os.environ['BL_CUSTODY_IMAGE'])
        identity = os.environ['BL_CUSTODY_TEST_SOURCE_SHA256']
        with tempfile.TemporaryDirectory(prefix='native-publication-') as directory:
            root = Path(directory)
            destination = root / 'project/priv/native/tiny.so'
            destination.parent.mkdir(parents=True)
            destination.write_bytes(b'old-installed')
            source = root / 'built.so'
            source.write_bytes(b'new-artifact')
            owner = observer = None
            sequence = 0
            publisher_seconds = 0
            started = time.monotonic()

            def publish(target=destination):
                nonlocal sequence, publisher_seconds
                sequence += 1
                result = root / f'publication-{sequence}.txt'
                env = dict(os.environ, BL_PUBLICATION_TEST_SOURCE=str(source),
                           BL_PUBLICATION_TEST_DESTINATION=str(target), BL_PUBLICATION_TEST_RESULT=str(result))
                start = time.monotonic()
                completed = subprocess.run([str(executable), '--exact', 'builder_tests::native_publication_subprocess_worker',
                                            '--ignored', '--nocapture', '--test-threads=1'],
                                           env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10)
                publisher_seconds += time.monotonic() - start
                self.assertEqual(0, completed.returncode, completed.stdout)
                self.assertIn('BUILD-CUSTODY-SOURCE ' + identity, completed.stdout)
                self.assertTrue(result.is_file(), completed.stdout)
                return result.read_text()

            try:
                owner = _vm.VM(image, root, 'owner')
                observer = _vm.VM(image, root, 'observer')
                vm_preparation = time.monotonic() - started
                execution_start = time.monotonic()
                scope = owner.ask('artifact_scope', destination=str(destination))['scope']
                held = owner.ask('claim', out=scope)
                self.assertTrue(held['acquired'])
                diagnostic = Path(scope) / '.claim'
                record = diagnostic.read_bytes()
                inode = destination.stat().st_ino
                self.assertIn('held', publish(), 'a real Source claim must exclude the Rust publisher')
                self.assertEqual(b'old-installed', destination.read_bytes())
                self.assertEqual(inode, destination.stat().st_ino)
                self.assertEqual(record, diagnostic.read_bytes())
                owner.ask('release', out=scope)
                self.assertEqual('ok', publish())
                self.assertEqual(b'new-artifact', destination.read_bytes())
                self.assertNotEqual(inode, destination.stat().st_ino)
                inode = destination.stat().st_ino
                self.assertEqual('ok', publish())
                self.assertEqual(inode, destination.stat().st_ino, 'identical bytes retain their inode')
                # A shared real compiler follower remains after actual owner VM death.
                held = owner.ask('claim', out=scope)
                observer.ask('follow', context=held['context'])
                owner.close()
                owner = None
                self.assertIn('held', publish())
                observer.ask('release_follower')
                self.assertEqual('ok', publish())
                self.assertEqual({'ran': False, 'result': 'stale-workspace-claim'},
                                 observer.ask('late_follower', context=held['context']))
                # Directory alias and ordinary Source claim must name the same anchor.
                alias = root / 'native-alias'
                alias.symlink_to(destination.parent, target_is_directory=True)
                alias_target = alias / destination.name
                alias_scope = observer.ask('artifact_scope', destination=str(alias_target))['scope']
                self.assertTrue(observer.ask('claim', out=alias_scope)['acquired'])
                self.assertIn('held', publish())
                observer.ask('release', out=alias_scope)
                self.assertEqual('ok', publish(alias_target))
                # Reverse direction uses the actual Rust admission guard, then
                # kills its real owner. It never fabricates Source authority.
                entered, finish = root / 'rust-entered', root / 'rust-finish'
                env = dict(os.environ, BL_PUBLICATION_TEST_SOURCE=str(source),
                           BL_PUBLICATION_TEST_DESTINATION=str(alias_target),
                           BL_PUBLICATION_TEST_RESULT=str(entered), BL_PUBLICATION_TEST_HOLD_UNTIL=str(finish))
                child = subprocess.Popen([str(executable), '--exact', 'builder_tests::native_publication_subprocess_worker',
                                          '--ignored', '--nocapture', '--test-threads=1'], env=env,
                                         text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                try:
                    deadline = time.monotonic() + 5
                    while not entered.exists():
                        self.assertIsNone(child.poll(), 'Rust holder exited before admission')
                        self.assertLess(time.monotonic(), deadline, 'Rust holder failed to enter')
                        time.sleep(.005)
                    self.assertEqual('held', entered.read_text())
                    self.assertFalse(observer.ask('claim', out=scope)['acquired'],
                                     'Rust custody must exclude actual Source admission')
                    child.kill()
                    output, _ = child.communicate(timeout=5)
                    self.assertIn('BUILD-CUSTODY-SOURCE ' + identity, output)
                finally:
                    if child.poll() is None:
                        child.kill()
                    child.communicate(timeout=5)
                self.assertTrue(observer.ask('claim', out=scope)['acquired'], 'Rust death must release custody')
                observer.ask('release', out=scope)
                self.assertEqual([], list(destination.parent.glob('tiny.so.tmp-*')))
                print('native-publication-control ' + json.dumps({'status': 'passed', 'source_scope': scope,
                      'native_source_identity': identity, 'actual_os_vms': 2, 'publication_attempts': sequence,
                      'vm_preparation_seconds': round(vm_preparation, 3),
                      'execution_seconds': round(time.monotonic() - execution_start, 3),
                      'publisher_subprocess_seconds': round(publisher_seconds, 3)}))
            finally:
                if owner is not None:
                    owner.close()
                if observer is not None:
                    observer.close()


if __name__ == '__main__':
    unittest.main()
