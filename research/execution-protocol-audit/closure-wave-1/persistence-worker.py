#!/usr/bin/env python3
"""Check existing portable bytes and the six genuine persistent-unit phases."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

root = Path.cwd()
sdk = Path(os.environ['CLOSURE_PROOF_SDK'])
out = Path(os.environ['CLOSURE_PROOF_OUTPUT'])
metadata = json.loads((sdk / 'artifact.json').read_text())
projection = out / 'projection'
projection.mkdir()
subprocess.run([sys.executable, str(root / 'scripts/ci-materialize-candidate.py'),
                '--root', str(projection), '--sdk', str(sdk),
                '--candidate', str(Path(metadata['release']) / 'bl.drop')], check=True)
result = subprocess.run([sys.executable, str(root / 'test/scripts/sdk_build_persistence.py'),
                         '--image', str(projection / '.bl/ci-image'),
                         '--work-dir', str(out / 'persistence')],
                        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=1200)
(out / 'persistence.log').write_text(result.stdout)
print(result.stdout, end='', flush=True)
if result.returncode:
    raise SystemExit(result.returncode)
metrics = [json.loads(row) for row in re.findall(r'^SDK-BUILD-PROBE (.+)$', result.stdout, re.M)]
assert [row['phase'] for row in metrics] == ['first', 'unchanged', 'restore', 'changed', 'corrupt', 'contended']
(out / 'persistence-result.json').write_text(json.dumps({'status': 'passed', 'phases': metrics}, indent=2) + '\n')
