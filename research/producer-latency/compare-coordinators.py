#!/usr/bin/env python3
"""Compare already realized coordinator products, serially under a caller cap.

Unknown-command refusal loads the actual preparation program but creates no
job. Wrappers supply the same project cwd and their immutable runtime policy.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', required=True, type=Path)
    parser.add_argument('--after', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    products = {name: path.resolve(strict=True) for name, path in
                [('before', args.before), ('after', args.after)]}
    programs = {name: path / 'foundry/bin/preparation-operation.bl'
                for name, path in products.items()}
    contents = [path.read_bytes() for path in programs.values()]
    assert contents[0] == contents[1], 'compare the identical preparation program'
    report = dict(program_sha256=hashlib.sha256(contents[0]).hexdigest(),
                  products={name: str(path) for name, path in products.items()}, runs=[])
    for repeat in range(3):
        # Alternate order to expose a simple monotonic shared-host bias.
        for name in (['before', 'after'] if repeat % 2 == 0 else ['after', 'before']):
            label = f'{name}-{repeat}'
            usage = args.out / (label + '.usage.json')
            started = time.monotonic()
            result = subprocess.run(
                ['time', '-f', '{"max_rss_kib":%M,"user_seconds":%U,"system_seconds":%S}',
                 '-o', str(usage), str(products[name] / 'bin/bl'), '--cold', 'run',
                 str(programs[name]), '--', 'profile-refusal'],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
            elapsed = time.monotonic() - started
            (args.out / (label + '.stdout')).write_text(result.stdout)
            (args.out / (label + '.stderr')).write_text(result.stderr)
            assert result.returncode == 1, result
            assert json.loads(result.stdout) == {'ok': False, 'error': 'Unknown preparation command'}
            report['runs'].append(dict(variant=name, repeat=repeat, seconds=elapsed,
                **json.loads(usage.read_text().splitlines()[-1])))
            (args.out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
            print(json.dumps(report['runs'][-1]), flush=True)


if __name__ == '__main__':
    main()
