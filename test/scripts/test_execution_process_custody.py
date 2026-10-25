#!/usr/bin/env python3
"""Actual CLI/API, follower and generation custody across two reused BEAM VMs."""
import hashlib
from collections import deque
import json
import os
from pathlib import Path
import selectors
import shutil
import signal
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / 'test/scripts/execution-custody-worker.exs'
BUILD_BEFORE = '(c/acquire! out "build producer")'
BUILD_AFTER = '{:ok? true}'
CACHE_BEFORE = '(generation_lock_path root (Map/get g :name)) false true'
CACHE_AFTER = '(generation_lock_path root (Map/get g :name)) true true'


class VM:
    def __init__(self, image, directory, label):
        self.sequence = 0
        self.buffer = b''
        self.noise = deque(maxlen=100)
        self.stderr = (directory / (label + '.stderr')).open('wb')
        executable = shutil.which('elixir')
        if not executable:
            raise RuntimeError('required elixir prerequisite missing')
        command = [executable, '--erl', '+S 2:2 +SDcpu 1:1 +SDio 1']
        own = image / '.bl/lib/beam_lisp-0.1.0/ebin'
        if not own.is_dir():
            own = image / 'ebin'
        if not own.is_dir():
            raise RuntimeError('require coherent checkout/candidate application with its own ebin')
        paths = sorted((image / '.bl/lib').glob('*/ebin'))
        paths += [Path(p) for p in json.loads(os.environ.get('BL_CUSTODY_EBINS', '[]'))]
        for path in dict.fromkeys(p.resolve() for p in paths if p.resolve() != own.resolve()):
            command += ['-pa', str(path)]
        # -pa prepends: place the actual candidate last so dependency paths
        # cannot silently choose another beam_lisp floor with the same key.
        command += ['-pa', str(own), str(WORKER)]
        env = {**os.environ, 'BL_ROOT': str(image), 'BL_DAEMON': 'off',
               'BEAM_LISP_AOT_CACHE': 'off'}
        self.process = subprocess.Popen(command, cwd=directory, env=env, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=self.stderr, start_new_session=True)
        self.poller = selectors.DefaultSelector()
        self.poller.register(self.process.stdout, selectors.EVENT_READ)
        try:
            self.ready = self.read(40)
            if not self.ready.get('ready'):
                raise RuntimeError('missing worker readiness: ' + repr(self.ready))
            if Path(self.ready['root']).resolve() != (image / 'priv').resolve():
                raise RuntimeError('worker selected another physical runtime root')
            if self.ready['os_pid'] != str(self.process.pid):
                raise RuntimeError('worker wrapper PID differs from actual BEAM PID')
            scope = 'source-component' if 'BL_CUSTODY_COMPONENT_IDENTITY' in env else 'packaged-floor'
            if self.ready.get('identity_scope') != scope:
                raise RuntimeError('worker used a different identity scope')
        except BaseException:
            self.close()
            raise

    def read(self, timeout=30):
        deadline = time.monotonic() + timeout
        while True:
            if time.monotonic() >= deadline:
                raise TimeoutError('absolute worker reply budget expired')
            if b'\n' in self.buffer:
                line, self.buffer = self.buffer.split(b'\n', 1)
                if line.startswith(b'BL-CUSTODY '):
                    return json.loads(line[len(b'BL-CUSTODY '):])
                self.noise.append(line.decode(errors='replace'))
                continue
            if not self.poller.select(max(0, deadline - time.monotonic())):
                raise TimeoutError('worker reply timed out: ' + repr(list(self.noise)[-10:]))
            block = os.read(self.process.stdout.fileno(), 65536)
            if not block:
                self.stderr.flush()
                raise RuntimeError('worker exited: ' + Path(self.stderr.name).read_text())
            self.buffer += block

    def send(self, operation, **arguments):
        self.sequence += 1
        self.process.stdin.write((json.dumps({'id': self.sequence, 'op': operation, **arguments}) + '\n').encode())
        self.process.stdin.flush()
        return self.sequence

    def result(self, sequence):
        response = self.read()
        if response.get('id') != sequence or response.get('ok') is not True:
            raise RuntimeError('failed or unrelated worker reply: ' + repr(response))
        return response['value']

    def ask(self, operation, **arguments):
        return self.result(self.send(operation, **arguments))

    def close(self):
        if self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGKILL)
        self.process.wait(timeout=10)
        self.poller.close()
        self.process.stdin.close()
        self.process.stdout.close()
        self.stderr.close()


