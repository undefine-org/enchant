#!/usr/bin/env python3
"""Three fresh actual SDK receivers test image-aware first initialization.

Run under one process-tree cap. No compiler or SDK product is emitted. The
receivers use the live Loader, an unchanged private copy, and the historical
Source-only recognition predicate. Retained product bytes must stay identical.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time


BOOT = '''root = System.fetch_env!("BL_ROOT")
library = Path.join(Path.dirname(root), "sdk-runtime-lib/beam_lisp-0.1.0")
File.mkdir_p!(Path.dirname(library))
case File.ln_s(root, library) do
  :ok -> :ok
  {:error, :eexist} -> {:ok, ^root} = File.read_link(library)
end
true = Code.prepend_path(Path.join(library, "ebin"))
Application.load(:beam_lisp)
for app <- Application.spec(:beam_lisp, :applications) || [], do: {:ok, _} = Application.ensure_all_started(app)
:ok = BeamLisp.LazyMemo.ensure_loaded!()
BeamLisp.AOT.boot()
BeamLisp.run_file(hd(System.argv()))
'''


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    root, sdk, out = args.root.resolve(), args.sdk.resolve(), args.out.absolute()
    out.mkdir(parents=True, exist_ok=False)
    image = out / 'image'
    started = time.monotonic()
    shutil.copytree(sdk / 'image', image, symlinks=True)
    # Only owned directories become writable, to prune Source. Retained regular
    # file bytes remain identical to the immutable product throughout execution.
    directories = [image, *(p for p in image.rglob('*') if p.is_dir() and not p.is_symlink())]
    for directory in directories:
        directory.chmod(directory.stat().st_mode | 0o200)
    removed, retained = {}, {}
    for path in sorted(image.rglob('*')):
        if path.is_file() and not path.is_symlink():
            relative = str(path.relative_to(image))
            if relative.startswith('priv/') and path.name.endswith(('.bl', '.bl.md', '.bl.org')):
                removed[relative] = sha(path)
                path.unlink()
            else:
                retained[relative] = sha(path)
                assert retained[relative] == sha(sdk / 'image' / relative)
    fixture = root / 'test/fixtures/sdk_sealed_loading_context_control.bl'
    report = {
        'scope': 'actual immutable Nix SDK; copied receiver removes only SDK Source',
        'sdk': str(sdk), 'sdk_descriptor_sha256': sha(sdk / 'artifact.json'),
        'fixture_sha256': sha(fixture), 'removed': removed, 'retained': retained,
        'preparation_seconds': round(time.monotonic() - started, 3),
        'passed': False, 'receivers': [],
    }
    (out / 'inputs.json').write_text(json.dumps(report, indent=2) + '\n')
    product = json.loads((sdk / 'artifact.json').read_text())
    platform = Path(product['platform'])
    (out / 'boot.exs').write_text(BOOT)
    command = [str(platform / 'bin/elixir')]
    for dependency in sorted((sdk / 'lib').glob('*/ebin')):
        if not dependency.parent.name.startswith('beam_lisp-'):
            command += ['-pa', str(dependency)]
    command += ['-pa', str(image / 'ebin'), str(out / 'boot.exs'), str(fixture)]
    environment = {
        **os.environ, 'BL_ROOT': str(image), 'BL_DAEMON': 'off', 'BEAM_LISP_PATH': '',
        'BL_TEST_TIMES': '1', 'BL_TEST_SOURCE_ROOT': str(root),
        'ELIXIR_ERL_OPTIONS': '+S 4:4 +SDcpu 2:2 +SDio 1:1',
        'PATH': str(platform / 'bin') + ':' + os.environ['PATH'],
    }
    modes = [
        ('original', 'SDK_SEALED_LOADING_CONTEXT_READY'),
        ('copied-original', 'SDK_SEALED_LOADING_CONTEXT_COPIED_ORIGINAL_READY'),
        ('source-only-redirect', 'SDK_SEALED_LOADING_CONTEXT_SOURCE_ONLY_CONTROL_CAUGHT'),
    ]
    for mode, marker in modes:
        child_env = {**environment, 'BL_TEST_SDK_SEALED_LOADING_CONTROL': mode,
                     'XDG_CACHE_HOME': str(out / ('cache-' + mode))}
        started = time.monotonic()
        result = subprocess.run(command, cwd=image, env=child_env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
        (out / (mode + '.log')).write_text(result.stdout)
        print(mode, result.stdout, flush=True)
        row = {'mode': mode, 'execution_seconds': round(time.monotonic() - started, 3),
               'exit': result.returncode, 'passed': result.returncode == 0 and marker in result.stdout}
        report['receivers'].append(row)
        report['retained_byte_identical_after'] = all(
            sha(image / path) == digest == sha(sdk / 'image' / path)
            for path, digest in retained.items())
        report['fixture_unchanged'] = sha(fixture) == report['fixture_sha256']
        report['passed'] = (len(report['receivers']) == len(modes)
                            and all(receiver['passed'] for receiver in report['receivers'])
                            and report['retained_byte_identical_after'] and report['fixture_unchanged'])
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        if not row['passed']:
            break
    assert report['passed']
    print('SDK_SEALED_INITIALIZATION_CONTROLS_READY', flush=True)


if __name__ == '__main__':
    main()
