#!/usr/bin/env python3
"""Sequential consumers of one genuine immutable SDK. Run under a process-tree cap.

The output must not exist. Retains project copies, receipts and per-stage
logs; no checkout source or installed output is modified. Preparation jobs may
outlive a timed-out caller and retain their own roots for later inspection.
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
import sys
import time


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=1200, help='seconds per subprocess stage')
    args = parser.parse_args()
    if not 1 <= args.timeout <= 7200:
        parser.error('--timeout must be between 1 and 7200 seconds')
    repo = Path(__file__).resolve().parents[2]
    sdk, output = args.sdk.resolve(strict=True), args.output.resolve()
    if not re.fullmatch(r'/nix/store/[0-9a-z]{32}-[^/]+', str(sdk)):
        parser.error('--sdk must resolve to a top-level immutable store product')
    metadata = json.loads((sdk / 'artifact.json').read_text())
    assert (metadata['version'], metadata['kind'], metadata['target']) == (1, 'sdk', 'x86_64-linux')
    coordinator = (sdk / 'preparation-coordinator').resolve(strict=True)
    assert metadata['coordinator'] == str(coordinator)
    platform = Path(json.loads((coordinator / 'artifact.json').read_text())['platform'])
    assert re.fullmatch(r'/nix/store/[0-9a-z]{32}-[^/]+', str(platform))
    launcher, elixir = sdk / 'bin/bl', platform / 'bin/elixir'
    assert launcher.is_file() and elixir.is_file()
    output.mkdir(parents=True, exist_ok=False)
    (output / 'logs').mkdir()
    report = {'version': 1, 'scope': 'exact-sdk-sequential-normal-consumers', 'sdk': str(sdk),
              'sdk_descriptor_sha256': digest(sdk / 'artifact.json'), 'coordinator': str(coordinator),
              'platform': str(platform), 'driver_sha256': digest(Path(__file__)),
              'status': 'running', 'stages': [], 'products': {},
              'limitations': ['Selected consumer controls only; original execution checklist remains authoritative.',
                              'No automatic live-consumer GC or deployment qualification.',
                              'Timeout cleanup stops only this harness process group; durable preparation jobs retain their own lifecycle.']}
    base_env = {k: v for k, v in os.environ.items()
                if not k.startswith('BL_') and k not in ('BEAM_LISP_PATH', 'BEAM_LISP_DEV', 'BEAM_LISP_AOT_CACHE_DIR', 'ERL_LIBS', 'ERL_FLAGS', 'ERL_AFLAGS', 'ERL_ZFLAGS', 'BEAM_LISP_CODE_PATH', 'ELIXIR_ERL_OPTIONS')}
    base_env.update(PATH=str(platform / 'bin') + os.pathsep + base_env.get('PATH', ''),
                    ELIXIR_ERL_OPTIONS='+S 4:4 +SDcpu 2:2 +SDio 1:1')

    def save():
        (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')

    def run(name, command, cwd, env=None, marker=None):
        log = output / 'logs' / (name + '.log')
        stage = {'name': name, 'argv': list(map(str, command)), 'cwd': str(cwd), 'log': str(log), 'status': 'running'}
        report['stages'].append(stage)
        save()
        started = time.monotonic()
        child_env = dict(base_env, XDG_CACHE_HOME=str(output / 'cache' / name), BL_DAEMON='off')
        child_env.update({k: str(v) for k, v in (env or {}).items()})
        print(name, flush=True)
        try:
            with log.open('wb') as stream:
                process = subprocess.Popen(list(map(str, command)), cwd=cwd, env=child_env,
                                           stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
                try:
                    code = process.wait(timeout=args.timeout)
                except BaseException:
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        process.wait()
                    raise
            stage['exit'] = code
            if code:
                raise RuntimeError(f'{name} exited {code}; see {log}')
            if marker is not None and marker not in log.read_text(errors='replace'):
                raise RuntimeError(f'{name} did not emit expected marker {marker!r}; see {log}')
            stage['status'] = 'passed'
        except BaseException as error:
            stage.update(status='failed', error=str(error))
            raise
        finally:
            stage['seconds'] = round(time.monotonic() - started, 3)
            save()

    def bl(name, arguments, cwd, env=None, marker=None):
        run(name, [launcher, '--cold', *arguments], cwd, env, marker)

    scripts = repo / 'test/scripts'
    project = output / 'application-project'
    project.mkdir()
    shutil.copytree(repo / 'test/fixtures/artifact-production/artifact', project / 'src/artifact')
    (project / 'env.bl').write_text('{:paths ["src"] :build {:paths ["src"] :jobs 1}}\n')
    try:
        ordinary = output / 'ordinary'
        bl('ordinary-cli', ['build', '--out', str(ordinary)], project)
        ordinary_product = (ordinary / '.nix-product').resolve(strict=True)
        report['products']['ordinary'] = str(ordinary_product)
        assert json.loads((ordinary_product / 'artifact.json').read_text())['sdk'] == str(sdk)
        assert len(json.loads((ordinary_product / 'result.json').read_text())['units']) == 2

        # The checker makes a private source-free SDK image and restores both
        # mutation victims in its finally block. Its image is reused below.
        checked = output / 'sdk-integrity'
        run('source-free-sdk-integrity', [sys.executable, repo / 'scripts/check-produced-sdk',
                                        '--sdk', sdk, '--elixir', elixir, '--out', checked], output)
        assert json.loads((checked / 'result.json').read_text())['status'] == 'passed'
        # Standard OTP app layout keeps priv_dir bound to this verified image
        # while the native application's receiver runs from its own project cwd.
        receiver_lib = checked / 'receiver-lib'
        receiver_lib.mkdir()
        image = receiver_lib / 'beam_lisp-0.1.0'
        image.symlink_to(checked / 'image', target_is_directory=True)
        receiver_env = {'BL_APPLICATION_SDK': sdk, 'BL_APPLICATION_IMAGE': image, 'BL_ROOT': image,
                        'BL_REQUIRE_SOURCE_FREE': '1', 'BL_ARTIFACT_PLATFORM': platform / 'artifact-platform',
                        'BL_PREPARATION_COORDINATOR': coordinator, 'BL_SDK_PRODUCT': sdk}
        run('ordinary-source-free-receiver', [elixir, scripts / 'nix_application_receiver.exs'], image,
            dict(receiver_env, BL_APPLICATION_PRODUCT=ordinary_product), 'IMMUTABLE-MULTI answer=42')
        bl('java-oracle', ['test', str(repo / 'test/bl/java_oracle_port_test.bl')], output)

        bl('ordinary-cli-unchanged', ['build', '--out', str(ordinary)], project)
        assert (ordinary / '.nix-product').resolve(strict=True) == ordinary_product
        receipts = list((output / 'cache/ordinary-cli-unchanged/beam_lisp/artifacts').glob('application-*/receipt.json'))
        assert len(receipts) == 1, receipts
        cached = json.loads(receipts[0].read_text())
        assert cached['cached?'] is True and cached['job'] is None, cached
        assert not (receipts[0].parent / 'job').exists(), 'cache hit started a durable worker'
        assert Path(cached['retention-root']).resolve(strict=True) == ordinary_product
        unrelated = project / 'src/artifact/demo/unrelated.bl'
        unrelated.write_text('(ns artifact.demo.unrelated) (defn answer [] 7)\n')
        values = project / 'src/artifact/demo/values.bl'
        original_values = values.read_text()
        try:
            bl('ordinary-cli-added', ['build', '--out', str(ordinary)], project)
            added = (ordinary / '.nix-product').resolve(strict=True)
            counts = json.loads((added / 'result.json').read_text())
            assert (counts['unit-compiled'], counts['unit-restored']) == (1, 2), counts
            for namespace in ('artifact.demo.values', 'artifact.demo.consumer'):
                before, after = ordinary_product / 'units' / namespace, added / 'units' / namespace
                assert {p.name: digest(p) for p in before.iterdir()} == {p.name: digest(p) for p in after.iterdir()}
            values.write_text(original_values.replace('(+ 20 20)', '(+ 20 30)'))
            bl('ordinary-cli-macro-edit', ['build', '--out', str(ordinary)], project)
            edited = (ordinary / '.nix-product').resolve(strict=True)
            counts = json.loads((edited / 'result.json').read_text())
            assert (counts['unit-compiled'], counts['unit-restored']) == (2, 1), counts
            run('ordinary-edited-source-free-receiver', [elixir, scripts / 'nix_application_receiver.exs'], image,
                dict(receiver_env, BL_APPLICATION_PRODUCT=edited, BL_APPLICATION_EXPECT_ANSWER='52',
                     BL_APPLICATION_EXPECT_BASE='50'), 'IMMUTABLE-MULTI answer=52')
            unrelated.unlink()
            bl('ordinary-cli-deleted', ['build', '--out', str(ordinary)], project)
            deleted = (ordinary / '.nix-product').resolve(strict=True)
            counts = json.loads((deleted / 'result.json').read_text())
            assert (counts['unit-compiled'], counts['unit-restored']) == (0, 2), counts
            assert not (deleted / 'units/artifact.demo.unrelated').exists()
            assert not list((deleted / 'ebin').glob('*Unrelated*'))
        finally:
            values.write_text(original_values)
            unrelated.unlink(missing_ok=True)
        bl('ordinary-cli-restored', ['build', '--out', str(ordinary)], project)
        ordinary_product = (ordinary / '.nix-product').resolve(strict=True)
        report['products']['ordinary_restored'] = str(ordinary_product)

        bl('application-publication', ['run', str(scripts / 'nix_application_publication.bl')], project,
           {'BL_APPLICATION_CONTROL_SOURCE': project, 'BL_APPLICATION_CONTROL_OUTPUT': output / 'publication',
            'BL_APPLICATION_CONTROL_RESULT': output / 'publication.json'}, 'APPLICATION-PUBLICATION')
        bl('application-scope', ['run', str(scripts / 'nix_application_scope.bl')], project,
           {'BL_SCOPE_SOURCE': project, 'BL_SCOPE_OUTPUT': output / 'scoped', 'BL_SCOPE_BASE': ordinary_product},
           'APPLICATION-SCOPE-PUBLICATION passed')
        bl('application-force', ['run', str(scripts / 'nix_application_force.bl')], project,
           {'BL_FORCE_SOURCE': project, 'BL_FORCE_OUTPUT': output / 'force', 'BL_FORCE_RESULT': output / 'force.json'},
           'APPLICATION-FORCE-REMOTE passed')
        bl('sdk-projection', ['run', str(scripts / 'nix_sdk_projection.bl')], output,
           {'BL_SDK_CONTROL_PRODUCT': sdk, 'BL_SDK_CONTROL_OUTPUT': output / 'sdk-projection'},
           'SDK PROJECTION AND REUSE PASSED')

        world = output / 'world-project'
        shutil.copytree(repo / 'test/fixtures/contextual-language', world)
        (world / 'env.bl').write_text('{:build {:world "world.bl" :jobs 1}}\n')
        world_out = output / 'world'
        bl('world-cli', ['build', '--out', str(world_out)], world)
        world_product = (world_out / '.nix-product').resolve(strict=True)
        report['products']['world'] = str(world_product)
        descriptor = json.loads((world_product / 'artifact.json').read_text())
        assert descriptor['sdk'] == str(sdk)
        bl('world-publication', ['run', str(scripts / 'nix_world_publication.bl')], output,
           {'BL_WORLD_CONTROL_OUTPUT': output / 'world-publication', 'BL_WORLD_CONTROL_PRODUCT': world_product,
            'BL_WORLD_CONTROL_SDK': sdk, 'BL_WORLD_CONTROL_SOURCE': descriptor['source']}, 'WORLD-PUBLICATION passed')
        run('world-source-free-receiver', [elixir, scripts / 'nix_world_receiver.exs'], image,
            dict(receiver_env, BL_APPLICATION_PRODUCT=world_product), 'IMMUTABLE-WORLD')

        portable_dir = output / 'portable'
        portable_dir.mkdir()
        portable = portable_dir / 'bl.drop'
        bl('self-build', ['self-build', '--out', str(portable)], output, marker='self-build:')
        release = Path(metadata['release'])
        release_metadata = json.loads((release / 'artifact.json').read_text())
        assert release_metadata['compiler'] == metadata['compiler']
        assert release_metadata['sha256'] == digest(portable) == digest(release / 'bl.drop')
        assert portable.read_bytes() == (release / 'bl.drop').read_bytes()
        report['products']['portable'] = {'path': str(portable), 'release': str(release), 'sha256': digest(portable)}
        run('portable-receiver', [portable, '--cold', 'eval', '(do (assert (= 42 (+ 20 22))) (println "PORTABLE-CONSUMER passed"))'],
            portable_dir, marker='PORTABLE-CONSUMER passed')

        fhs = output / 'portable-fhs'
        run('portable-no-nix-store', [platform / 'artifact-platform/bin/nix', 'build', '--impure',
                                    '--file', repo / 'test/nix/portable-runtime-control.nix',
                                    '--argstr', 'release', release, '--max-jobs', '0',
                                    '--option', 'experimental-features', 'nix-command flakes',
                                    '--out-link', fhs], output)
        fhs_result = json.loads((fhs / 'result.json').read_text())
        assert fhs_result == {'passed': True, 'nixStoreVisible': False, 'answer': 42, 'nativeJson': True}
        report['products']['portable_fhs'] = str(fhs.resolve(strict=True))

        workspace = output / 'workspace-project'
        shutil.copytree(repo / 'examples/artifacts/workspace', workspace,
                        ignore=shutil.ignore_patterns('target', '.bl', '.git', 'priv'))
        support = workspace / 'rust/support/answer.txt'
        original = support.read_bytes()
        try:
            bl('workspace-ordinary-build', ['build', '--out', str(output / 'workspace-application')], workspace)
            workspace_product = (output / 'workspace-application/.nix-product').resolve(strict=True)
            assert (workspace_product / 'native/workspace_demo.so').is_file()
            assert json.loads((workspace_product / 'artifact.json').read_text())['sdk'] == str(sdk)
            # Use the native pointer installed by ordinary application build.
            # Hide the project Source during the fresh receiver, so no loader
            # fallback can disguise failure to consume the compiled units.
            held_source = output / 'workspace-source-held'
            (workspace / 'src').rename(held_source)
            try:
                run('workspace-application-source-free-receiver',
                    [elixir, scripts / 'nix_workspace_application_receiver.exs'], workspace,
                    dict(receiver_env, BL_APPLICATION_PRODUCT=workspace_product,
                         BL_WORKSPACE_PROJECT=workspace), 'IMMUTABLE-WORKSPACE-APPLICATION passed')
            finally:
                held_source.rename(workspace / 'src')
            report['products']['workspace_application'] = str(workspace_product)
            bl('workspace-42', ['run', 'showcase.bl'], workspace, marker='"answer":42')
            answer_records = [json.loads(line) for line in (output / 'logs/workspace-42.log').read_text().splitlines()
                              if line.startswith('{') and 'supportMessage' in line]
            assert len(answer_records) == 1
            assert answer_records[0]['supportMessage'] == 'workspace support is captured'
            assert answer_records[0]['crate'] == 'workspace_demo'
            assert answer_records[0]['package'] == 'artifact-workspace-engine'
            assert answer_records[0]['cargoLibrary'] == 'workspace_engine_nif'
            first = (workspace / 'priv/native/workspace_demo.so').resolve(strict=True)
            support.write_text('43\n')
            bl('workspace-43', ['run', 'showcase.bl'], workspace,
               {'BL_WORKSPACE_EXPECTED': '43'}, '"answer":43')
            changed = (workspace / 'priv/native/workspace_demo.so').resolve(strict=True)
            assert first != changed
            support.write_bytes(original)
            bl('workspace-restored-42', ['run', 'showcase.bl'], workspace, marker='"answer":42')
            assert (workspace / 'priv/native/workspace_demo.so').resolve(strict=True) == first
            report['products']['workspace'] = {'original': str(first), 'mutated': str(changed), 'restored': str(first)}
        finally:
            support.write_bytes(original)
        report['status'] = 'passed'
    except BaseException as error:
        report.update(status='failed', error=str(error), error_type=type(error).__name__)
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
