"""Retain timings, sampled stacks and exact output inventories from a probe."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('log', type=Path)
parser.add_argument('units', type=Path)
parser.add_argument('out', type=Path)
args = parser.parse_args()
report = {'samples': [], 'calls': []}
for line in args.log.read_text().splitlines():
    if line.startswith('RESTORE-RESULT '): report.update(json.loads(line.split(' ',1)[1]))
    elif line.startswith('SDK-UNIT-PHASES '): report['phases'] = json.loads(line.split(' ',1)[1])
    elif line.startswith('RESTORE-SAMPLES '): report.update(json.loads(line.split(' ',1)[1]))
    elif line.startswith('RESTORE-SAMPLE '): report['samples'].append(json.loads(line.split(' ',1)[1]))
    elif line.startswith('RESTORE-CALL '): report['calls'].append(json.loads(line.split(' ',1)[1]))
assert report['compiled'] == 0 and report['cached'] > 500
files = {str(p.relative_to(args.units)): hashlib.sha256(p.read_bytes()).hexdigest()
         for p in args.units.rglob('*') if p.is_file()}
assert files
encoded = json.dumps(files, sort_keys=True, separators=(',', ':')).encode()
report.update(files=len(files), output_inventory_sha256=hashlib.sha256(encoded).hexdigest())
match = re.search(r'Maximum resident set size \(kbytes\): (\d+)', args.log.read_text())
if match: report['max_rss_kib'] = int(match.group(1))
args.out.write_text(json.dumps(report, indent=2)+'\n')
args.out.with_suffix('.files.json').write_text(json.dumps(files, sort_keys=True)+'\n')
shutil.rmtree(args.units)
