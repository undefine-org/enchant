"""Alternate fresh commands after qualification to check shared-host contention.

Use the same project, environment and scheduler settings for both immutable
SDKs. This compares checkout revisions, including their other runtime changes;
it is not a reader-cache-only causal startup experiment.
"""
import argparse
import json
import os
from pathlib import Path
import statistics
import subprocess
import tempfile
import time

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--before-root', type=Path, required=True)
p.add_argument('--after-root', type=Path, required=True)
p.add_argument('--project', type=Path, required=True)
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
a.out.mkdir(parents=True, exist_ok=False)
env = {k: v for k, v in os.environ.items() if not k.startswith('BL_')
       and k not in ('ERL_FLAGS', 'ERL_AFLAGS', 'ERL_ZFLAGS', 'ERL_LIBS', 'BEAM_LISP_PATH', 'BEAM_LISP_DEV')}
env['ELIXIR_ERL_OPTIONS'] = '+S 4:4 +SDcpu 2:2 +SDio 1:1'
report = {'status': 'running', 'scope': __doc__, 'runs': []}
with tempfile.TemporaryDirectory(prefix='bl-cold-controls-', dir=env.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) as runtime:
    env['XDG_RUNTIME_DIR'] = runtime
    for pair in range(3):
        for variant in (('before', 'after') if pair % 2 == 0 else ('after', 'before')):
            name = f'{pair}-{variant}'
            usage = a.out / f'{name}.usage.json'
            before = Path('/proc/loadavg').read_text().strip()
            started = time.monotonic()
            with (a.out / f'{name}.log').open('w') as log:
                result = subprocess.run(['time', '-f', '{"rss_kib":%M,"user_seconds":%U,"system_seconds":%S}',
                    '-o', str(usage), str(getattr(a, variant + '_root') / 'bin/bl'), '--cold', 'eval', '(+ 1 2)'],
                    cwd=a.project, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=90)
            row = {'pair': pair, 'variant': variant, 'wall_seconds': time.monotonic() - started,
                   'exit': result.returncode, 'load_before': before,
                   'load_after': Path('/proc/loadavg').read_text().strip(), **json.loads(usage.read_text())}
            report['runs'].append(row)
            (a.out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
            assert result.returncode == 0 and '3' in (a.out / f'{name}.log').read_text().splitlines()
            print(json.dumps(row), flush=True)
for variant in ('before', 'after'):
    report[variant] = {k: statistics.median(x[k] for x in report['runs'] if x['variant'] == variant)
                       for k in ('wall_seconds', 'rss_kib', 'user_seconds', 'system_seconds')}
report['status'] = 'passed'
(a.out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
