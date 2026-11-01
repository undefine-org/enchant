"""Evaluate actual compiler reuse decisions without starting a compiler or VM."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class CompilerProductIdentityTests(unittest.TestCase):
    def test_library_changes_preserve_the_floor_and_a_new_predecessor_does_not_rotate_it(self):
        with tempfile.TemporaryDirectory(prefix='compiler-identity-') as temporary:
            base = Path(temporary)
            source = base / 'source'
            names = ['priv/boot', 'priv/host', 'priv/self', 'priv/bootstrap/seed', 'priv/build',
                     'priv/std/multi.bl', 'priv/std/bl/env.bl.md', 'priv/std/bl/util.bl.md',
                     'priv/std/bl/loading-policy.bl', 'priv/std/bl/native-declarations.bl',
                     'priv/std/proc/owner-registry.bl', 'priv/std/vm/native.bl', 'env.bl', 'bl.lock',
                     'bin/bl-producer', 'bin/bl-stage-hosts', 'scripts/qualify-artifact-generation',
                     'scripts/check-source-floor', 'scripts/assemble-compiler-generations.py',
                     'scripts/check-produced-compiler.py', 'scripts/compiler-unit-baseline.py',
                     'scripts/demo-artifact-production', 'scripts/check-execution-history',
                     'test/scripts/artifact-generation.bl']
            for name in names:
                target = source / name
                target.parent.mkdir(parents=True, exist_ok=True)
                if (ROOT / name).is_dir():
                    shutil.copytree(ROOT / name, target)
                else:
                    shutil.copyfile(ROOT / name, target)

            def evaluate(previous=None):
                expression = '''let
                  lock = builtins.fromJSON (builtins.readFile %s);
                  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
                  sources = import %s { inherit (pkgs) lib; root = %s; };
                  product = import %s {
                    inherit pkgs; src = sources.compiler;
                    erlang = pkgs.emptyDirectory; elixir = pkgs.emptyDirectory;
                    dependencies = pkgs.emptyDirectory; checkoutPlatform = pkgs.emptyDirectory;
                    nativeProducts = { names = []; bundle = pkgs.emptyDirectory; };
                    previousCompiler = %s;
                  };
                in if builtins.isString product then { reused = product; }
                   else { output = product.outPath; command = product.buildCommand; }
                ''' % (json.dumps(str(ROOT / 'flake.lock')), str(ROOT / 'nix/producer-sources.nix'),
                       str(source), str(ROOT / 'nix/compiler-product.nix'),
                       'null' if previous is None else json.dumps(str(previous)))
                return json.loads(subprocess.check_output(
                    ['nix-instantiate', '--eval', '--strict', '--json', '--read-write-mode',
                     '--expr', expression, '--option', 'experimental-features', 'nix-command flakes'],
                    text=True, timeout=90))

            original = evaluate()
            metadata = json.loads(re.search(r'\{"identity":"[0-9a-f]{64}"[^\n]+', original['command'])[0])
            previous = base / 'retained-compiler'
            previous.mkdir()
            (previous / 'producer.json').write_text(json.dumps(metadata))
            self.assertEqual({'reused': str(previous)}, evaluate(previous))
            library = source / 'priv/lib/application.bl'
            library.parent.mkdir(parents=True)
            library.write_text('(ns application) (def value 42)\n')
            self.assertEqual(original, evaluate())
            self.assertEqual({'reused': str(previous)}, evaluate(previous))
            host = source / 'priv/host/env.bl'
            host.write_text(host.read_text() + '\n; changed host Source\n')
            changed = evaluate(previous)
            self.assertIn('output', changed)
            self.assertNotEqual(original['output'], changed['output'])


if __name__ == '__main__':
    unittest.main()
