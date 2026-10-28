mod = BeamLisp.CompilerData
false = :code.is_loaded(BeamLisp.Ns.Compiler) != false
:undefined = :ets.whereis(:beam_lisp_vars)
{:module, ^mod} = Code.ensure_loaded(mod)
ref = %{version: 1, kind: :"binding-reference", world: <<0::256>>, declaration: <<1::256>>, id: <<2::256>>, space: {:symbol, "value"}, phase: 0}
row = %{name: "one", slot: "one_1", reference: ref, node: %{op: :lit, val: 42, ann: %{}}}
unit = %{version: 1, kind: :"compiled-contextual-unit", initializers: [row], entry: row.node, exports: [ref]}
^unit = apply(mod, :check_contextual_unit!, [unit])
other = %{row | name: "two", slot: "two_2", reference: %{ref | declaration: <<3::256>>, id: <<4::256>>}}
for {bad, reason} <- [
  {%{unit | version: 1.0}, :unit},
  {%{unit | initializers: [row, %{other | slot: row.slot}]}, :"initializer-slot"},
  {%{unit | initializers: [row, %{other | name: row.name}]}, :"initializer-name"},
  {%{unit | exports: [ref, ref]}, :"export-reference"}
] do
  caught = try do
    apply(mod, :check_contextual_unit!, [bad])
    :accepted
  rescue
    error in ErlangError -> error.original
  end
  {:invalid_contextual_unit, ^reason} = caught
end
clause = %{pats: [%{pop: :pvar, name: "_"}], guard: nil, body: row.node}
function = %{op: :fn, clauses: [clause], ann: %{}}
^clause = apply(mod, :simple_function_clause, [function])
empty = %{clause | pats: []}
^empty = apply(mod, :simple_function_clause, [%{function | clauses: [empty]}])
nil = apply(mod, :simple_function_clause, [%{function | clauses: [%{clause | guard: row.node}]}])
nil = apply(mod, :simple_function_clause, [%{function | clauses: [%{clause | pats: [%{pop: :pnil}]}]}])
deferred = fn -> send(self(), :unexpected_pattern_realization) end
nil = apply(mod, :simple_function_clause, [%{function | clauses: [%{clause | pats: deferred}]}])
receive do :unexpected_pattern_realization -> raise "pattern shape view executed input" after 0 -> :ok end
%{frames: "__STACKTRACE__", raw: "__STACKTRACE_RAW__"} = apply(mod, :catch_stack_bindings, [])
false = :code.is_loaded(BeamLisp.Ns.Compiler) != false
:undefined = :ets.whereis(:beam_lisp_vars)
IO.puts("CONTEXTUAL-UNIT-PREBOOT 11 passed; compiler unloaded; namespace table absent")
