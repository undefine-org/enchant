# Private Nix worker. Previous units are immutable inputs, never a shared
# writable cache. Ordinary artifact data is sealed by the existing SDK writer.
base = System.fetch_env!("BL_INCREMENTAL_BASE")
root = System.fetch_env!("BL_ROOT")
out = System.fetch_env!("BL_INCREMENTAL_OUTPUT")
request = System.fetch_env!("BL_INCREMENTAL_REQUEST")
for path <- Path.wildcard(base <> "/lib/*/ebin"),
    not String.starts_with?(Path.basename(Path.dirname(path)), "beam_lisp-"),
    do: Code.prepend_path(path)
Code.prepend_path(root <> "/ebin")
Application.load(:beam_lisp)
for app <- Application.spec(:beam_lisp, :applications) || [],
    do: ({:ok, _} = Application.ensure_all_started(app))
BeamLisp.AOT.boot()
{:ok, [floor]} = :file.consult(String.to_charlist(root <> "/priv/bootstrap/seed/manifest.term"))
unless floor["compiler_key"] == BeamLisp.AOTCache.current_compiler_key(),
  do: raise("compiler Source differs from qualified floor")
config = Jason.decode!(File.read!(request))
key = BeamLisp.AOTCache.compiler_key()
runtime = Base.encode16(BeamLisp.AOT.runtime_image_key(), case: :lower)
previous = config["previous"]
old = if previous, do: Jason.decode!(File.read!(previous <> "/index.json")), else: nil
if old && (old["runtime"] != runtime || old["compiler"] != config["compiler"] ||
           old["dependencies"] != config["dependencies"] || old["baseline"] != config["baseline"]),
  do: raise("previous product belongs to another compiler/runtime/dependency generation")
sha = fn bytes -> Base.encode16(:crypto.hash(:sha256, bytes), case: :lower) end
priv = root <> "/priv"
snapshot = fn ->
  Map.new(Path.wildcard(priv <> "/**/*") |> Enum.filter(&File.regular?/1),
    fn path -> {path, sha.(File.read!(path))} end)
end
frozen = snapshot.()
selection = Enum.map(config["selection"], fn relative ->
  path = Path.join(root, relative)
  source = BeamLisp.Loader.read_source(path)
  ns = BeamLisp.Loader.declared_ns(source) || raise("selected Source has no namespace")
  unless Regex.match?(~r/^[A-Za-z_][A-Za-z0-9_.-]*$/, ns), do: raise("invalid unit directory name")
  {ns, path}
end)
unless Enum.uniq_by(selection, &elem(&1, 0)) == selection, do: raise("duplicate namespace")
File.mkdir_p!(out <> "/units")
started = System.monotonic_time(:millisecond)
# Count actual compiler calls, independently of the reuse bookkeeping.
pattern = {BeamLisp.AOT, :compile_unit, 1}
:erlang.trace_pattern(pattern, true, [:local, :call_count])
before_env = BeamLisp.Env.capture()
{entries, manifest, compiled, restored} =
  Enum.reduce(selection, {%{}, %{}, [], []}, fn {ns, path}, {entries, manifest, compiled, restored} ->
    prior = old && old["units"][ns]
    destination = out <> "/units/" <> ns
    # Re-resolve every recorded namespace in the current frozen source world.
    # Hashes include macro/value providers actually read by the constructor.
    reusable = prior && Enum.all?(prior["inputs"], fn input ->
      current = BeamLisp.Loader.source_path(input["namespace"])
      current && Path.relative_to(current, priv) == input["file"] &&
        sha.(BeamLisp.Loader.read_source(current)) == input["sha256"]
    end)
    {verified, inputs, compiled, restored} = if reusable do
      verified = BeamLisp.AOT.verify_unit(previous <> "/units/" <> ns)
      expected = Enum.map(prior["inputs"], &{&1["namespace"], &1["sha256"]}) |> Enum.sort()
      actual = Enum.map(verified.manifest.inputs,
        &{&1.namespace, Base.encode16(&1.sha256, case: :lower)}) |> Enum.sort()
      unless actual == expected && verified.manifest.namespace == ns,
        do: raise("unit dependency inventory differs from verified artifact")
      File.cp_r!(previous <> "/units/" <> ns, destination)
      {verified, prior["inputs"], compiled, [ns | restored]}
    else
      workspace = BeamLisp.AOT.open_workspace(%{
        :"phase-imports" => [{:symbol, "core"}, {:symbol, "sugar"}], version: 2,
        roots: [priv], sources: [%{namespace: {:symbol, ns}, file: path}]}, %{})
      try do
        prepared = BeamLisp.AOT.prepare_unit(workspace, {:symbol, ns})
        BeamLisp.AOT.emit_unit(prepared, destination)
        inputs = Enum.map(prepared.inputs, fn {name, input} ->
          %{namespace: name, file: Path.relative_to(input.file, priv), sha256: sha.(input.source)}
        end) |> Enum.sort_by(& &1.namespace)
        {BeamLisp.AOT.verify_unit(destination), inputs, [ns | compiled], restored}
      after
        BeamLisp.AOT.close_workspace!(workspace)
      end
    end
    unless Enum.any?(verified.manifest.inputs, &(&1.namespace == ns)),
      do: raise("unit does not capture its own Source")
    for {module, bytes} <- verified.beams,
      do: File.write!(root <> "/ebin/" <> Atom.to_string(module) <> ".beam", bytes)
    row = %{modules: Enum.map(verified.beams, &elem(&1, 0))}
    {Map.put(entries, ns, %{file: Path.relative_to(path, priv), inputs: inputs}),
     Map.put(manifest, path, row), compiled, restored}
  end)
unless before_env == BeamLisp.Env.capture(), do: raise("production changed receiving environment")
calls = elem(:erlang.trace_info(pattern, :call_count), 1)
unless calls == length(compiled), do: raise("reported compilation count differs from actual calls")
unless frozen == snapshot.(), do: raise("SDK Source changed during production")
inventory = BeamLisp.AOT.write_sdk_inventory!(priv, manifest, root <> "/ebin", priv <> "/sdk-code.term")
File.cp_r!(root, out <> "/image")
# This is a sealed fragment, not a fallback source checkout. Omitted/deleted
# units cannot reappear through source loading in the resulting image.
for path <- Path.wildcard(out <> "/image/priv/**/*"), File.regular?(path),
    String.ends_with?(path, [".bl", ".bl.md", ".bl.org", ".clj", ".cljc", ".ex", ".exs", ".rs"]),
    do: File.rm!(path)
File.write!(out <> "/index.json", Jason.encode!(%{version: 1, runtime: runtime,
  compiler: config["compiler"], dependencies: config["dependencies"], baseline: config["baseline"], units: entries}))
File.write!(out <> "/result.json", Jason.encode!(%{version: 1, kind: "incremental-sdk-fragment",
  compiled: Enum.reverse(compiled), restored: Enum.reverse(restored), compile_calls: calls,
  removed: if(old, do: Map.keys(old["units"]) -- Map.keys(entries), else: []),
  compiler: config["compiler"], dependencies: config["dependencies"], compiler_key: key,
  sdk_modules: inventory}))
# Clocks belong in build logs; immutable products must reproduce exactly.
timing = %{milliseconds: System.monotonic_time(:millisecond) - started}
IO.puts("INCREMENTAL-SDK " <> Jason.encode!(Map.merge(Jason.decode!(File.read!(out <> "/result.json")), timing)))
