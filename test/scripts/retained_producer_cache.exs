restore = System.fetch_env!("BL_PRODUCER_RESTORE")
cache = System.fetch_env!("BL_PRODUCTION_CACHE")
ebin = System.fetch_env!("BL_EBIN")
root = BeamLisp.Tiers.priv_root()
floor = BeamLisp.Bootstrap.manifest()["modules"]
floor_bytes = Map.new(floor, fn {name, _} -> {name, File.read!(Path.join(ebin, name))} end)
index_path = Path.join(cache, "unit-index.json")
original_index = File.read!(index_path)
index = Jason.decode!(original_index)
clean = fn ->
  for path <- Path.wildcard(Path.join(ebin, "*.beam")), not Map.has_key?(floor, Path.basename(path)), do: File.rm!(path)
  File.rm(Path.join(root, "precompiled.term"))
end
run = fn ->
  {result, _} = Code.eval_file(restore)
  result
end
assert_refused = fn action ->
  refused = try do action.(); false catch _, _ -> true end
  unless refused, do: raise("invalid producer cache was accepted")
  unless Enum.all?(floor_bytes, fn {name, bytes} -> File.read!(Path.join(ebin, name)) == bytes end),
    do: raise("qualified floor was overwritten")
end

# Missing current input is an ordinary per-unit cache miss.
row = index["units"]["vm.osenv"]
input = Path.join(root, row["file"])
bytes = File.read!(input)
File.chmod!(input, 0o644)
File.write!(input, bytes <> "\n; changed probe input\n")
changed = run.()
if changed.modules == 0, do: raise("unaffected producer units were lost")
if File.exists?(Path.join(ebin, "Elixir.BeamLisp.Ns.Vm.Osenv.beam")), do: raise("changed input was restored")
File.write!(input, bytes)
clean.()

# A receipt omitting a real constructor dependency is not a cache miss.
forged = put_in(index, ["units", "selfbuild", "inputs"], tl(index["units"]["selfbuild"]["inputs"]))
File.write!(index_path, Jason.encode!(forged))
assert_refused.(run)
File.write!(index_path, original_index)
clean.()

# Native verification, not a copied index, authenticates complete unit bytes.
unit_beam = Path.wildcard(Path.join(cache, ".units/selfbuild/*.beam")) |> hd()
unit_bytes = File.read!(unit_beam)
File.chmod!(unit_beam, 0o644)
File.write!(unit_beam, "corrupt")
assert_refused.(run)
File.write!(unit_beam, unit_bytes)
clean.()

File.write!(index_path, Jason.encode!(%{index | "runtime" => String.duplicate("0", 64)}))
%{eligible: false, modules: 0} = run.()
File.write!(index_path, original_index)
clean.()

%{eligible: true, modules: restored} = run.()
if restored == 0, do: raise("empty restored producer")
patterns = [{BeamLisp.AOT, :constructor_compile_sdk_unit!, 2}, {BeamLisp.AOT, :compile_source_unit_impl, 2}, {BeamLisp.AOT, :compile_unit, 1}]
for pattern <- patterns, do: :erlang.trace_pattern(pattern, true, [:local, :call_count])
0 = BeamLisp.Launcher.boot(["--cold", "eval", "(ns producer.probe (:require [selfbuild])) (println :producer-loaded)"], %{halt: fn status -> status end})
for pattern <- patterns do
  {:call_count, count} = :erlang.trace_info(pattern, :call_count)
  unless count == 0, do: raise("producer recompiled SDK Source: #{inspect(pattern)}: #{count}")
end
unless Enum.all?(floor_bytes, fn {name, bytes} -> File.read!(Path.join(ebin, name)) == bytes end),
  do: raise("qualified floor changed")
IO.puts("SDK-PRODUCER-CONTROLS passed")
