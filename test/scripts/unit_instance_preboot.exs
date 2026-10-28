# Actual immutable candidate only: no Source compiler, namespace vars or body.
owner = BeamLisp.Env
{:module, ^owner} = Code.ensure_loaded(owner)
for {name, arity} <- [invoke_generation_factory!: 1, consume_generation_factory!: 0,
                       invoke_generation_value!: 2] do
  true = function_exported?(owner, name, arity)
end
defmodule UnitInstancePrebootBomb do
  def __bl_unit__, do: send(self(), :unexpected_unit_body)
end
false = :code.is_loaded(BeamLisp.Ns.Compiler) != false
:undefined = :ets.whereis(:beam_lisp_vars)
for {name, args, expected} <- [
      {:invoke_generation_factory!, [UnitInstancePrebootBomb], :unadmitted_unit_factory},
      {:consume_generation_factory!, [], :unadmitted_unit_factory},
      {:invoke_generation_value!, [fn -> send(self(), :unexpected_unit_body) end, []], :unadmitted_unit_instance}
    ] do
  caught = try do
    apply(owner, name, args)
    :accepted
  rescue
    error in ErlangError -> error.original
  end
  ^expected = caught
end
receive do :unexpected_unit_body -> raise "preboot unit gate ran body" after 0 -> :ok end
false = :code.is_loaded(BeamLisp.Ns.Compiler) != false
:undefined = :ets.whereis(:beam_lisp_vars)
IO.puts("UNIT-INSTANCE-PREBOOT 3 refused; compiler unloaded; namespace table absent")
