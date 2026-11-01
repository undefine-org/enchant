#!/usr/bin/env python3
"""Check the read-only combined selector against real immutable products.

Run under a process-tree memory cap. This control evaluates recipes and retains
existing outputs; it never realizes a producer or runs a BEAM VM.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--product', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    sdk, product, out = args.sdk.resolve(strict=True), args.product.resolve(strict=True), args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    request = json.loads((product / 'production-request.json').read_text())
    source = out / 'project'
    shutil.copytree(request['source'], source)
    for path in (source, *source.rglob('*')):
        path.chmod(path.stat().st_mode | 0o200)
    report = {'status': 'running', 'sdk': str(sdk), 'base': str(product), 'stages': []}

    def evaluate(name, recipe, values, succeeds=True):
        command = ['nix-instantiate', '--eval', '--strict', '--json', str(recipe),
                   '--option', 'experimental-features', 'nix-command flakes',
                   '--option', 'allow-import-from-derivation', 'false', '--option', 'max-jobs', '0']
        for key, value in values.items():
            command.extend(['--argstr', key, value])
        start = time.monotonic()
        done = subprocess.run(command, text=True, capture_output=True, timeout=90)
        (out / (name + '.log')).write_text(done.stdout + done.stderr)
        report['stages'].append({'name': name, 'seconds': round(time.monotonic() - start, 3), 'exit': done.returncode})
        assert (done.returncode == 0) == succeeds, done.stderr
        return json.loads(done.stdout) if succeeds else None

    try:
        values = {'source': str(source), 'rootsJson': json.dumps(sorted(p.name for p in source.iterdir())),
                  'sdk': str(sdk), 'requestJson': json.dumps(dict(request, base=str(product)))}
        expected = evaluate('separate-selector', ROOT / 'nix/artifact-selection.nix',
                            {'kind': 'application', 'sdk': str(sdk), 'requestJson': values['requestJson']})
        selected = evaluate('combined-selector', ROOT / 'nix/application-selection.nix', values)
        assert selected['source'] == request['source'], selected
        assert {k: selected[k] for k in ('output', 'derivation')} == expected, (selected, expected)
        assert Path(selected['output']).is_dir(), 'the supplied product must match the current producer'
        subprocess.run(['nix-store', '--add-root', str(out / 'retained-source'), '--indirect',
                        '--realise', selected['source']], check=True, capture_output=True, timeout=30)
        assert (out / 'retained-source').resolve(strict=True) == Path(request['source'])
        forced = evaluate('force', ROOT / 'nix/application-selection.nix',
                          dict(values, requestJson=json.dumps(dict(request, force=True, attempt='1' * 64))))
        assert forced == {'source': request['source'], 'output': None, 'derivation': None}, forced
        declaration = source / 'env.bl'
        declaration.write_text(declaration.read_text() + '\n;; read-only missing-snapshot selection control\n')
        changed = evaluate('changed-source', ROOT / 'nix/application-selection.nix', values)
        assert changed['source'] != request['source'] and changed['output'] is None, changed
        assert not Path(changed['source']).exists(), 'read-only selection realized a source snapshot'
        (source / 'forbidden-link').symlink_to(source / 'env.bl')
        evaluate('symlink-refusal', ROOT / 'nix/application-selection.nix',
                 dict(values, rootsJson=json.dumps(['env.bl', 'forbidden-link'])), succeeds=False)
        report.update(status='passed', selected=selected, changed=changed)
    except BaseException as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
