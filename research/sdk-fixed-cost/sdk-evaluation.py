"""Fresh strict SDK recipe evaluations; run serially on Build under a cap."""
import argparse
import json
from pathlib import Path
import subprocess
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--before-engine', required=True)
parser.add_argument('--after-engine', required=True)
parser.add_argument('--previous', required=True)
parser.add_argument('--out', required=True, type=Path)
args = parser.parse_args()
args.out.mkdir(parents=True, exist_ok=False)
expression = args.out / 'select.nix'
expression.write_text('''{ source, previous }:
let product = import (source + "/nix/sdk-artifact.nix") { inherit source previous; };
in { output = product.outPath; derivation = product.drvPath; }
''')
report = {'runs': []}
expected = {}
for repeat in range(3):
    for label, engine in [('before', args.before_engine), ('after', args.after_engine)]:
        usage = args.out / f'{label}-{repeat}.usage'
        started = time.monotonic()
        result = subprocess.run(['time', '-f', '%M', '-o', str(usage),
            'nix-instantiate', '--eval', '--strict', '--json', str(expression),
            '--argstr', 'source', engine, '--argstr', 'previous', args.previous,
            '--option', 'allow-import-from-derivation', 'false', '--option', 'max-jobs', '0',
            '--extra-experimental-features', 'nix-command flakes'], text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert result.returncode == 0, result.stderr
        selection = json.loads(result.stdout)
        if label not in expected:
            expected[label] = selection
        assert selection == expected[label], (label, selection, expected[label])
        row = dict(variant=label, repeat=repeat, seconds=time.monotonic()-started,
                   max_rss_kib=int(usage.read_text().strip()), selection=selection)
        report['runs'].append(row)
        (args.out / 'result.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(row), flush=True)
