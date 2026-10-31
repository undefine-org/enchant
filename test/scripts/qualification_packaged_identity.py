#!/usr/bin/env python3
"""Exact portable parent/fixture-child identity; existing artifacts only.

Run under a process-tree cap. Four cold VMs execute serially across two parent
requests. The private negative helper uses the genuine checkout seed, never a
forged SDK inventory or replacement installed runtime.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def quoted(text):
    return json.dumps(text, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    sdk, out = args.sdk.resolve(strict=True), args.out.absolute()
    metadata = json.loads((sdk / 'artifact.json').read_text())
    assert (metadata['version'], metadata['kind'], metadata['target']) == (1, 'sdk', 'x86_64-linux')
    candidate = Path(metadata['release']) / 'bl.drop'
    release = json.loads((candidate.parent / 'artifact.json').read_text())
    assert digest(candidate) == release['sha256'] and release['compiler'] == metadata['compiler']
    out.mkdir(parents=True, exist_ok=False)
    project, fixture = out / 'foreign-project', out / 'fixtures'
    project.mkdir(); fixture.mkdir()
    (project / 'env.bl').write_text('{:name "foreign-caller" :paths ["poison"]}\n')
    shutil.copytree(root / 'priv/host', project / 'priv/host')
    poison = project / 'poison/clojure'; poison.mkdir(parents=True)
    (poison / 'string.bl').write_text('(ns clojure.string) (defn upper-case [x] "wrong caller SDK")\n')
    foreign = project / 'priv/host/server.bl'
    foreign.write_bytes(foreign.read_bytes() + b'\n; conflicting caller compiler Source\n')
    (fixture / 'identity_child.bl').write_text('(println "CHILD_APPLICATION_READY")\n')
    members = ['Elixir.BeamLisp', 'Elixir.BeamLisp.Compiler', 'Elixir.BeamLisp.Bootstrap']
    expected = {module: digest(sdk / 'image/ebin' / (module + '.beam')) for module in members}
    native_members = ', '.join('{' + module + ', ' + quoted(value) + '}' for module, value in expected.items())
    preflight = '''for {module, expected} <- [%s] do
  file = :code.which(module)
  actual = if is_list(file), do: Base.encode16(:crypto.hash(:sha256, File.read!(file)), case: :lower), else: nil
  unless actual == expected, do: raise("QUALIFICATION_CHILD_WRONG_COMPILER_BYTES #{module}")
end
IO.puts("CHILD_NATIVE_IDENTITY_READY")
''' % native_members
    helper = (root / 'test/support/source_fixtures.bl').read_text()
    needle = r'"Application.load(:beam_lisp)\n"'
    assert helper.count(needle) == 1
    helper = helper.replace(needle, quoted(preflight + 'Application.load(:beam_lisp)\n'))
    before = 'paths (Enum/map (code/get_path) (fn [path] (erlang/list_to_binary path)))'
    after = 'paths (erlang/++ (Enum/map (code/get_path) (fn [path] (erlang/list_to_binary path))) (list ' + quoted(str(root / 'priv/bootstrap/seed')) + '))'
    assert helper.count(before) == 1
    current = helper.replace('(ns test.support.source-fixtures)', '(ns qualification.identity.current)')
    mutant = helper.replace('(ns test.support.source-fixtures)', '(ns qualification.identity.foreign)').replace(before, after)
    manifest_sha = digest(sdk / 'image/priv/bootstrap/seed/manifest.term')
    parent = '''(ns qualification.portable.identity)
(let [expected %s]
 (doseq [[name sha] expected]
  (let [path (erlang/list_to_binary (code/which (String/to_existing_atom name)))]
   (when-not (= sha (String/downcase (Base/encode16 (crypto/hash :sha256 (File/read! path)))))
    (throw (ex-info "Portable parent selected different native bytes" {:module name})))))
 (when-not (= %s (String/downcase (Base/encode16 (crypto/hash :sha256
     (File/read! (Path/join (BeamLisp.Bootstrap/seed_dir) "manifest.term"))))))
  (throw :portable-parent-selected-caller-floor))
 (when-not (= (elem (BeamLisp.Bootstrap/packaged_keys!) 0) (BeamLisp.AOTCache/current_compiler_key))
  (throw :portable-parent-fingerprinted-foreign-source))
 (println "PORTABLE_PARENT_IDENTITY_READY")
 (when (= "children" (System/get_env "BL_HISTORY_IDENTITY_MODE"))
  ;; The actual qualification entry makes the same host-child distinction:
  ;; external Elixir must resolve its own erl rather than the drop's private one.
  (let [path (System/fetch_env! "BL_HISTORY_HOST_PATH")]
   (System/put_env "PATH" path)
   (erlang/apply :Elixir.System :put_env (list "PATH" path)))
  (doseq [name ["ERTS_BIN" "ERL_ROOTDIR"]]
   (System/delete_env name)
   (erlang/apply :Elixir.System :delete_env (list name)))
  (BeamLisp.Env/with_ns "qualification.portable.identity" #(BeamLisp.Compiler/eval_string %s))
  (BeamLisp.Env/with_ns "qualification.portable.identity" #(BeamLisp.Compiler/eval_string %s))
  (let [[good good-status] (BeamLisp.Ns.Rt/invoke (BeamLisp.Env/fetch_exact! "qualification.identity.current" "cold!") (list "identity_child.bl"))
        [bad bad-status] (BeamLisp.Ns.Rt/invoke (BeamLisp.Env/fetch_exact! "qualification.identity.foreign" "cold!") (list "identity_child.bl"))]
   (println good)
   (when-not (and (= 0 good-status) (String/contains? good "CHILD_NATIVE_IDENTITY_READY")
                 (String/contains? good "CHILD_APPLICATION_READY"))
    (throw (ex-info "Current fixture child identity failed" {:status good-status :output good})))
   (when-not (and (not= 0 bad-status) (String/contains? bad "QUALIFICATION_CHILD_WRONG_COMPILER_BYTES")
                 (not (String/contains? bad "CHILD_APPLICATION_READY")))
    (throw (ex-info "Foreign fixture child escaped identity control" {:status bad-status :output bad})))
   (println "FOREIGN_CHILD_REFUSED_BEFORE_APPLICATION_READY"))))
''' % ('{' + ' '.join(quoted(k) + ' ' + quoted(v) for k, v in expected.items()) + '}',
       quoted(manifest_sha), quoted(current), quoted(mutant))
    driver = project / 'parent.bl'; driver.write_text(parent)
    environment = {name: value for name, value in os.environ.items()
                   if not name.startswith(('BL_', 'BEAM_LISP_')) and name not in ('ERTS_BIN', 'ERL_ROOTDIR', 'ERL_LIBS', 'ERL_FLAGS', 'ERL_AFLAGS', 'ERL_ZFLAGS', 'DROP_STORE_ROOT')}
    host_path = str(Path(metadata['platform']) / 'bin') + ':' + environment.get('PATH', '')
    environment.update(PATH=host_path, BL_HISTORY_HOST_PATH=host_path,
                       BL_TEST_SOURCE_ROOT=str(fixture), ELIXIR_ERL_OPTIONS='+S 2:2 +SDcpu 1:1 +SDio 1:1 +fnu')
    report = {'version': 1, 'cases': ['E25', 'E49'], 'status': 'running', 'sdk': str(sdk),
              'candidate_sha256': digest(candidate), 'manifest_sha256': manifest_sha,
              'helper_source_sha256': digest(root / 'test/support/source_fixtures.bl'),
              'before': before, 'after': after, 'expected_native_bytes': expected, 'stages': [],
              'scope': 'Actual portable executable and actual Source-derived cold fixture helper; no SDK production or installed SDK mutation'}
    try:
        for mode in ['children', 'edited-caller-source']:
            if mode != 'children':
                foreign.write_bytes(foreign.read_bytes() + b'; another caller edit\n')
                (project / 'env.bl').write_text('{:name "different-foreign-caller" :paths ["poison"]}\n')
            env = dict(environment, BL_HISTORY_IDENTITY_MODE=mode)
            for key in ('CACHE', 'DATA', 'STATE', 'RUNTIME'):
                directory = out / mode / key.lower(); directory.mkdir(parents=True, mode=0o700)
                env['XDG_' + key + ('_DIR' if key == 'RUNTIME' else '_HOME')] = str(directory)
            started = time.monotonic()
            process = subprocess.Popen([str(candidate), '--cold', 'run', str(driver)], cwd=project, env=env,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
            try:
                output, _ = process.communicate(timeout=90)
            except BaseException:
                os.killpg(process.pid, signal.SIGKILL); process.communicate(); raise
            (out / (mode + '.log')).write_text(output)
            report['stages'].append({'mode': mode, 'exit': process.returncode, 'seconds': round(time.monotonic() - started, 3)})
            print(output[-9000:], end='', flush=True)
            assert process.returncode == 0 and 'PORTABLE_PARENT_IDENTITY_READY' in output, output
            if mode == 'children':
                assert 'FOREIGN_CHILD_REFUSED_BEFORE_APPLICATION_READY' in output, output
            assert digest(candidate) == report['candidate_sha256']
        report['status'] = 'passed'
    finally:
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PACKAGED_IDENTITY_CONTROLS_READY')


if __name__ == '__main__':
    main()
