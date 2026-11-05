#!/usr/bin/env python3
"""Serial checkout/SDK latency controls. Run on Build under a process-tree cap.

Both checkouts must already own their exact retained SDK selection. Placement
and credentials remain in the operator's Source-described backend. This probe
never changes either checkout's engine inputs and stops its private command VMs.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(directory):
    return {str(path.relative_to(directory)): digest(path)
            for path in directory.rglob('*') if path.is_file()}


def stop_owned(runtime):
    owned = []
    for process in Path('/proc').glob('[0-9]*'):
        try:
            if (f'XDG_RUNTIME_DIR={runtime}'.encode() + b'\0' in (process / 'environ').read_bytes()
                    and b'beam' in (process / 'cmdline').read_bytes().lower()):
                os.kill(int(process.name), signal.SIGTERM)
                owned.append(int(process.name))
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            pass
    deadline = time.monotonic() + 3
    while owned and time.monotonic() < deadline:
        owned = [pid for pid in owned if Path(f'/proc/{pid}').exists()]
        if owned:
            time.sleep(0.05)
    for pid in owned:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before-root', required=True, type=Path)
    parser.add_argument('--after-root', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--only', choices=('before', 'after'), help='measure one prepared revision')
    parser.add_argument('--trace', action='store_true', help='record warm-client syscall counts')
    args = parser.parse_args()
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {'version': 1, 'status': 'running', 'stages': [], 'variants': {}}
    base_env = {name: value for name, value in os.environ.items()
                if not name.startswith('BL_') and name not in ('ERL_FLAGS', 'ERL_AFLAGS', 'ERL_ZFLAGS',
                   'ERL_LIBS', 'BEAM_LISP_PATH', 'BEAM_LISP_DEV', 'ELIXIR_ERL_OPTIONS')}
    base_env['ELIXIR_ERL_OPTIONS'] = '+S 4:4 +SDcpu 2:2 +SDio 1:1'
    base_env['DBUS_SESSION_BUS_ADDRESS'] = os.environ.get('DBUS_SESSION_BUS_ADDRESS',
                                                        f'unix:path=/run/user/{os.getuid()}/bus')

    def save():
        (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')

    def run(name, argv, cwd, env, timeout=600):
        log = output / (name + '.log')
        usage = output / (name + '.usage.json')
        started = time.monotonic()
        with log.open('w') as stream:
            result = subprocess.run(['time', '-f', '{"max_rss_kib":%M,"user_seconds":%U,"system_seconds":%S}',
                                     '-o', str(usage), *map(str, argv)], cwd=cwd, env=env,
                                    stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
        row = dict(name=name, seconds=round(time.monotonic() - started, 6), exit=result.returncode,
                   **json.loads(usage.read_text().splitlines()[-1]))
        report['stages'].append(row)
        save()
        print(json.dumps(row), flush=True)
        if result.returncode:
            raise RuntimeError(f'{name} failed: {log}')
        return log.read_text()

    try:
        for variant, checkout in [('before', args.before_root.resolve()), ('after', args.after_root.resolve())]:
            if args.only and variant != args.only:
                continue
            launcher = checkout / 'bin/bl'
            project = output / (variant + '-project')
            project.mkdir()
            fixture = checkout / 'test/fixtures/artifact-production/artifact'
            shutil.copytree(fixture, project / 'src/artifact')
            (project / 'env.bl').write_text('{:paths ["src"] :build {:paths ["src"] :jobs 1}}\n')
            build = project / 'build'
            runtime_parent = os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')
            with tempfile.TemporaryDirectory(prefix='bl-latency-', dir=runtime_parent) as runtime:
                env = dict(base_env, XDG_RUNTIME_DIR=runtime)
                try:
                    run(variant + '-platform', [checkout / 'scripts/prepare-checkout-platform'], checkout, env)
                    selection = run(variant + '-selection', [checkout / 'scripts/prepare-checkout-sdk', '--selection'], checkout, env)
                    sdk = Path(selection.splitlines()[-1].split()[0])
                    metadata = json.loads((sdk / 'artifact.json').read_text())
                    assert (metadata['version'], metadata['kind']) == (1, 'sdk')
                    report['variants'][variant] = dict(sdk=str(sdk), metadata=metadata)
                    for repeat in range(3):
                        result = run(f'{variant}-cold-{repeat}', [launcher, '--cold', 'eval', '(+ 1 2)'], project, env)
                        assert '3' in result.splitlines(), result
                    owner_form = '(println (str "LATENCY-OWNER " (System/pid)))'
                    first = run(variant + '-warm-first', [launcher, 'eval', owner_form], project, env)
                    owner = re.search(r'LATENCY-OWNER (\d+)', first).group(1)
                    for repeat in range(3):
                        result = run(f'{variant}-warm-{repeat}', [launcher, 'eval', owner_form], project, env)
                        assert re.search(r'LATENCY-OWNER (\d+)', result).group(1) == owner
                    if args.trace:
                        result = run(variant + '-warm-syscalls', ['strace', '-f', '-c', '-o',
                            output / (variant + '-warm.strace'), launcher, 'eval', owner_form], project, env)
                        assert re.search(r'LATENCY-OWNER (\d+)', result).group(1) == owner
                    run(variant + '-build-first', [launcher, 'build', '--out', build], project, env)
                    product = (build / '.nix-product').resolve(strict=True)
                    assert json.loads((product / 'artifact.json').read_text())['sdk'] == str(sdk)
                    units = product / 'units/artifact.demo.values'
                    unchanged = inventory(units)
                    run(variant + '-build-unchanged', [launcher, 'build', '--out', build], project, env)
                    assert (build / '.nix-product').resolve(strict=True) == product
                    source = project / 'src/artifact/demo/consumer.bl'
                    source.write_text(source.read_text().replace('(values/define-answer answer)', '(defn answer [] 43)'))
                    run(variant + '-build-edit', [launcher, 'build', '--out', build], project, env)
                    edited = (build / '.nix-product').resolve(strict=True)
                    counts = json.loads((edited / 'result.json').read_text())
                    assert (counts['unit-compiled'], counts['unit-restored']) == (1, 1), counts
                    assert unchanged == inventory(edited / 'units/artifact.demo.values')
                    run(variant + '-build-fresh-unchanged', [launcher, '--cold', 'build', '--out', build], project, env)
                    assert (build / '.nix-product').resolve(strict=True) == edited
                    result = run(variant + '-after-edit-owner', [launcher, 'eval', owner_form], project, env)
                    assert re.search(r'LATENCY-OWNER (\d+)', result).group(1) == owner
                    status = Path('/proc') / owner / 'status'
                    memory = {name: int(value) for name, value in re.findall(r'^(VmRSS|VmHWM|VmSwap):\s+(\d+)', status.read_text(), re.M)}
                    report['variants'][variant].update(owner=int(owner), memory_kib=memory,
                        initial_product=str(product), edited_product=str(edited), edited_counts=counts,
                        unchanged_provider_files=len(unchanged))
                    if variant == 'after':
                        platform = Path(metadata['platform'])
                        checked = output / 'source-free-sdk'
                        run('source-free-sdk-integrity', ['python3', checkout / 'scripts/check-produced-sdk',
                            '--sdk', sdk, '--elixir', platform / 'bin/elixir', '--out', checked], project, env)
                        receiver_lib = checked / 'receiver-lib'
                        receiver_lib.mkdir()
                        image = receiver_lib / 'beam_lisp-0.1.0'
                        image.symlink_to(checked / 'image', target_is_directory=True)
                        receiver_env = dict(env, BL_APPLICATION_SDK=str(sdk), BL_APPLICATION_IMAGE=str(image),
                            BL_ROOT=str(image), BL_REQUIRE_SOURCE_FREE='1', BL_APPLICATION_EXPECT_ANSWER='43',
                            BL_APPLICATION_PRODUCT=str(edited), BL_SDK_PRODUCT=str(sdk))
                        text = run('edited-source-free-application', [platform / 'bin/elixir',
                            checkout / 'test/scripts/nix_application_receiver.exs'], image, receiver_env)
                        assert 'IMMUTABLE-MULTI answer=43' in text
                finally:
                    try:
                        run(variant + '-stop', [launcher, 'realm', 'stop'], project, env, timeout=90)
                    finally:
                        stop_owned(runtime)
        report['status'] = 'passed'
    except BaseException as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
