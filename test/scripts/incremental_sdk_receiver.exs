# An ordinary new application expression uses a genuinely sealed SDK fragment.
base = System.fetch_env!("BL_INCREMENTAL_BASE")
image = System.fetch_env!("BL_INCREMENTAL_IMAGE")
for path <- Path.wildcard(base <> "/lib/*/ebin"),
    not String.starts_with?(Path.basename(Path.dirname(path)), "beam_lisp-"),
    do: Code.prepend_path(path)
Code.prepend_path(image <> "/ebin")
Application.load(:beam_lisp)
for app <- Application.spec(:beam_lisp, :applications) || [],
    do: ({:ok, _} = Application.ensure_all_started(app))
BeamLisp.AOT.boot()
[] = Path.wildcard(image <> "/priv/**/*.bl")
pattern = {BeamLisp.AOT, :compile_file, 2}
:erlang.trace_pattern(pattern, true, [:local, :call_count])
:ok = BeamLisp.Loader.ensure_loaded("sdk.artifact.consumer")
answer = BeamLisp.Ns.Rt.invoke(BeamLisp.Env.fetch!("sdk.artifact.consumer", "answer"), [])
true = answer == String.to_integer(System.fetch_env!("BL_INCREMENTAL_ANSWER"))
{:call_count, 0} = :erlang.trace_info(pattern, :call_count)
# New project Source expands the packaged SDK macro with SDK Source absent.
^answer = BeamLisp.eval("(ns incremental.prototype.application (:require [sdk.artifact.provider :as p])) (+ 2 (p/forty))")
if value = System.get_env("BL_INCREMENTAL_REAL_VALUE") do
  actual = BeamLisp.eval("(ns incremental.prototype.real-application (:require [errors :as e])) (e/incremental-prototype-value)")
  true = actual == String.to_integer(value)
end
IO.puts("INCREMENTAL-CONSUMER passed answer=#{answer} sdk-compilations=0 source-free=true")
