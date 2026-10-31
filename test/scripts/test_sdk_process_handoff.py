#!/usr/bin/env python3
"""Actual user-manager handoff, including the original missing-PATH mutation.

Linux/systemd/Elixir are mandatory prerequisites for this focused component
control. Missing tools or a failed child fail; there are no skipped passes.
"""
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import tempfile
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[2]
PRODUCER = ROOT / 'test/scripts/sdk_build_persistence.py'


class ProcessHandoffControls(unittest.TestCase):
    def test_E12_setup_path_reaches_real_elixir_and_its_external_child(self):
        source = PRODUCER.read_text()
        before = "for key in ('PATH', 'BL_ROOT', 'PROBE_WORK', 'PROBE_PHASE', 'BEAM_LISP_AOT_CACHE_DIR', 'BL_DAEMON', 'ELIXIR_ERL_OPTIONS'):"
        after = "for key in ('BL_ROOT', 'PROBE_WORK', 'PROBE_PHASE', 'BEAM_LISP_AOT_CACHE_DIR', 'BL_DAEMON', 'ELIXIR_ERL_OPTIONS'):"
        self.assertEqual(source.count(before), 1)
        good = runpy.run_path(str(PRODUCER))['phase_command']
        namespace = {'__file__': str(PRODUCER), '__name__': 'historical_handoff_mutant'}
        exec(compile(source.replace(before, after), str(PRODUCER), 'exec'), namespace)
        bad = namespace['phase_command']
        for tool in ['systemd-run', 'systemctl', 'elixir']:
            self.assertIsNotNone(shutil.which(tool), f'missing required prerequisite: {tool}')
        # Endpoint isolation must not redirect systemctl/systemd-run away from
        # the real user manager. These clients use XDG_RUNTIME_DIR/systemd,
        # including when DBUS_SESSION_BUS_ADDRESS is explicitly preserved.
        manager_env = dict(os.environ)
        if manager_env.get('BL_TEST_USER_RUNTIME_DIR'):
            manager_env['XDG_RUNTIME_DIR'] = manager_env['BL_TEST_USER_RUNTIME_DIR']
        manager = subprocess.run(['systemctl', '--user', 'show-environment'],
                                 env=manager_env, capture_output=True, text=True, check=True, timeout=10).stdout
        with tempfile.TemporaryDirectory(prefix='history-service-path-') as temporary:
            work = Path(temporary)
            setup = work / 'setup toolchain'
            setup.mkdir()
            leaf = 'beam-lisp-handoff-' + uuid.uuid4().hex
            token = 'HANDOFF_TOKEN_' + uuid.uuid4().hex
            tool = setup / leaf
            tool.write_text('#!/bin/sh\nprintf %s ' + token + '\n')
            tool.chmod(0o755)
            self.assertNotIn(str(setup), manager, 'negative manager PATH must exclude setup')
            expression = (f'{{{json.dumps(token)}, 0}} = System.cmd({json.dumps(leaf)}, [])\n'
                          'IO.puts("HANDOFF_REAL_ELIXIR_READY")')
            command = [shutil.which('elixir'), '--erl', '+S 2:2 +SDcpu 1:1 +SDio 1', '-e', expression]
            env = {**manager_env, 'PATH': str(setup) + os.pathsep + os.environ['PATH'],
                   'BL_ROOT': str(work), 'PROBE_WORK': str(work), 'PROBE_PHASE': 'handoff',
                   'BEAM_LISP_AOT_CACHE_DIR': str(work / 'cache'), 'BL_DAEMON': 'off',
                   'ELIXIR_ERL_OPTIONS': '+S 2:2 +SDcpu 1:1 +SDio 1'}
            self.assertEqual(good(command, {}, use_systemd=False, image=work, unit='unused'), command)
            outcomes = {}
            for variant, launch in [('explicit', good), ('missing-path', bad)]:
                unit = f'bl-history-handoff-{os.getpid()}-{variant}'
                try:
                    result = subprocess.run(launch(command, env, use_systemd=True, image=work, unit=unit),
                                            env=env, capture_output=True, text=True, timeout=30)
                    output = result.stdout + result.stderr
                    outcomes[variant] = {'exit': result.returncode, 'output': output}
                    if variant == 'explicit':
                        self.assertEqual(result.returncode, 0, output)
                        self.assertIn('HANDOFF_REAL_ELIXIR_READY', output)
                    else:
                        self.assertNotEqual(result.returncode, 0, output)
                        self.assertNotIn('HANDOFF_REAL_ELIXIR_READY', output)
                        self.assertTrue((leaf in output and ('enoent' in output or 'no such file' in output))
                                        or 'exec: erl: not found' in output, output)
                finally:
                    subprocess.run(['systemctl', '--user', 'stop', unit],
                                   env=manager_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            print('history-E12 ' + json.dumps(outcomes, sort_keys=True))


if __name__ == '__main__':
    unittest.main()
