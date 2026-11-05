"""Alternate unchanged public builds on already-qualified projects and SDKs."""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time

parser = argparse.ArgumentParser(description=__doc__)
for name in ('before_root', 'after_root', 'before_project', 'after_project', 'out'):
    parser.add_argument('--'+name.replace('_', '-'), required=True, type=Path)
args = parser.parse_args()
args.out.mkdir(parents=True, exist_ok=False)
report = {'status': 'running', 'runs': [], 'memory_kib': {}}
env = {k: v for k, v in os.environ.items() if not k.startswith('BL_') and k not in
       ('ERL_FLAGS', 'ERL_AFLAGS', 'ERL_ZFLAGS', 'ERL_LIBS', 'BEAM_LISP_PATH',
        'BEAM_LISP_DEV', 'ELIXIR_ERL_OPTIONS')}
env['ELIXIR_ERL_OPTIONS'] = '+S 4:4 +SDcpu 2:2 +SDio 1:1'
env['DBUS_SESSION_BUS_ADDRESS'] = os.environ.get('DBUS_SESSION_BUS_ADDRESS',
                                               f'unix:path=/run/user/{os.getuid()}/bus')
variants = {}


def save():
    (args.out / 'result.json').write_text(json.dumps(report, indent=2)+'\n')


def run(label, variant, argv):
    root, project, runtime, expected = variants[variant]
    started = time.monotonic()
    done = subprocess.run([str(root/'bin/bl'), *argv], cwd=project,
        env=dict(env, XDG_RUNTIME_DIR=runtime), text=True, capture_output=True, timeout=180)
    row = dict(stage=label, variant=variant, seconds=time.monotonic()-started, exit=done.returncode)
    report['runs'].append(row)
    (args.out / f'{variant}-{label}.log').write_text(done.stdout+done.stderr)
    save()
    assert done.returncode == 0, done.stderr
    assert (project/'build/.nix-product').resolve(strict=True) == expected
    print(json.dumps(row), flush=True)
    return done.stdout


def owned(runtime):
    found = []
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            command = (proc/'cmdline').read_bytes().split(b'\0', 1)[0]
            if (Path(os.fsdecode(command)).name in ('beam', 'beam.smp') and
                f'XDG_RUNTIME_DIR={runtime}'.encode()+b'\0' in (proc/'environ').read_bytes()):
                found.append(int(proc.name))
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            pass
    return found


with tempfile.TemporaryDirectory(prefix='bl-fixed-warm-') as scratch:
    try:
        for variant in ('before', 'after'):
            root = getattr(args, variant+'_root').resolve(strict=True)
            project = getattr(args, variant+'_project').resolve(strict=True)
            runtime = str(Path(scratch)/variant)
            Path(runtime).mkdir(mode=0o700)
            variants[variant] = root, project, runtime, (project/'build/.nix-product').resolve(strict=True)
            text = run('owner', variant, ['eval', '(println (str "WARM-BUILD-OWNER " (System/pid)))'])
            pid = int(re.search(r'WARM-BUILD-OWNER (\d+)', text).group(1))
            report[variant+'_owner'] = pid
            run('prime', variant, ['build', '--out', str(project/'build')])
        for repeat in range(3):
            for variant in ('before', 'after'):
                run(f'unchanged-{repeat}', variant, ['build', '--out', str(variants[variant][1]/'build')])
        for repeat in range(3):
            for variant in ('before', 'after'):
                run(f'fresh-unchanged-{repeat}', variant,
                    ['--cold', 'build', '--out', str(variants[variant][1]/'build')])
        for variant in variants:
            status = Path('/proc')/str(report[variant+'_owner'])/'status'
            report['memory_kib'][variant] = {k: int(v) for k, v in re.findall(
                r'^(VmRSS|VmHWM|VmSwap):\s+(\d+)', status.read_text(), re.M)}
        report['status'] = 'passed'
    finally:
        cleanup_errors = []
        for variant, (_, _, runtime, _) in variants.items():
            try:
                run('stop', variant, ['realm', 'stop'])
            except Exception as error:
                cleanup_errors.append(str(error))
            finally:
                for pid in owned(runtime):
                    os.kill(pid, signal.SIGTERM)
                deadline = time.monotonic()+3
                while owned(runtime) and time.monotonic() < deadline:
                    time.sleep(.05)
                for pid in owned(runtime):
                    os.kill(pid, signal.SIGKILL)
        if cleanup_errors:
            report.update(status='cleanup-failed', cleanup_errors=cleanup_errors)
        save()
        assert not cleanup_errors, cleanup_errors