def wait_for_file(path, process, timeout=30):
    deadline = time.monotonic() + timeout
    while not path.is_file():
        if process.poll() is not None:
            raise RuntimeError('CLI owner died before its compilation barrier')
        if time.monotonic() >= deadline:
            raise TimeoutError('CLI never reached actual compiler barrier')
        time.sleep(0.01)


class ProcessCustodyControls(unittest.TestCase):
    def test_E06_E07_actual_processes_preserve_build_and_generation_custody(self):
        image = Path(os.environ.get('BL_CUSTODY_IMAGE', os.environ.get('BL_ROOT', ROOT))).resolve()
        build = (ROOT / 'priv/build/build.bl').read_text()
        cache = (ROOT / 'priv/host/aot_cache.bl').read_text()
        cli = (ROOT / 'priv/std/bl/cli.bl').read_text()
        self.assertEqual(cli.count('(if (not (:ok? acquired))'), 1)
        self.assertEqual(build.count(BUILD_BEFORE), 1)
        self.assertEqual(cache.count(CACHE_BEFORE), 1)
        with tempfile.TemporaryDirectory(prefix='history-process-custody-') as temporary:
            root = Path(temporary)
            cache_probe = root / 'shared-retirement.bl'
            build_probe = root / 'unclaimed-build.bl'
            cli_probe = root / 'claimless-cli.bl'
            self.assertEqual(cli.count('(ns bl.cli\n'), 1)
            cli_probe.write_text(cli.replace('(ns bl.cli\n', '(ns execution.history.claimless-cli\n')
                                .replace('(if (not (:ok? acquired))', '(if false'))
            cache_probe.write_text(cache.replace(CACHE_BEFORE, CACHE_AFTER))
            self.assertEqual(build.count('(ns build\n'), 1)
            build_probe.write_text(build.replace('(ns build\n', '(ns execution.history.unclaimed-build\n')
                                   .replace(BUILD_BEFORE, BUILD_AFTER))
            owner = collector = None
            try:
                # Startup is serial; both VMs then stay alive for every control.
                owner = VM(image, root, 'owner')
                collector = VM(image, root, 'collector')
                self.assertEqual(owner.ready['compiler_key'], collector.ready['compiler_key'])
                for worker in [owner, collector]:
                    expected_manifest = hashlib.sha256((image / 'priv/bootstrap/seed/manifest.term').read_bytes()).hexdigest()
                    self.assertEqual(worker.ready['manifest_sha256'], expected_manifest)
                    for field, variable in [('compiler_key', 'BL_CUSTODY_COMPILER_KEY'),
                                            ('native_identity', 'BL_CUSTODY_NATIVE_IDENTITY')]:
                        if variable in os.environ:
                            self.assertEqual(worker.ready[field], os.environ[variable])
                identity = owner.ready
                self.assertEqual(owner.ready['native_identity'], collector.ready['native_identity'])
                self.assertNotEqual(owner.ready['os_pid'], collector.ready['os_pid'])
                collector.ask('prepare', cache_source=str(cache_probe), build_source=str(build_probe), cli_source=str(cli_probe), output=str(root / 'probe'))
                workspace = root / 'output'
                marker, release = root / 'compiling', root / 'continue'
                source, rival = root / 'owner.bl', root / 'rival.bl'
                source.write_text('(ns historical.cli.owner)\n'
                                  '(defmacro hold-compilation []\n'
                                  f' (File/write! {json.dumps(str(marker))} "entered")\n'
                                  ' (loop [n 0]\n'
                                  f'  (if (File/exists? {json.dumps(str(release))}) nil\n'
                                  '   (if (> n 2500) (throw "compilation barrier timed out")\n'
                                  '    (do (Process/sleep 10) (recur (inc n))))))\n'
                                  " (list 'defn 'answer [] 42))\n(hold-compilation)\n")
                rival.write_text('(ns historical.api.rival) (defn answer [] 99)\n')
                pending = owner.send('cli', root=str(root), source=str(source), out=str(workspace))
                wait_for_file(marker, owner.process)
                log = workspace / 'build.log'
                before = log.read_bytes() if log.exists() else None
                good = collector.ask('build', namespace='build', source=str(rival), out=str(workspace))
                self.assertEqual(good['built'], 0)
                self.assertTrue(any('held by' in error for error in good['errors']), good)
                self.assertEqual(log.read_bytes() if log.exists() else None, before)
                cli_denied = collector.ask('cli', root=str(root), source=str(rival), out=str(workspace))
                self.assertEqual(cli_denied, {'exit': 1, 'events': 0})
                collector.ask('cli_mode', mutant=True)
                cli_mutant = collector.ask('cli', root=str(root), source=str(rival), out=str(workspace))
                self.assertEqual(cli_mutant, {'exit': 1, 'events': 2}, 'ignored CLI claim must expose premature build events')
                collector.ask('cli_mode', mutant=False)
                self.assertEqual(log.read_bytes() if log.exists() else None, before)
                bad = collector.ask('build', namespace='execution.history.unclaimed-build', source=str(rival), out=str(workspace))
                self.assertEqual(bad['errors'], [], bad)
                self.assertEqual(bad['built'], 1)
                self.assertNotEqual(log.read_bytes() if log.exists() else None, before,
                                    'bypassed SDK admission must expose the shared fact-log write')
                release.write_text('go')
                self.assertEqual(owner.result(pending)['exit'], 0)
                custody = owner.ask('claim', out=str(workspace))
                self.assertTrue(custody['acquired'])
                collector.ask('follow', context=custody['context'])
                gc = root / 'cache'
                gc.mkdir()
                owner.ask('cache_root', root=str(gc))
                collector.ask('cache_root', root=str(gc))
                active, transient = 'f' * 64, 'a' * 64
                live = owner.ready['compiler_key']
                def generation(key):
                    for directory in [gc / key, gc / 'sdk-build' / key]:
                        directory.mkdir(parents=True, exist_ok=True)
                        (directory / 'marker').write_text(key)
                        os.utime(directory, (1, 1))
                def exists(key):
                    return [(gc / key).is_dir(), (gc / 'sdk-build' / key).is_dir()]
                generation(active)
                generation(transient)
                owner.ask('hold_generation', key=transient)
                collector.ask('gc', active=active, mutant=False)
                self.assertEqual(exists(transient), [True, True])
                owner.ask('release_generation')
                collector.ask('gc', active=active, mutant=False)
                self.assertEqual(exists(transient), [False, False])
                generation(live)
                self.assertTrue(owner.ask('pin')['idle'])
                collector.ask('gc', active=active, mutant=False)
                self.assertEqual(exists(live), [True, True], 'idle VM custody protects both paths')
                collector.ask('gc', active=active, mutant=True)
                self.assertEqual(exists(live), [False, False], 'shared retirement mutant deletes live paths')
                generation(live)
                collector.ask('gc', active=active, mutant=False)
                self.assertEqual(exists(live), [True, True])
                # A single actual OS crash tests both native lifetime relations.
                owner.close()
                owner = None
                collector.ask('gc', active=active, mutant=False)
                self.assertEqual(exists(live), [False, False], 'VM crash releases generation custody')
                blocked = collector.ask('claim', out=str(workspace))
                self.assertFalse(blocked['acquired'])
                self.assertEqual(blocked['custody'], 'child')
                collector.ask('release_follower')
                self.assertTrue(collector.ask('claim', out=str(workspace))['acquired'])
                stale = collector.ask('late_follower', context=custody['context'])
                self.assertEqual(stale, {'ran': False, 'result': 'stale-workspace-claim'})
                collector.ask('release', out=str(workspace))
                self.assertEqual(exists(active), [True, True])
                print('history-E06-E07 ' + json.dumps({'build': {'normal': good, 'mutant': bad, 'cli': cli_denied, 'cli_mutant': cli_mutant},
                    'compiler_key': live, 'image': identity, 'actual_os_vms': 2, 'source_sha256': {
                    'priv/build/build.bl': hashlib.sha256(build.encode()).hexdigest(),
                    'priv/std/bl/cli.bl': hashlib.sha256(cli.encode()).hexdigest(),
                    'priv/host/aot_cache.bl': hashlib.sha256(cache.encode()).hexdigest()},
                    'active_idle_crash_retirement': True, 'follower_after_parent_crash': True,
                    'late_follower_refused_before_effect': True}, sort_keys=True))
            finally:
                if owner is not None:
                    owner.close()
                if collector is not None:
                    collector.close()


if __name__ == '__main__':
    unittest.main()
