# Invoked only by the closed SDK worker, before ordinary Launcher.main/1.
# Cache data cannot grant SDK authority. Exact constructor inputs are checked
# against native-verified raw units; the normal loader still checks closure,
# tier key, complete membership and actual relocated BEAM digests before use.
case System.get_env("BL_PRODUCTION_CACHE") do
  nil -> :ok
  directory ->
    started = System.monotonic_time(:microsecond)
    BeamLisp.LazyMemo.ensure_loaded!()
    root = BeamLisp.Tiers.priv_root()
    index_file = Path.join(directory, "unit-index.json")
    unless File.stat!(index_file).size <= 33_554_432, do: raise("producer index exceeds bound")
    index = Jason.decode!(File.read!(index_file))
    runtime = Base.encode16(BeamLisp.AOT.runtime_image_key(), case: :lower)
    eligible = index["version"] == 1 and index["compiler"] == BeamLisp.AOTCache.compiler_key() and index["runtime"] == runtime
    selected = if eligible, do: index["units"], else: %{}
    inputs = selected |> Map.values() |> Enum.flat_map(& &1["inputs"])
    observations = inputs |> Enum.uniq_by(&{&1["scope"], &1["file"]}) |> Map.new(fn input ->
      path = Path.expand(input["file"], root)
      sha = if input["scope"] == "root" and String.starts_with?(path, Path.expand(root) <> "/") and File.regular?(path),
        do: Base.encode16(:crypto.hash(:sha256, BeamLisp.Loader.read_source(path)), case: :lower)
      {{input["scope"], input["file"]}, sha}
    end)
    names = Enum.flat_map(selected, fn {namespace, row} ->
      unless Regex.match?(~r/^[A-Za-z_][A-Za-z0-9_.-]*$/, namespace), do: raise("invalid producer namespace")
      current = row["inputs"] != [] and Enum.all?(row["inputs"], fn input ->
        observations[{input["scope"], input["file"]}] == input["sha256"]
      end)
      if current and row["key"] == BeamLisp.AOTCache.key_for_source(Path.join(root, row["file"])) do
        verified = BeamLisp.AOT.verify_unit(Path.join([directory, ".units", namespace]))
        actual = Map.new(verified.manifest.inputs, &{&1.namespace, Base.encode16(&1.sha256, case: :lower)})
        expected = Map.new(row["inputs"], &{&1["namespace"], &1["sha256"]})
        unless verified.manifest.namespace == namespace and actual == expected and Map.has_key?(actual, namespace),
          do: raise("producer constructor receipts disagree")
        Enum.map(verified.manifest.modules, & &1.module)
      else
        []
      end
    end)
    # A partial miss leaves absent modules absent; normal loading compiles them.
    # The index is immutable data and cannot admit a module on its own.
    floor = BeamLisp.Bootstrap.manifest()["modules"]
    names = Enum.reject(names, &Map.has_key?(floor, &1 <> ".beam"))
    for name <- names do
      File.cp!(Path.join([directory, "ebin", name <> ".beam"]), Path.join(System.fetch_env!("BL_EBIN"), name <> ".beam"))
    end
    index_file = Path.join(directory, "precompiled.term")
    unless File.stat!(index_file).size <= 8_388_608, do: raise("producer projection exceeds bound")
    projection = :erlang.binary_to_term(File.read!(index_file), [:safe])
    present = MapSet.new(names)
    entries = Map.filter(projection.entries, fn {_, row} -> Enum.all?(row.modules, &MapSet.member?(present, &1)) end)
    File.write!(Path.join(root, "precompiled.term"), :erlang.term_to_binary(%{projection | entries: entries}, [:deterministic]))
    result = %{modules: length(names), eligible: eligible, inputs: map_size(observations), references: length(inputs),
      "elapsed-us": System.monotonic_time(:microsecond) - started}
    IO.puts("SDK-PRODUCER-RESTORE " <> Jason.encode!(result))
    result
end
