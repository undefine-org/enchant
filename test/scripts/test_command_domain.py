"""Real OS-domain controls; generic file loans here grant no Source authority."""
import fcntl
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import time
import unittest


class CommandDomainControls(unittest.TestCase):
    def request(self, root, program, timeout=10000, output=65536):
        (root / 'anchor').touch()
        (root / 'claim').write_text('current-cohort')
        return {'version': 1, 'follower': [str(root / 'anchor'), str(root / 'claim'), 'current-cohort'],
                'read_locks': [], 'program': str(Path(sys.executable).resolve()), 'argv': ['-c', program, str(root)],
                'cwd': str(root), 'limits': {'timeout_ms': timeout, 'output_bytes': output, 'memory_bytes': 268435456}}

    def launch(self, request):
        return subprocess.Popen([os.environ['BL_CUSTODY_EXECUTOR'], '--custody-command', json.dumps(request)],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def wait_ready(self, root, process):
        deadline = time.monotonic() + 5
        while not (root / 'child').exists():
            if process.poll() is not None:
                self.fail('domain ended before child readiness: ' + process.communicate()[0].decode(errors='replace'))
            self.assertLess(time.monotonic(), deadline, 'domain never reached the real child')
            time.sleep(.005)
        return os.pidfd_open(int((root / 'child').read_text()))

    def assert_released(self, root):
        with (root / 'anchor').open('r+') as anchor:
            deadline = time.monotonic() + 3
            while True:
                try:
                    fcntl.flock(anchor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return
                except BlockingIOError:
                    self.assertLess(time.monotonic(), deadline, 'domain left a kernel loan after all work stopped')
                    time.sleep(.005)

    def test_stale_context_and_invalid_descriptor_refuse_before_program_birth(self):
        with tempfile.TemporaryDirectory(prefix='command-refusal-') as directory:
            root = Path(directory)
            request = self.request(root, 'from pathlib import Path;import sys;Path(sys.argv[1],"born").touch()')
            request['follower'][2] = 'old-cohort'
            process = self.launch(request)
            output, _ = process.communicate(timeout=10)
            self.assertNotEqual(0, process.returncode)
            self.assertIn(b'stale workspace cohort', output)
            self.assertFalse((root / 'born').exists())
            self.assert_released(root)
            request['version'] = 99
            process = self.launch(request)
            output, _ = process.communicate(timeout=5)
            self.assertEqual(125, process.returncode)
            self.assertIn(b'unsupported protocol', output)
            self.assertFalse((root / 'born').exists())

    def test_deadline_stops_a_descriptor_filtering_setsid_orphan_before_releasing_its_loan(self):
        with tempfile.TemporaryDirectory(prefix='command-deadline-') as directory:
            root = Path(directory)
            descendant = ('import os,signal,sys,time;from pathlib import Path;os.closerange(3,65536);'
                          'signal.signal(signal.SIGTERM,signal.SIG_IGN);'
                          'Path(sys.argv[1],"child").write_text(str(os.getpid()));time.sleep(30)')
            program = ('import subprocess,sys;subprocess.Popen([sys.executable,"-c",' + repr(descendant)
                       + ',sys.argv[1]],close_fds=True,start_new_session=True)')
            process = self.launch(self.request(root, program, timeout=700))
            child = None
            try:
                child = self.wait_ready(root, process)
                with (root / 'anchor').open('r+') as anchor:
                    with self.assertRaises(BlockingIOError): fcntl.flock(anchor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                output, _ = process.communicate(timeout=8)
                self.assertNotEqual(0, process.returncode, output)
                self.assertTrue(select.select([child], [], [], 1)[0], 'escaped process group must still be stopped')
                self.assert_released(root)
            finally:
                if child is not None:
                    if not select.select([child], [], [], 0)[0]: signal.pidfd_send_signal(child, signal.SIGKILL)
                    os.close(child)
                if process.poll() is None: process.communicate(timeout=8)

    def test_output_capacity_stops_the_whole_domain_and_retains_only_bounded_output(self):
        with tempfile.TemporaryDirectory(prefix='command-output-') as directory:
            root = Path(directory)
            program = ('import os,sys,time;from pathlib import Path;'
                       'Path(sys.argv[1],"child").write_text(str(os.getpid()));'
                       'os.write(1,b"x"*65536);time.sleep(30)')
            process = self.launch(self.request(root, program, output=64))
            child = None
            try:
                child = self.wait_ready(root, process)
                output, _ = process.communicate(timeout=8)
                self.assertEqual(125, process.returncode, output)
                self.assertIn(b'command output capacity exceeded', output)
                self.assertLess(len(output), 512)
                self.assertTrue(select.select([child], [], [], 1)[0])
                self.assert_released(root)
            finally:
                if child is not None:
                    if not select.select([child], [], [], 0)[0]: signal.pidfd_send_signal(child, signal.SIGKILL)
                    os.close(child)
                if process.poll() is None: process.communicate(timeout=8)


if __name__ == '__main__':
    unittest.main()
