#!/usr/bin/env python3
"""Measure one real SDK edit and restore its exact isolated checkout afterward.

Run on Build under a cap, after the checkout's initial SDK is prepared. All
production goes through the normal Source-described preparation backend.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time


def inventory(directory):
    assert directory.is_dir(), directory
    files = {str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in directory.rglob('*') if path.is_file()}
    assert files, directory
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    root, output = args.root.resolve(strict=True), args.out.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = root / 'priv/std/errors.bl'
    original = source.read_bytes()
    report = dict(status='running', root=str(root), stages=[])

    def save():
        (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')

    def prepare(label):
        usage = output / (label + '.usage.json')
        started = time.monotonic()
        with (output / (label + '.log')).open('w') as log:
            result = subprocess.run(['time', '-f', '{"max_rss_kib":%M,"user_seconds":%U,"system_seconds":%S}',
                '-o', str(usage), str(root / 'scripts/prepare-checkout-sdk')], cwd=root,
                text=True, stdout=subprocess.PIPE, stderr=log, timeout=3600)
        report['stages'].append(dict(name=label, seconds=time.monotonic()-started,
            exit=result.returncode, **json.loads(usage.read_text().splitlines()[-1])))
        save()
        assert result.returncode == 0, f'{label}: see {output}'
        sdk = Path(result.stdout.strip()).resolve(strict=True)
        metadata = json.loads((sdk / 'artifact.json').read_text())
        assert (metadata['version'], metadata['kind']) == (1, 'sdk')
        report[label] = str(sdk)
        save()
        return sdk, metadata

    try:
        before, _ = prepare('unchanged')
        repeated, _ = prepare('unchanged-repeat')
        assert before == repeated
        source.write_bytes(original + b'\n; producer latency one-file edit control\n')
        edited, metadata = prepare('edit')
        assert edited != before
        deriver = subprocess.check_output(['nix-store', '-q', '--deriver', metadata['image']], text=True).strip()
        with (output / 'image.log').open('w') as log:
            subprocess.run(['nix-store', '-l', deriver], text=True, stdout=log, stderr=subprocess.STDOUT, check=True)
        report['phases'] = []
        seen = set()
        report['duplicate_phase_lines'] = 0
        for line in (output / 'image.log').read_text().splitlines():
            if line.startswith(('SDK-PHASE ', 'SDK-SHELL-PHASE ', 'SDK-UNIT-RESULT ',
                                'SDK-UNIT-PHASES ', 'SDK-PARTS-RESULT ', 'SDK-IMAGE-RESULT ')):
                # The bounded worker's exit trap replays its debug stream.
                if line in seen:
                    report['duplicate_phase_lines'] += 1
                    continue
                seen.add(line)
                label, value = line.split(' ', 1)
                report['phases'].append(dict(kind=label, value=json.loads(value)))
        prior = json.loads((before / 'unit-store/unit-index.json').read_text())
        current = json.loads((edited / 'unit-store/unit-index.json').read_text())
        assert prior['compiler'] == current['compiler']
        assert prior['runtime'] == current['runtime']
        assert prior['units'].keys() == current['units'].keys()
        unchanged = [name for name, row in current['units'].items() if prior['units'][name] == row]
        assert unchanged
        for name in unchanged:
            assert inventory(before / 'unit-store/.units' / name) == inventory(edited / 'unit-store/.units' / name), name
        report.update(units=len(current['units']), identical_unchanged_units=len(unchanged),
                      changed_units=sorted(set(current['units'])-set(unchanged)))
        report['status'] = 'passed'
    except BaseException as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        source.write_bytes(original)
        restored, _ = prepare('restore')
        assert str(restored) == report.get('unchanged'), 'restore must select the original SDK'
        report['source_restored_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
        save()


if __name__ == '__main__':
    main()
