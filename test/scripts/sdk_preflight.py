#!/usr/bin/env python3
"""Prove source preflight reports independent failures with an existing SDK."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--sdk', type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='sdk-preflight-control-') as temporary:
    candidate = Path(temporary)
    # Preflight reads source as data; no compiler image or native binary copy
    # is needed to inspect another tree.
    for source in (root / 'priv').rglob('*'):
        if source.is_file() and source.name.endswith(('.bl', '.bl.md', '.bl.org')):
            target = candidate / source.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    additions = {
        'invalid': '(ns preflight.invalid',
        'native-consumer': '(ns preflight.native-consumer (:require [js.binary :as b]))',
        'cycle-a': '(ns preflight.cycle-a (:require [preflight.cycle-b]))',
        'cycle-b': '(ns preflight.cycle-b (:require [preflight.cycle-a]))',
    }
    for name, text in additions.items():
        (candidate / 'priv/std' / ('preflight-' + name + '.bl')).write_text(text)
    # The driver remains the exact repository command; --root selects only
    # candidate data. Copy its BL entry as required by the command's contract.
    (candidate / 'scripts').mkdir()
    shutil.copyfile(root / 'scripts/sdk-preflight.bl', candidate / 'scripts/sdk-preflight.bl')
    report_path = candidate / 'report.json'
    done = subprocess.run([root / 'scripts/sdk-preflight', '--sdk', args.sdk,
                           '--root', candidate, '--out', report_path], timeout=340)
    assert done.returncode == 1, done.returncode
    report = json.loads(report_path.read_text())
    assert len(report['source-errors']) == 1, report['source-errors']
    assert report['source-errors'][0]['file'] == 'std/preflight-invalid.bl'
    assert report['target-dependency-errors'] == [{
        'file': 'std/preflight-native-consumer.bl',
        'namespace': 'preflight.native-consumer', 'requires': 'js.binary'}]
    assert report['require-cycles'], report['require-cycles']
    assert not report['sources_changed_during_analysis']
    assert all('error' not in row for row in report['analyses'])
    print('SDK-PREFLIGHT-CONTROL passed: parse, target edge and cycle refusals')
