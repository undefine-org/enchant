"""Actual Source native producer and surviving real Cargo build script."""
import importlib.util
import json
import os
from pathlib import Path
import select
import signal
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location('source_command_vm', ROOT / 'test/scripts/test_execution_process_custody.py')
_vm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_vm)


class SourceCommandCustody(unittest.TestCase):
    def test_actual_native_producer_excludes_replacement_after_beam_and_cargo_die(self):
        image = Path(os.environ['BL_CUSTODY_IMAGE'])
        with tempfile.TemporaryDirectory(prefix='source-command-custody-') as directory:
            root = Path(directory)
            project = root / 'project'
            crate = project / 'native/custody_probe'
            (crate / 'src').mkdir(parents=True)
            (crate / 'Cargo.toml').write_text('[package]\nname="custody_probe"\nversion="0.0.0"\n'
                                             'edition="2021"\nbuild="src/build.rs"\n[workspace]\n'
                                             '[lib]\ncrate-type=["cdylib"]\n')
            (crate / 'Cargo.lock').write_text('version=4\n[[package]]\nname="custody_probe"\nversion="0.0.0"\n')
            (crate / 'src/lib.rs').write_text('#[no_mangle]\npub extern "C" fn answer() -> u8 { 42 }\n')
            # Included in the actual Source key; no mutable out-of-key build.rs.
            (crate / 'src/build.rs').write_text(r'''
fn main() {
    let root = std::path::PathBuf::from(std::env::var_os("BL_CUSTODY_EXTERNAL_ROOT").unwrap());
    let status = std::fs::read_to_string("/proc/self/status").unwrap();
    let parent = status.lines().find_map(|line| line.strip_prefix("PPid:")).unwrap().trim();
    std::fs::write(root.join("cargo-pid"), parent).unwrap();
    std::fs::write(root.join("external-pid"), std::process::id().to_string()).unwrap();
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(30);
    while !root.join("finish").exists() {
        assert!(std::time::Instant::now() < deadline, "Source command test timed out");
        std::thread::sleep(std::time::Duration::from_millis(5));
    }
    std::fs::write(root.join("external-exited"), "exited").unwrap();
}
''')
            owner = observer = None
            child_fd = cargo_fd = None
            start = time.monotonic()
            try:
                with patch.dict(os.environ, {'XDG_CACHE_HOME': str(root / 'cache'),
                                             'BL_CUSTODY_EXTERNAL_ROOT': str(root), 'CARGO_NET_OFFLINE': 'true'}):
                    owner = _vm.VM(image, root, 'owner')
                    observer = _vm.VM(image, root, 'observer')
                preparation = time.monotonic() - start
                scope = owner.ask('native_scope', project=str(project), crate='custody_probe')['scope']
                owner.send('native_build', project=str(project), crate='custody_probe')
                _vm.wait_for_file(root / 'external-pid', owner.process, timeout=20)
                child_pid = int((root / 'external-pid').read_text())
                cargo_pid = int((root / 'cargo-pid').read_text())
                child_fd, cargo_fd = os.pidfd_open(child_pid), os.pidfd_open(cargo_pid)
                self.assertEqual([], select.select([child_fd, cargo_fd], [], [], 0)[0])
                self.assertIn('cargo', Path(f'/proc/{cargo_pid}/exe').resolve().name)
                # Kill only the actual owner, not its entire process group.
                owner.process.kill()
                owner.process.wait(timeout=5)
                signal.pidfd_send_signal(cargo_fd, signal.SIGKILL)
                self.assertEqual([], select.select([child_fd], [], [], 0)[0], 'real build script must still be alive')
                acquired = observer.ask('claim', out=scope)
                self.assertFalse(acquired['acquired'], 'a real Source producer must exclude replacement while its orphan writes')
                self.assertEqual('child', acquired['custody'])
                (root / 'finish').write_text('finish')
                self.assertTrue(select.select([child_fd], [], [], 5)[0], 'actual build script must exit')
                deadline = time.monotonic() + 5
                while True:
                    acquired = observer.ask('claim', out=scope)
                    if acquired['acquired']:
                        break
                    self.assertLess(time.monotonic(), deadline, 'custody not released after last writer exit')
                    time.sleep(.005)
                observer.ask('release', out=scope)
                print('source-command-custody ' + json.dumps({'status': 'passed', 'scope': scope,
                      'preparation_seconds': round(preparation, 3),
                      'execution_seconds': round(time.monotonic() - start - preparation, 3),
                      'actual_os_vms': 2, 'real_cargo_and_build_script': True}))
            finally:
                (root / 'finish').write_text('finish')
                if child_fd is not None:
                    if not select.select([child_fd], [], [], 3)[0]:
                        signal.pidfd_send_signal(child_fd, signal.SIGKILL)
                    os.close(child_fd)
                if cargo_fd is not None:
                    if not select.select([cargo_fd], [], [], 3)[0]:
                        signal.pidfd_send_signal(cargo_fd, signal.SIGKILL)
                    os.close(cargo_fd)
                if owner is not None:
                    owner.close()
                if observer is not None:
                    observer.close()


if __name__ == '__main__':
    unittest.main()
