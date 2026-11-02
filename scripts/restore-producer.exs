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
    units = Enum.flat_map(selected, fn {namespace, row} ->
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
        [%{key: row["key"], modules: Enum.map(verified.beams, &elem(&1, 0))}]
      else
        []
      end
    end)
    # Seed only the ordinary writable cache, never the executable code path.
    # Native store/prepare_fetch validate the same complete provenance protocol
    # used by every other cache hit; Loader still owns activation and effects.
    index_file = Path.join(directory, "precompiled.term")
    unless File.stat!(index_file).size <= 8_388_608, do: raise("producer projection exceeds bound")
    projection = :erlang.binary_to_term(File.read!(index_file), [:safe])
    floor = BeamLisp.Bootstrap.manifest()["modules"]
    restored = Enum.reduce(units, 0, fn unit, total ->
      names = Enum.map(unit.modules, &Atom.to_string/1) |> MapSet.new()
      entry = Enum.find(projection.entries, fn {{key, _closure}, row} ->
        key == unit.key and MapSet.new(row.modules) == names
      end)
      if entry && Enum.all?(names, &(not Map.has_key?(floor, &1 <> ".beam"))) do
        {{key, closure}, row} = entry
        unless Regex.match?(~r/^[0-9a-f]{64}$/, key) && Regex.match?(~r/^[0-9a-f]{64}$/, closure),
          do: raise("invalid producer cache address")
        for name <- row.modules do
          bytes = File.read!(Path.join([directory, "ebin", name <> ".beam"]))
          unless :crypto.hash(:sha256, bytes) == row.digests[name], do: raise("producer image bytes disagree")
        end
        :ok = BeamLisp.AOTCache.store(key, closure, Path.join(directory, "ebin"), unit.modules, closure)
        case BeamLisp.AOTCache.prepare_fetch(key, closure) do
          %{modules: captured} ->
            unless MapSet.new(captured) == MapSet.new(unit.modules), do: raise("producer cache membership differs")
            total + length(captured)
          nil -> total  # An ordinary unsupported cache shape is a compile miss.
        end
      else
        total
      end
    end)
    result = %{modules: restored, eligible: eligible, inputs: map_size(observations), references: length(inputs),
      "elapsed-us": System.monotonic_time(:microsecond) - started}
    IO.puts("SDK-PRODUCER-RESTORE " <> Jason.encode!(result))
    result
end
