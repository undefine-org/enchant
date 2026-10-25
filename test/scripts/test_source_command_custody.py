"""Actual Source native producer and surviving real Cargo build script."""
import importlib.util
import json
import os
from pathlib import Path
import select
import signal
import shutil
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location('source_command_vm', ROOT / 'test/scripts/test_execution_process_custody.py')
_vm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_vm)


class SourceCommandCustody(unittest.TestCase):
    def test_descriptor_filtering_child_keeps_source_and_read_loans_after_both_launchers_die(self):
        image = Path(os.environ['BL_CUSTODY_IMAGE'])
        with tempfile.TemporaryDirectory(prefix='source-domain-filter-') as directory:
            root = Path(directory)
            scope, cwd, tools = root / 'workspace', root / 'cwd with spaces', root / 'tools'
            cwd.mkdir(); tools.mkdir()
            (tools / 'python3').symlink_to(Path(sys.executable).resolve())
            readonly = root / 'generation-lock'
            readonly.touch()
            owner = observer = None
            child_fd = helper_fd = None
            start = time.monotonic()
            try:
                owner = _vm.VM(image, root, 'owner')
                observer = _vm.VM(image, root, 'observer')
                preparation = time.monotonic() - start
                # Reuse the owners for a genuine new BEAM before any SDK load.
                preboot = root / 'preboot'
                self.assertTrue(owner.ask('claim', out=str(preboot))['acquired'])
                probe = ('import fcntl,os,sys;f=os.open(sys.argv[1],os.O_RDWR);'
                         '\ntry:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)'
                         '\nexcept BlockingIOError:sys.exit(17)')
                script = ('[python, probe, lock, ready, finish] = System.argv()\n'
                          '{_, 17} = System.cmd(python, ["-c", probe, lock])\n'
                          'false = :code.is_loaded(BeamLisp.Ns.Core)\n'
                          'File.write!(ready, System.pid())\n'
                          'wait = fn wait -> if !File.exists?(finish), do: (Process.sleep(5); wait.(wait)) end\n'
                          'wait.(wait)\n')
                sequence = owner.send('managed_command', root=str(preboot),
                                      program=str(Path(shutil.which('elixir')).resolve()),
                                      argv=['--erl', '+S 2:2 +SDcpu 1:1 +SDio 1', '-e', script, '--', str(Path(sys.executable).resolve()), probe,
                                            str(readonly), str(root / 'preboot-ready'), str(root / 'preboot-finish')],
                                      read_locks=[str(readonly)])
                _vm.wait_for_file(root / 'preboot-ready', owner.process, timeout=15)
                self.assertEqual({'status': 'busy'}, observer.ask('probe_lock', path=str(readonly)))
                (root / 'preboot-finish').write_text('finish')
                self.assertEqual(0, owner.result(sequence)['exit'])
                self.assertEqual({'status': 'ok'}, observer.ask('probe_lock', path=str(readonly)))
                owner.ask('release', out=str(preboot))
                self.assertTrue(owner.ask('claim', out=str(scope))['acquired'])
                program = r'''
import fcntl,json,os,sys,time
from pathlib import Path
os.closerange(3,65536)
root=Path(sys.argv[1]);read=os.open(root/'generation-lock',os.O_RDWR)
try:
 fcntl.flock(read,fcntl.LOCK_EX|fcntl.LOCK_NB);busy=False
except BlockingIOError:busy=True
os.close(read)
root.joinpath('observed').write_text(json.dumps({'cwd':os.getcwd(),'argv':sys.argv[2:],
 'request':os.environ.get('DOMAIN_REQUEST_TOKEN'),'control_visible':'NOTIFY_SOCKET' in os.environ,
 'read_busy_at_first_instruction':busy,'helper':os.getppid()}))
root.joinpath('child').write_text(str(os.getpid()))
while not root.joinpath('finish').exists():time.sleep(.005)
root.joinpath('workspace/witness').write_text('protected write')
'''
                owner.send('managed_command', root=str(scope), program='python3',
                           argv=['-c', program, str(root), 'two words', '$(no-shell)', 'Ω'],
                           cwd=str(cwd), read_locks=[str(readonly)],
                           env={'PATH': str(tools), 'DOMAIN_REQUEST_TOKEN': 'private-request-env',
                                'DBUS_SESSION_BUS_ADDRESS': 'invalid-request-bus', 'NOTIFY_SOCKET': 'not-the-controller'})
                _vm.wait_for_file(root / 'child', owner.process, timeout=15)
                observed = json.loads((root / 'observed').read_text())
                self.assertEqual(str(cwd), observed['cwd'])
                self.assertEqual(['two words', '$(no-shell)', 'Ω'], observed['argv'])
                self.assertEqual('private-request-env', observed['request'])
                self.assertFalse(observed['control_visible'])
                self.assertTrue(observed['read_busy_at_first_instruction'])
                child_fd = os.pidfd_open(int((root / 'child').read_text()))
                helper_fd = os.pidfd_open(observed['helper'])
                self.assertNotIn(b'private-request-env', Path(f'/proc/{observed["helper"]}/cmdline').read_bytes())
                owner.process.kill(); owner.process.wait(timeout=5)
                signal.pidfd_send_signal(helper_fd, signal.SIGKILL)
                self.assertTrue(select.select([helper_fd], [], [], 3)[0])
                self.assertFalse(select.select([child_fd], [], [], 0)[0])
                self.assertEqual({'status': 'busy'}, observer.ask('probe_lock', path=str(readonly)))
                acquired = observer.ask('claim', out=str(scope))
                self.assertFalse(acquired['acquired'])
                self.assertEqual('child', acquired['custody'])
                (root / 'finish').write_text('finish')
                self.assertTrue(select.select([child_fd], [], [], 5)[0])
                self.assertEqual('protected write', (scope / 'witness').read_text())
                deadline = time.monotonic() + 5
                while not observer.ask('claim', out=str(scope))['acquired']:
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(.005)
                observer.ask('release', out=str(scope))
                self.assertEqual({'status': 'ok'}, observer.ask('probe_lock', path=str(readonly)))
                print('source-domain-filter ' + json.dumps({'status': 'passed',
                      'vm_preparation_seconds': round(preparation, 3),
                      'execution_seconds': round(time.monotonic()-start-preparation, 3)}))
            finally:
                (root / 'finish').write_text('finish')
                if child_fd is not None:
                    if not select.select([child_fd], [], [], 3)[0]: signal.pidfd_send_signal(child_fd, signal.SIGKILL)
                    os.close(child_fd)
                if helper_fd is not None:
                    if not select.select([helper_fd], [], [], 3)[0]: signal.pidfd_send_signal(helper_fd, signal.SIGKILL)
                    os.close(helper_fd)
                if owner is not None: owner.close()
                if observer is not None: observer.close()

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
    let witness = std::path::PathBuf::from(std::env::var_os("OUT_DIR").unwrap()).join("after-owner-death.txt");
    std::fs::write(root.join("witness-path"), witness.to_str().unwrap()).unwrap();
    std::fs::write(root.join("cargo-pid"), parent).unwrap();
    std::fs::write(root.join("external-pid"), std::process::id().to_string()).unwrap();
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(30);
    while !root.join("finish").exists() {
        assert!(std::time::Instant::now() < deadline, "Source command test timed out");
        std::thread::sleep(std::time::Duration::from_millis(5));
    }
    std::fs::write(witness, "actual write after both ancestors died").unwrap();
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
                witness = Path((root / 'witness-path').read_text())
                self.assertTrue(witness.resolve().is_relative_to(Path(scope).resolve()),
                                'actual Cargo OUT_DIR must lie inside the claimed producer scope')
                self.assertFalse(witness.exists())
                acquired = observer.ask('claim', out=scope)
                (root / 'finish').write_text('finish')
                self.assertTrue(select.select([child_fd], [], [], 5)[0], 'actual build script must exit')
                self.assertEqual('actual write after both ancestors died', witness.read_text())
                self.assertFalse(acquired['acquired'], 'a real Source producer must exclude replacement while its orphan writes')
                self.assertEqual('child', acquired['custody'])
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
