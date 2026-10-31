# Native harness only: the image carries no BL Source, constructor driver or
# project code path. Preload the observed modules so exact-byte floor adoption
# preserves their trace patterns; an unloaded module would make an empty trace
# a false negative. Module-info reads are metadata, outside compiler work.
Application.ensure_all_started(:crypto)
program = System.get_env("BL_RUNTIME_MAIN") || "program"
showcases = System.get_env("BL_RUNTIME_SHOWCASES") || "showcases"
if expected_root = System.get_env("BL_RUNTIME_EXPECT_ROOT") do
  root = Path.expand(expected_root)
  unless Path.expand(to_string(:code.root_dir())) == root, do: raise("runtime used host ERTS root")
  unless File.read_link!("/proc/self/exe") == Path.join(root, "erts-#{:erlang.system_info(:version)}/bin/beam.smp"),
    do: raise("runtime did not execute bundled beam.smp")
  for path <- :code.get_path() do
    expanded = Path.expand(to_string(path))
    unless expanded == root or String.starts_with?(expanded, root <> "/"), do: raise("external runtime code path: #{expanded}")
  end
end
{:ok,[manifest]}=:file.consult(String.to_charlist(Path.join(BeamLisp.Bootstrap.seed_dir(),"manifest.term")))
producer=manifest["compiler_key"]
support_root = Path.dirname(BeamLisp.Tiers.priv_root())
for pattern <- ["**/*.bl", "**/*.bl.md", "**/*.phase"] do
 unless Path.wildcard(Path.join(support_root, pattern)) == [],
   do: raise("compiled runtime contains Source or phase inputs")
end
if System.get_env("BL_RUNTIME_CHANGED_FLOOR") == "yes" do
  # Exercise the native runtime admission boundary in this fresh receiver.
  # The positive consumer below separately checks packaged compiler identity.
  BeamLisp.run_runtime_artifact(program, [])
  raise "changed runtime floor was admitted"
end
unless BeamLisp.AOTCache.current_compiler_key()==producer,
  do: raise("packaged compiler identity does not match its verified floor")
observed=[BeamLisp.Reader,BeamLisp.Compiler,BeamLisp.Ns.Reader,BeamLisp.Ns.Body.Reader,
          BeamLisp.Ns.Compiler,BeamLisp.Ns.Body.Compiler]
patterns=Enum.flat_map(observed,fn module ->
 Code.ensure_loaded!(module)
 for {name,arity}<-module.module_info(:functions), name != :module_info, do: {module,name,arity}
end) ++ [{BeamLisp.AOT,:eval_constructor_session!,4},{BeamLisp.AOT,:runtime_floor!,0}]
Code.ensure_loaded!(BeamLisp.AOT)
parent=self()
tracer=spawn(fn ->
 loop=fn loop, calls ->
  receive do
   {:trace,_,:call,{module,name,_}} -> loop.(loop,Map.update(calls,{module,name},1,&(&1+1)))
   {:finish,ticket} -> send(parent,{:calls,ticket,calls})
  end
 end
 loop.(loop,%{})
end)
for pattern<-patterns, do: 1=:erlang.trace_pattern(pattern,true,[:local])
:erlang.trace(self(),true,[:call,{:tracer,tracer}])
value=BeamLisp.run_runtime_artifact(program,["runtime-argument"])
[42,99,42]=BeamLisp.Vector.to_list(value)
false=BeamLisp.Env.seeded?()
false=BeamLisp.Env.retire_module!(BeamLisp.Ns.Body.Rt)
false=BeamLisp.Env.retire_module!(BeamLisp.Ns.Body.Core)
[42,99,42]=BeamLisp.run_runtime_artifact(program,[]) |> BeamLisp.Vector.to_list()
false=BeamLisp.Env.seeded?()
first_owner=Process.whereis(BeamLisp.Env)
Agent.stop(BeamLisp.Env)
[42,99,42]=BeamLisp.run_runtime_artifact(program,[]) |> BeamLisp.Vector.to_list()
second_owner=Process.whereis(BeamLisp.Env)
unless first_owner != second_owner and Process.alive?(second_owner), do: raise "runtime did not recover actual Env ownership"
false=BeamLisp.Env.retire_module!(BeamLisp.Ns.Body.Rt)
false=BeamLisp.Env.seeded?()
showcase_failures = Enum.flat_map(
 [{"language",[42,102,42,42]},{"query",[4,6]},
  {"mailbox",[42,107,99]},{"cleanup",[42,100,40,200]}], fn {name,expected} ->
 try do
  result=BeamLisp.run_runtime_artifact(Path.join(showcases,name),[])
  actual=if is_struct(result,BeamLisp.Vector), do: BeamLisp.Vector.to_list(result), else: result
  unless actual==expected, do: raise "runtime showcase #{name}: #{inspect(actual)}"
  IO.puts("RUNTIME-SHOWCASE #{name} #{inspect(actual,charlists: :as_lists)}")
  []
 rescue
  error ->
   message = Exception.message(error)
   IO.puts(:stderr, "RUNTIME-SHOWCASE-FAILED #{name} #{message}")
   [{name,message}]
 end
end)
Process.delete(:"contextual-cleanup-log")
replacement=File.read!(System.fetch_env!("BL_RUNTIME_REPLACEMENT"))
before=BeamLisp.Ns.Body.Rt.module_info(:md5)
{:ok,{BeamLisp.Ns.Body.Rt,other}}=:beam_lib.md5(replacement)
unless before != other, do: raise "replacement control is not different code"
try do
 BeamLisp.Env.publish_binaries!([{{BeamLisp.Ns.Body.Rt,replacement},"foreign-runtime-proposal"}])
 raise "retained runtime replacement unexpectedly succeeded"
rescue
 error in ErlangError ->
  unless Map.get(error,:original)==:runtime_floor_replacement_requires_restart, do: reraise(error,__STACKTRACE__)
end
^before=BeamLisp.Ns.Body.Rt.module_info(:md5)
[42,99,42]=BeamLisp.run_runtime_artifact(program,[]) |> BeamLisp.Vector.to_list()
barrier=:erlang.trace_delivered(:all)
receive do {:trace_delivered,:all,^barrier}->:ok after 5000->raise "trace barrier timed out" end
ticket=make_ref();send(tracer,{:finish,ticket})
calls=receive do {:calls,^ticket,calls}->calls after 5000->raise "trace report timed out" end
:erlang.trace(self(),false,[:call])
for pattern<-patterns, do: :erlang.trace_pattern(pattern,false,[:local])
floor_captures = Map.get(calls, {BeamLisp.AOT, :runtime_floor!}, 0)
compiler_calls = Map.delete(calls, {BeamLisp.AOT, :runtime_floor!})
unless compiler_calls == %{}, do: raise "runtime executed compiler work: #{inspect(compiler_calls)}"
unless floor_captures == 2, do: raise "warm entries recaptured the support floor: #{floor_captures}"
IO.puts("STANDALONE-RUNTIME #{inspect(BeamLisp.Vector.to_list(value),charlists: :as_lists)} compiler-calls=0 exact-floor-retained=true compiler-seeded=false env-restarted=true replacement-refused=true floor-captures=#{floor_captures} warm-recaptures=0")
unless showcase_failures == [], do: raise("runtime showcases failed: #{inspect(showcase_failures)}")
