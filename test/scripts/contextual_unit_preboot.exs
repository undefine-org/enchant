mod = BeamLisp.CompilerData
false = :code.is_loaded(BeamLisp.Ns.Compiler) != false
:undefined = :ets.whereis(:beam_lisp_vars)
{:module, ^mod} = Code.ensure_loaded(mod)
ref = %{version: 1, kind: :"binding-reference", world: <<0::256>>, declaration: <<1::256>>, id: <<2::256>>, space: {:symbol, "value"}, phase: 0}
row = %{name: "one", slot: "one_1", reference: ref, node: %{op: :lit, val: 42, ann: %{}}}
unit = %{version: 2, kind: :"compiled-contextual-unit", initializers: [row], steps: [%{op: :initialize, reference: ref}], entry: row.node, exports: [ref]}
^unit = apply(mod, :check_contextual_unit!, [unit])
other = %{row | name: "two", slot: "two_2", reference: %{ref | declaration: <<3::256>>, id: <<4::256>>}}
for {bad, reason} <- [
  {%{unit | version: 2.0}, :unit},
  {%{unit | version: 1}, :unit},
  {%{unit | steps: []}, :"missing-initialization"},
  {%{unit | steps: [%{op: :initialize, reference: ref}, %{op: :initialize, reference: ref}]}, :"step-reference"},
  {%{unit | steps: [%{op: :initialize, reference: other.reference}]}, :"step-reference"},
  {%{unit | steps: [%{op: :capture, slot: row.slot, node: row.node}, %{op: :initialize, reference: ref}]}, :"step-slot"},
  {%{unit | steps: [%{op: :unknown, node: row.node}, %{op: :initialize, reference: ref}]}, :"step-operation"},
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
aot = BeamLisp.AOT
spec = {:vector, [{:symbol, "provider"}, {:keyword, "as"}, {:symbol, "p"}, {:keyword, "refer"}, {:vector, [{:symbol, "answer"}]}]}
^spec = apply(mod, :check_reader_data!, [spec])
expected = {"provider", "p", ["answer"]}
^expected = apply(mod, :namespace_require_spec, [spec])
header = fn request -> {:list, [{:symbol, "ns"}, {:symbol, "preboot"}, {:list, [{:keyword, "require"}, request]}]} end
%{"preboot" => %{require_specs: [^expected]}} = apply(aot, :namespace_header, [header.(spec)])
for {flags, reason} <- [
  {[{:keyword, "as"}], :"missing-option-value"},
  {[{:keyword, "as"}, 42], :symbol},
  {[{:keyword, "unknown"}, true], :option},
  {[{:keyword, "as"}, {:symbol, "p"}, {:keyword, "as"}, {:symbol, "q"}], :"duplicate-option"},
  {[{:keyword, "refer"}, {:vector, [{:symbol, "x"}, {:symbol, "x"}]}], :"duplicate-refer"}
] do
  request = {:vector, [{:symbol, "provider"} | flags]}
  for {owner, function, value} <- [{mod, :namespace_require_spec, request}, {aot, :namespace_header, header.(request)}] do
    caught = try do apply(owner, function, [value]); :accepted rescue error in ErlangError -> error.original end
    {:invalid_namespace_require, ^reason} = caught
  end
end
for {owner, function, value} <- [{mod, :namespace_require_spec, {:vector, deferred}}, {aot, :namespace_header, header.({:vector, deferred})}] do
  refused = try do apply(owner, function, [value]); false rescue _ -> true end
  true = refused
end
receive do :unexpected_pattern_realization -> raise "require parser executed input" after 0 -> :ok end
clause = {:list, [{:keyword, "require"}, spec]}
[^clause] = apply(mod, :namespace_clauses, [["documentation", clause]])
%{"preboot" => %{require_specs: [^expected]}} = apply(aot, :namespace_header, [{:list, [{:symbol, "ns"}, {:symbol, "preboot"}, "documentation", clause]}])
for tail <- [[42], ["first", "second"]] do
  caught = try do apply(mod, :namespace_clauses, [tail]); :accepted rescue error in ErlangError -> error.original end
  {:invalid_namespace_header, :clause} = caught
end
false = :code.is_loaded(BeamLisp.Ns.Compiler) != false
:undefined = :ets.whereis(:beam_lisp_vars)
IO.puts("CONTEXTUAL-UNIT-PREBOOT 31 passed; compiler unloaded; namespace table absent")
