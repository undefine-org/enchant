import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('station', ROOT / 'nix/build-station.py')
STATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STATION)
SOURCE = '/nix/store/' + 'a' * 32 + '-source'
SDK = '/nix/store/' + 'b' * 32 + '-sdk'
OUTPUT = '/nix/store/' + 'c' * 32 + '-output'


class BuildStationTests(unittest.TestCase):
    def test_nix_features_do_not_replace_operator_policy_or_credentials(self):
        policy = 'include /operator/nix.conf'
        with patch.dict(os.environ, NIX_CONFIG=policy, NIX_SSHOPTS='-F/operator/ssh.conf'), \
                patch.object(STATION.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
            STATION.command(['nix', 'build', '--file', 'recipe.nix'])
            argv = run.call_args.args[0]
            self.assertEqual(['nix', '--extra-experimental-features', 'nix-command flakes', 'build'], argv[:4])
            self.assertNotIn('env', run.call_args.kwargs)
            self.assertEqual(policy, os.environ['NIX_CONFIG'])

    def test_finite_operations_share_the_normal_pinned_recipes(self):
        for value, recipe in [
            ({'version': 1, 'kind': 'sdk', 'source': SOURCE, 'product': 'sdk'}, 'sdk-artifact.nix'),
            ({'version': 1, 'kind': 'release', 'sdk': SDK}, 'portable-artifact.nix'),
            ({'version': 1, 'kind': 'application', 'sdk': SDK, 'request': {'source': SOURCE}}, 'application-artifact.nix'),
            ({'version': 1, 'kind': 'native', 'request': {'source': SOURCE}}, 'native-artifact.nix')]:
            with self.subTest(kind=value['kind']):
                arguments = STATION.arguments(value)
                self.assertEqual(['--file', str(STATION.PLATFORM / 'nix' / recipe)], arguments[:2])
        for patch_value in ({'argv': ['sh']}, {'source': '/tmp/live'}, {'product': 'arbitrary'}, {'version': 4}):
            with self.subTest(patch=patch_value), self.assertRaises((ValueError, KeyError)):
                STATION.operation({**dict(version=1, kind='sdk', source=SOURCE, product='sdk'), **patch_value})

    def test_remote_evaluation_copies_inputs_then_result_and_retains_before_ack(self):
        value = dict(version=1, kind='release', sdk=SDK)
        calls = []

        def command(argv, **options):
            calls.append((argv, options))
            if argv[0] == 'ssh' and 'input' in options:
                message = json.loads(options['input'])
                if message['action'] == 'build':
                    response = dict(version=1, ticket=message['ticket'], operationSHA=STATION.digest(value),
                                    host='fixture-station', rows=[dict(outputs={'out': OUTPUT})])
                    return subprocess.CompletedProcess(argv, 0, json.dumps(response))
            return subprocess.CompletedProcess(argv, 0, '')

        description = dict(version=1, storeUri='ssh-ng://fixture-station', transport=['ssh', 'fixture-station', '{endpoint}'])
        with patch.object(STATION, 'command', command):
            rows = STATION.client(value, '/tmp/owned-root', description)
        self.assertEqual(OUTPUT, rows[0]['outputs']['out'])
        self.assertEqual(['nix', 'copy', '--to', description['storeUri']], calls[0][0][:4])
        self.assertIn(SDK, calls[0][0])
        self.assertEqual(str(STATION.PLATFORM / 'bin/beam-build-station'), calls[1][0][-1])
        self.assertEqual(['nix', 'copy', '--from', description['storeUri'], OUTPUT], calls[2][0])
        self.assertEqual('nix-store', calls[3][0][0])
        self.assertEqual('release', json.loads(calls[4][1]['input'])['action'])

    def test_a_station_failure_never_falls_back_to_local_evaluation(self):
        description = dict(version=1, storeUri='ssh-ng://fixture', transport=['ssh', 'fixture', '{endpoint}'])
        with patch.object(STATION, 'command', side_effect=subprocess.CalledProcessError(255, 'ssh')) as command:
            with self.assertRaises(subprocess.CalledProcessError):
                STATION.client(dict(version=1, kind='release', sdk=SDK), '/tmp/owned-root', description)
        self.assertEqual(1, command.call_count)

    def test_endpoint_keeps_separate_request_roots_and_acknowledges_only_its_ticket(self):
        value = dict(version=1, kind='release', sdk=SDK)
        with tempfile.TemporaryDirectory() as directory, patch.dict(STATION.os.environ, XDG_CACHE_HOME=directory):
            with patch.object(STATION, 'command', return_value=subprocess.CompletedProcess([], 0, json.dumps([dict(outputs={'out': OUTPUT})]))):
                for letter in ('a', 'b'):
                    response = STATION.serve(dict(version=1, action='build', operation=value, ticket=letter * 64))
                    self.assertEqual(STATION.digest(value), response['operationSHA'])
            STATION.serve(dict(version=1, action='release', ticket='a' * 64))
            roots = Path(directory) / 'beam_lisp/station'
            self.assertFalse((roots / ('a' * 64)).exists())
            self.assertTrue((roots / ('b' * 64)).exists())
            with self.assertRaises(ValueError):
                STATION.serve(dict(version=1, action='release', ticket='../escape'))


if __name__ == '__main__':
    unittest.main()
