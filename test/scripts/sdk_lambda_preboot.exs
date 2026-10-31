# Positive metadata parsing and refusal must work before any Lisp namespace.
aot = BeamLisp.AOT
false = :code.is_loaded(BeamLisp.Ns.Compiler) != false
:undefined = :ets.whereis(:beam_lisp_vars)

for module <- [BeamLisp.Env, BeamLisp.AOT] do
  {:module, ^module} = Code.ensure_loaded(module)
  bytes = File.read!(to_string(:code.which(module)))
  routes = apply(aot, :sdk_lambda_routes!, [bytes])
  true = map_size(routes) > 0
  true = Enum.sort(Map.keys(routes)) == Enum.to_list(0..(map_size(routes) - 1))
  true = Enum.all?(routes, fn {_, {name, arity, free}} ->
    is_atom(name) and is_integer(arity) and is_integer(free) and
      arity >= 0 and free >= 0 and arity + free <= 255
  end)
end

bytes = File.read!(to_string(:code.which(BeamLisp.Env)))
{:ok, _, chunks} = :beam_lib.all_chunks(bytes)
{_, table} = List.keyfind(chunks, ~c"FunT", 0)
replace_word = fn binary, offset, value ->
  <<prefix::binary-size(^offset), _::unsigned-big-32, suffix::binary>> = binary
  <<prefix::binary, value::unsigned-big-32, suffix::binary>>
end
<<_::unsigned-big-32, _function::unsigned-big-32, first_arity::unsigned-big-32, _::binary>> = table
malformed = [
  {:short_header, binary_part(table, 0, 3)},
  {:wrong_count, replace_word.(table, 0, 0)},
  {:oversized_count, replace_word.(table, 0, 65_537)},
  {:missing_function_atom, replace_word.(table, 4, 0)},
  {:oversized_arity, replace_word.(table, 8, 256)},
  {:free_exceeds_arity, replace_word.(table, 20, first_arity + 1)},
  {:trailing_bytes, table <> <<0>>}
]
for {label, changed} <- malformed do
  {:ok, bad} = :beam_lib.build_module(List.keyreplace(chunks, ~c"FunT", 0, {~c"FunT", changed}))
  caught = try do
    apply(aot, :sdk_lambda_routes!, [bad])
    :accepted
  rescue
    error in ErlangError -> error.original
  end
  unless caught == :invalid_sdk_lambda_table,
    do: raise("SDK lambda preboot #{label}: #{inspect(caught)}")
end
{:ok, no_lambdas} = :beam_lib.build_module(List.keydelete(chunks, ~c"FunT", 0))
%{} = empty = apply(aot, :sdk_lambda_routes!, [no_lambdas])
0 = map_size(empty)
false = :code.is_loaded(BeamLisp.Ns.Compiler) != false
:undefined = :ets.whereis(:beam_lisp_vars)
IO.puts("SDK-LAMBDA-PREBOOT 10 passed; compiler unloaded; namespace table absent")
