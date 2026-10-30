#!/usr/bin/env python3
"""Qualify the production native recipe with a real Rust body mutation."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workspace', action='store_true', help='also check a local path dependency and support input')
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = output / 'source'
    shutil.copytree(repo / 'native/bl_json', source,
                    ignore=shutil.ignore_patterns('target', '.git', '.bl'))
    nonce = uuid.uuid4().hex
    with (source / 'src/lib.rs').open('a') as stream:
        stream.write('\n// independent reuse control ' + nonce + '\n')
    request = dict(version=1, source=str(source), crate='bl_json',
                   abi='native-dependency-reuse-control', target='x86_64-linux')
    report = {'stages': [], 'status': 'running', 'fresh_source_control': nonce}

    def build(name):
        command = ['nix-build', str(repo / 'nix/native-artifact.nix'), '--argstr',
                   'requestJson', json.dumps(request), '--out-link', str(output / name),
                   '--max-jobs', '0', '--option', 'experimental-features', 'nix-command flakes']
        started = time.monotonic()
        with (output / (name + '.log')).open('w') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=600)
        product = (output / name).resolve(strict=True)
        metadata = json.loads((product / 'artifact.json').read_text())
        drv = subprocess.check_output(['nix-store', '--query', '--deriver', metadata['compiled']], text=True).strip()
        inputs = subprocess.check_output(['nix-store', '--query', '--references', drv], text=True).splitlines()
        caches = [path for path in inputs if '-bl-native-dependencies-' in path]
        assert len(caches) == 1, caches
        report['stages'].append(dict(name=name, product=str(product), dependency_cache=caches[0],
                                     seconds=round(time.monotonic() - started, 3)))
        return product, caches[0]

    def receive(product, loaded):
        script = output / 'receiver.exs'
        script.write_text('''defmodule BeamLisp.Native.Bl.JsonNative do
  def __nif_loaded__, do: :erlang.nif_error(:not_loaded)
  def json_encode(_), do: :erlang.nif_error(:not_loaded)
  def json_decode(_, _), do: :erlang.nif_error(:not_loaded)
  def json_count(_), do: :erlang.nif_error(:not_loaded)
  def load, do: :erlang.load_nif(String.to_charlist(System.fetch_env!("CONTROL_NIF")), 0)
end
:ok = BeamLisp.Native.Bl.JsonNative.load()
expected = System.fetch_env!("CONTROL_LOADED") == "true"
^expected = BeamLisp.Native.Bl.JsonNative.__nif_loaded__()
"[1,2]" = BeamLisp.Native.Bl.JsonNative.json_encode([1,2])
IO.puts("NATIVE-RECEIVER passed")
''')
        env = dict(os.environ, CONTROL_NIF=str(product / 'lib/bl_json'), CONTROL_LOADED=str(loaded).lower(),
                   ELIXIR_ERL_OPTIONS='+S 2:2 +SDcpu 1:1 +SDio 1:1')
        subprocess.run(['elixir', str(script)], env=env, check=True, timeout=30)

    try:
        original, cache = build('original')
        receive(original, True)
        body = source / 'src/lib.rs'
        before = body.read_text()
        needle = 'fn __nif_loaded__() -> bool {\n    true\n}'
        assert needle in before
        body.write_text(before.replace(needle, needle.replace('true', 'false'), 1))
        changed, changed_cache = build('changed')
        assert cache == changed_cache, 'Rust body mutation recompiled Cargo dependencies'
        assert original != changed
        log = (output / 'changed.log').read_text()
        compiled = [line.strip() for line in log.splitlines() if line.strip().startswith('Compiling ')]
        assert compiled and all(line.startswith('Compiling bl_json ') for line in compiled), compiled
        receive(changed, False)
        if args.workspace:
            workspace = output / 'workspace'
            shutil.copytree(repo / 'examples/artifacts/workspace/rust', workspace,
                            ignore=shutil.ignore_patterns('target', '.git', '.bl'))
            request = dict(version=2, source=str(workspace), member='crates/engine',
                           package='artifact-workspace-engine', crate='workspace_demo',
                           abi='workspace-dependency-reuse-control', target='x86_64-linux')
            with (workspace / 'crates/engine/src/lib.rs').open('a') as stream:
                stream.write('\n// independent reuse control ' + nonce + '\n')

            def workspace_receive(product, answer):
                script = output / 'workspace-receiver.exs'
                script.write_text('''defmodule BeamLisp.Native.Artifact.Workspace do
  def answer, do: :erlang.nif_error(:not_loaded)
  def support_message, do: :erlang.nif_error(:not_loaded)
  def load, do: :erlang.load_nif(String.to_charlist(System.fetch_env!("CONTROL_NIF")), 0)
end
:ok = BeamLisp.Native.Artifact.Workspace.load()
expected = String.to_integer(System.fetch_env!("CONTROL_ANSWER"))
^expected = BeamLisp.Native.Artifact.Workspace.answer()
"workspace support is captured" = BeamLisp.Native.Artifact.Workspace.support_message()
IO.puts("WORKSPACE-RECEIVER passed")
''')
                env = dict(os.environ, CONTROL_NIF=str(product / 'lib/workspace_demo'), CONTROL_ANSWER=str(answer),
                           ELIXIR_ERL_OPTIONS='+S 2:2 +SDcpu 1:1 +SDio 1:1')
                subprocess.run(['elixir', str(script)], env=env, check=True, timeout=30)

            original, cache = build('workspace-original')
            workspace_receive(original, 42)
            body = workspace / 'crates/engine/src/lib.rs'
            body.write_text(body.read_text().replace('workspace_support::answer()', 'workspace_support::answer() + 1'))
            changed, changed_cache = build('workspace-body')
            assert changed_cache == cache
            compiled = [line.strip() for line in (output / 'workspace-body.log').read_text().splitlines()
                        if line.strip().startswith('Compiling ')]
            assert compiled and all(line.startswith('Compiling artifact-workspace-engine ') for line in compiled), compiled
            workspace_receive(changed, 43)
            (workspace / 'support/answer.txt').write_text('44\n')
            support, support_cache = build('workspace-support')
            assert support_cache != cache
            workspace_receive(support, 45)
        report['status'] = 'passed'
    finally:
        (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
