# The current immutable candidate must expose restrictive ingress before boot.
owner = BeamLisp.Env
{:module, ^owner} = Code.ensure_loaded(owner)
true = function_exported?(owner, :with_source_execution!, 2)
false = :code.is_loaded(BeamLisp.Ns.Compiler) != false
:undefined = :ets.whereis(:beam_lisp_vars)
for marker <- [nil, %{}, {:"bl-execution-graph", {:env, make_ref()}, make_ref()}] do
  caught = try do
    apply(owner, :with_source_execution!, [marker, fn -> send(self(), :unexpected_instance_body) end])
    :accepted
  rescue
    error in ErlangError -> error.original
  end
  :source_instance_changed = caught
end
receive do :unexpected_instance_body -> raise "preboot instance guard ran body" after 0 -> :ok end
false = :code.is_loaded(BeamLisp.Ns.Compiler) != false
:undefined = :ets.whereis(:beam_lisp_vars)
IO.puts("SOURCE-INSTANCE-PREBOOT 3 refused; compiler unloaded; namespace table absent")
