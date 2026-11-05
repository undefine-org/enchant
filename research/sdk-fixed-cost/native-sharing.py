"""Compare exact native derivations with one pinned package set per evaluation."""
import json
from pathlib import Path
import subprocess
import time

root = Path.cwd()
out = root / '.local/fixed-cost'
variant = out / 'native-shared'
variant.mkdir(exist_ok=True)
archive = subprocess.Popen(['git', 'archive', 'HEAD'], stdout=subprocess.PIPE)
subprocess.run(['tar', '-x', '-C', str(variant)], stdin=archive.stdout, check=True)
archive.stdout.close()
assert archive.wait() == 0
p = variant / 'nix/native-artifact.nix'
s = p.read_text().replace('{ requestJson }:', '{ requestJson, packages ? null }:')
s = s.replace('  pkgs = import nixpkgs.outPath', '  pkgs = if packages != null then packages else import nixpkgs.outPath')
p.write_text(s)
p = variant / 'nix/native-products.nix'
s = p.read_text().replace('value = import ./native-artifact.nix {', 'value = import ./native-artifact.nix {\n      packages = pkgs;')
p.write_text(s)
expr = out / 'native-products-probe.nix'
expr.write_text('''{ root, sourceRoot }:
let
  lock = builtins.fromJSON (builtins.readFile (root + "/flake.lock"));
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
  native = import (root + "/nix/native-products.nix") { inherit pkgs; root = /. + sourceRoot; includeDesktop = true; };
in builtins.mapAttrs (_: product: { output = product.outPath; derivation = product.drvPath; }) native.products
''')
report = {'runs': []}
expected = None
for repeat in range(3):
    for label, tree in [('before', root), ('shared', variant)]:
        started = time.monotonic()
        usage = out / f'native-{label}-{repeat}.usage'
        result = subprocess.run(['time', '-f', '%M', '-o', str(usage),
            'nix-instantiate', '--eval', '--strict', '--json', str(expr),
            '--argstr', 'root', str(tree), '--argstr', 'sourceRoot', str(root), '--option', 'allow-import-from-derivation', 'false',
            '--option', 'max-jobs', '0', '--extra-experimental-features', 'nix-command flakes'],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert result.returncode == 0, result.stderr
        products = json.loads(result.stdout)
        if expected is None:
            expected = products
        assert products == expected, (label, products, expected)
        row = dict(variant=label, repeat=repeat, seconds=time.monotonic()-started,
                   max_rss_kib=int(usage.read_text().strip()), products=products)
        report['runs'].append(row)
        (out / 'native-sharing.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(row), flush=True)
