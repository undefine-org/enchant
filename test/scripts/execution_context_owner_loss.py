#!/usr/bin/env python3
"""Check actual Env death/restart in one disposable VM; run under a process-tree cap.

--image is a coherent app directory containing ebin/ and priv/. This test kills
that private VM's Env owner; it must never attach to a running checkout daemon.
"""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

DRIVER = r'''
for path <- BeamLisp.Loader.library_search_paths(), do: Code.append_path(path)
Application.load(:beam_lisp)
for app <- Application.spec(:beam_lisp, :applications) || [],
  do: {:ok, _} = Application.ensure_all_started(app)
{:ok, _} = Application.ensure_all_started(:beam_lisp)
{:ok, [manifest]} = :file.consult(~c"priv/bootstrap/seed/manifest.term")
unless manifest["compiler_key"] == BeamLisp.AOTCache.current_compiler_key(),
  do: raise "owner-loss image does not match its physical compiler inputs"
for {name, _} <- manifest["modules"], String.ends_with?(name, ".beam") do
  {:ok, {module, expected}} = :beam_lib.md5(String.to_charlist(Path.join("priv/bootstrap/seed", name)))
  if :erlang.module_loaded(module) do
    role = Keyword.get(module.module_info(:attributes), :bl_aot_artifact_role)
    unless role == [:"mutable-forwarder"] or module.module_info(:md5) == expected,
      do: raise "owner-loss startup replaced stable candidate code: #{module}"
  end
end
value = BeamLisp.eval("""
(ns context.owner.loss.probe (:require [reload.generation :as generation]))
(let [graph (generation/prepare!
              {:application-id "context-owner-loss"
               :sources {"context.owner.loss"
                 "(ns context.owner.loss) (defn callback [] (fn [] 42))
                  (defserver pending-owner (init [_] (ok nil)))
                  (defn pending-class [] pending-owner)"}})
      registration (generation/with! graph
                     #(BeamLisp.Execution/register!
                        (generation/invoke! graph "context.owner.loss/callback" [])))
      state (BeamLisp.Env/execution_registration_state registration)
      pending (generation/with! graph
                #(BeamLisp.Env/begin_server_start!
                   (generation/invoke! graph "context.owner.loss/pending-class" [])))
      pending-row (BeamLisp.Env/server_start_row (elem pending 2))]
 (assert (some? (:context-id pending-row)))
 (assert (not (contains? pending-row :generation)))
 (assert (not (contains? pending-row :context)))
 [registration (:context-id (BeamLisp.Env/code_callback_payload (:lease state)))
  (BeamLisp.Env/source_policy_row (tuple :execution_graph_marker (:scope graph)))
  pending (:context-id pending-row)])
""")
[registration, context, marker, pending, pending_context] = BeamLisp.Vector.to_list(value)
%{status: :completed, value: 42} = BeamLisp.Execution.invoke!(registration, [])
guard = BeamLisp.Execution.register!(fn ->
%{:"graph-id" => nil, status: :active} = BeamLisp.Execution.observe()
old = Process.whereis(BeamLisp.Env)
key = {:bl_execution_graph_snapshot, old, marker}
true = is_map(:persistent_term.get(key))
ref = Process.monitor(old)
Process.exit(old, :kill)
receive do
  {:DOWN, ^ref, :process, ^old, :killed} -> :ok
  after 5000 -> raise "actual Env owner did not terminate"
end
wait = fn recur, attempts ->
  case Process.whereis(BeamLisp.Env) do
    pid when is_pid(pid) and pid != old -> pid
    _ when attempts > 0 -> receive do after 5 -> recur.(recur, attempts - 1) end
    _ -> raise "supervisor did not replace the Env owner"
  end
end
new_owner = wait.(wait, 1000)
# Agent callback serializes observation after startup's orphan reclamation.
:ok = Agent.get(new_owner, fn _ -> :ok end)
:absent = :persistent_term.get(key, :absent)
%{status: :cancelled} = BeamLisp.Execution.invoke!(registration, [])
try do
  BeamLisp.Env.execution_context_value!(context)
  raise "old context ID survived native owner replacement"
rescue error in ErlangError -> :retired_execution_context = error.original
end
nil = BeamLisp.Env.server_start_observation(elem(pending, 2))
try do
  BeamLisp.Env.execution_context_value!(pending_context)
  raise "old pending-start context ID survived native owner replacement"
rescue error in ErlangError -> :retired_execution_context = error.original
end
nil = BeamLisp.Env.execution_origin()
try do
  BeamLisp.Env.assert_execution_context!()
  raise "lost frame custody was downgraded to unmanaged execution"
rescue error in ErlangError -> :unadmitted_execution_origin = error.original
end
:stale_frame_refused
end)
%{status: :completed, value: :stale_frame_refused} = BeamLisp.Execution.invoke!(guard, [])
IO.puts("PASS: actual Env restart erased orphan graph storage, refused old callback/pending-start context IDs, erased pending custody, and blocked stale unmanaged frame authority")
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    image = parser.parse_args().image.resolve()
    if not (image / "ebin/beam_lisp.app").is_file() or not (image / "priv").is_dir():
        parser.error("image must contain ebin/beam_lisp.app and priv/")
    with tempfile.TemporaryDirectory(prefix="bl-context-owner-loss-") as temporary:
        script = Path(temporary) / "driver.exs"
        script.write_text(DRIVER)
        env = dict(os.environ, BL_ROOT=str(image), BL_DAEMON="off",
                   XDG_CACHE_HOME=str(Path(temporary) / "cache"),
                   ELIXIR_ERL_OPTIONS="+S 4:4 +SDcpu 2:2 +SDio 1:1")
        tag = subprocess.check_output(
            ["elixir", "-e", 'IO.write("erts#{:erlang.system_info(:version)}-elixir#{System.version()}")'],
            text=True)
        cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "beam_lisp/ebin"
        deps = [*sorted((image / "deps").glob("*/ebin")),
                *sorted((image / "_build").glob("*/lib/*/ebin")),
                *sorted(cache.glob(f"*-{tag}/ebin"))]
        command = ["elixir"]
        for dep in dict.fromkeys(path.resolve() for path in deps):
            command += ["-pa", str(dep)]
        subprocess.run([*command, "-pa", str(image / "ebin"), str(script)],
                       cwd=image, env=env, timeout=300, check=True)


if __name__ == "__main__":
    main()
