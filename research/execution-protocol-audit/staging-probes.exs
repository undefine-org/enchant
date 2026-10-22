# Research driver. All parsing, compilation, staging and emission use the real
# language. Erlang tracing observes names only; it changes no resolver or guard.
defmodule StagingResearch do
  alias BeamLisp.AOT

  def collect(events, count) do
    receive do
      {:trace, _, :call, {_, function, args}} ->
        row = %{event: "call", function: Atom.to_string(function),
                args: Enum.map(args, &inspect(&1, limit: 5, printable_limit: 160))}
        collect(Enum.take([row | events], 512), count + 1)
      {:trace, _, type, {_, function, _}, _} when type in [:return_from, :exception_from] ->
        row = %{event: Atom.to_string(type), function: Atom.to_string(function)}
        collect(Enum.take([row | events], 512), count + 1)
      {:finish, owner} ->
        send(owner, {:research_trace, %{events: Enum.reverse(events), total_events: count,
                                      truncated: count > 512}})
    end
  end

  def trace(fun) do
    if System.get_env("BL_RESEARCH_TRACE") == "off" do
      fun.()
    else
      traced(fun)
    end
  end

  def traced(fun) do
    tracer = spawn(fn -> collect([], 0) end)
    :erlang.trace(self(), true, [:call, {:tracer, tracer}])
    try do
      fun.()
    after
      :erlang.trace(self(), false, [:call])
      delivered = :erlang.trace_delivered(self())
      receive do {:trace_delivered, _, ^delivered} -> :ok after 5000 -> raise "trace drain timed out" end
      send(tracer, {:finish, self()})
      receive do {:research_trace, result} -> Process.put(:research_trace, result)
      after 5000 -> raise "trace collector timed out" end
    end
  end

  def identities do
    for {mod, _} <- :code.all_loaded(),
        String.starts_with?(Atom.to_string(mod), "Elixir.BeamLisp."),
        into: %{}, do: {mod, mod.module_info(:md5)}
  end

  def probe(id, namespace, sources) do
    output = System.fetch_env!("BL_ARTIFACT_OUTPUT")
    directory = Path.join(System.cwd!(), "probes/" <> id)
    File.mkdir_p!(directory)
    rows = Enum.map(sources, fn {ns, input} ->
      path = case input do
        {:file, path} -> path
        source ->
          path = Path.join(directory, ns <> ".bl")
          File.write!(path, String.replace(source, "__RESEARCH_MARKER__", Path.join(directory, "never-written")))
          path
      end
      %{namespace: {:symbol, ns}, file: path}
    end)
    before = identities()
    generations = BeamLisp.Env.namespace_generations(Enum.map(rows, fn row -> elem(row.namespace, 1) end))
    environment = BeamLisp.Env.capture()
    manifest = if System.get_env("BL_RESEARCH_PHASE_AWARE") == "on",
      do: %{:"phase-imports" => [{:symbol, "core"}, {:symbol, "sugar"}], version: 2, sources: rows},
      else: %{version: 1, sources: rows}
    handle = AOT.open_workspace(manifest, %{})
    started = System.monotonic_time(:microsecond)
    result = try do
      trace(fn ->
        prepared = AOT.prepare_unit(handle, {:symbol, namespace})
        artifact = AOT.emit_unit(prepared, Path.join(output, id))
        verified = AOT.verify_unit(Path.join(output, id))
        definitions = Map.fetch!(hd(prepared.plans), :definitions)
        literals = for {name, [{:fixed, 0, _, %{body: %{op: :lit, val: value}}, _}]} <- definitions,
                       name in ["answer", "probe"], into: %{}, do: {name, value}
        %{status: "emitted", modules: length(artifact.modules), literal_functions: literals,
          inputs: Enum.map(artifact.inputs, & &1.namespace),
          native_admission: verified[:"native-admission"],
          definitions: Enum.sort(Map.keys(definitions)),
          clauses: inspect(Map.take(definitions, ["answer", "probe"]), limit: 120, printable_limit: 3000)}
      end)
    rescue
      error -> %{status: "refused", kind: Map.get(Map.get(error, :data) || %{}, :kind),
                 data: inspect(Map.get(error, :data), limit: 80),
                 exception: inspect(error.__struct__), message: Exception.message(error)}
    after
      AOT.close_workspace!(handle)
    end
    after_identity = identities()
    unchanged = Enum.all?(before, fn {mod, digest} -> Map.get(after_identity, mod) == digest end)
    unchanged = unchanged and environment == BeamLisp.Env.capture() and
      generations == BeamLisp.Env.namespace_generations(Enum.map(rows, fn row -> elem(row.namespace, 1) end))
    unless unchanged, do: raise "research changed running identities/environment: #{id}"
    if File.exists?(Path.join(directory, "never-written")), do: raise "research executed a forbidden source effect"
    result = Map.merge(result, %{id: id, running_state_unchanged: unchanged,
      microseconds: System.monotonic_time(:microsecond) - started,
      source_sha256: Enum.map(rows, fn row ->
        %{namespace: elem(row.namespace, 1), sha256: Base.encode16(:crypto.hash(:sha256, File.read!(row.file)), case: :lower)}
      end), trace: Process.delete(:research_trace)})
    IO.puts("#{id}: #{result.status} #{Map.get(result, :data, "")}")
    File.write!(Path.join(output, id <> ".json"), Jason.encode!(result, pretty: true))
    result
  end

  def run do
    for {name, arity} <- [{:constructor_compile_binding!, 2}, {:constructor_remote_source, 3}, {:staged_macro_lookup, 2}] do
      :erlang.trace_pattern({AOT, name, arity}, [{:_, [], [{:exception_trace}]}], [:local])
    end
    cases = [
      {"rt-no-macro", "rt", "(ns rt) (defn empty? [x] (erlang/== x ())) (defn probe [] 42)"},
      {"rt-cond-leaf", "rt", "(ns rt) (defn empty? [x] (erlang/== x ())) (defn first [x] (erlang/hd x)) (defn eqv [a b] (erlang/== a b)) (defn nth [x i] (if (erlang/== i 0) (erlang/hd x) (nth (erlang/tl x) (erlang/- i 1)))) (defn probe [] (cond :else 42))"},
      {"rt-cond-cycle", "rt", "(ns rt) (defn empty? [x] (cond :else (erlang/== x ()))) (defn probe [] (cond :else 42))"},
      {"rt-cond-missing", "rt", "(ns rt) (defn probe [] (cond :else 42))"},
      {"neutral-cond", "research.neutral", "(ns research.neutral) (defn empty? [x] (cond :else (erlang/== x ()))) (defn probe [] (cond :else 42))"},
      {"recursive-helper", "research.recursive", "(ns research.recursive) (defn descend [n] (if (erlang/== n 0) 42 (descend (erlang/- n 1)))) (defmacro answer-form [] (list 'defn 'answer [] (descend 4))) (answer-form)"},
      {"mutual-helpers", "research.mutual", "(ns research.mutual) (defn left [n] (if (erlang/== n 0) 42 (right (erlang/- n 1)))) (defn right [n] (left n)) (defmacro answer-form [] (list 'defn 'answer [] (left 4))) (answer-form)"},
      {"value-cycle", "research.cycle", "(ns research.cycle) (def a b) (def b a) (defmacro demand [] a) (demand)"},
      {"macro-self-cycle", "research.macrocycle", "(ns research.macrocycle) (defmacro again [] (again)) (again)"},
      {"rt-invoke-source", "rt", "(ns rt) (defn invoke [f args] '(defn answer [] 99)) (defmacro make [] (BeamLisp.Ns.Rt/invoke (fn [] '(defn answer [] 42)) ())) (make)"},
      {"rt-invoke-implicit", "rt", "(ns rt) (defn invoke [f args] '(defn answer [] 99)) (defmacro make [] ((fn [] '(defn answer [] 42)))) (make)"},
      {"rt-selected-semantics", "rt", "(ns rt) (defn empty? [x] false) (defmacro choose [] (if (empty? ()) '(defn answer [] 1) '(defn answer [] 2))) (choose)"},
      {"macro-forward", "research.forward", "(ns research.forward) (defn probe [] (choose)) (defmacro choose [] 42)"},
      {"macro-first", "research.forward", "(ns research.forward) (defmacro choose [] 42) (defn probe [] (choose))"},
      {"effect-refused", "research.effect", "(ns research.effect) (defmacro touch [] (File/write! \"__RESEARCH_MARKER__\" \"bad\")) (touch)"}
    ]
    cases = if System.get_env("BL_RESEARCH_REVERSE") == "on", do: Enum.reverse(cases), else: cases
    results = Enum.map(cases, fn {id, ns, source} -> probe(id, ns, [{ns, source}]) end)
    runtime = "(ns rt) (defn empty? [x] (cond :else (erlang/== x ())))"
    results = results ++ [
      probe("rt-available", "research.client", [
        {"research.client", "(ns research.client) (defn probe [] (cond :else 42))"}, {"rt", runtime}]),
      probe("rt-unused-require", "research.client", [
        {"research.client", "(ns research.client (:require [rt])) (defn probe [] (cond :else 42))"}, {"rt", runtime}])
    ]
    boot = Path.join(BeamLisp.Tiers.priv_root(), "boot")
    results = results ++ Enum.map(Path.wildcard(Path.join(boot, "*.bl")), fn path ->
      ns = Path.basename(path, ".bl")
      probe("boot-" <> ns, ns, [{ns, {:file, path}}])
    end)
    results = results ++ [probe("boot-multi", "multi", [{"multi", {:file, Path.join(BeamLisp.Tiers.priv_root(), "std/multi.bl")}}])]
    # Compare actual compiler outputs after erasing diagnostic annotations only.
    strip = fn recurse, value ->
      cond do
        is_map(value) -> Map.new(Map.delete(value, :ann), fn {k,v} -> {k,recurse.(recurse,v)} end)
        is_list(value) -> Enum.map(value, &recurse.(recurse,&1))
        is_tuple(value) -> value |> Tuple.to_list() |> Enum.map(&recurse.(recurse,&1)) |> List.to_tuple()
        true -> value
      end
    end
    parse = fn source -> hd(BeamLisp.Reader.read_string(source)) end
    env = Map.put(BeamLisp.Compiler.new_env("user"), :locals, %{"f" => "f", "xs" => "xs"})
    compile = fn source -> strip.(strip, BeamLisp.Compiler.compile(parse.(source), env)) end
    implicit = compile.("(f)")
    explicit = compile.("(BeamLisp.Ns.Rt/invoke f ())")
    ir = %{implicit_invoke: inspect(implicit, limit: :infinity), explicit_invoke: inspect(explicit, limit: :infinity),
           same_invoke_ir: implicit == explicit,
           linked_empty: inspect(compile.("(empty? xs)"), limit: :infinity),
           explicit_empty: inspect(compile.("(BeamLisp.Ns.Rt/empty? xs)"), limit: :infinity)}
    expected = %{
      "rt-no-macro" => "emitted", "rt-cond-leaf" => "emitted", "rt-cond-cycle" => "refused",
      "rt-cond-missing" => "refused", "neutral-cond" => "emitted", "recursive-helper" => "emitted",
      "mutual-helpers" => "emitted", "value-cycle" => "refused", "macro-self-cycle" => "refused",
      "rt-invoke-source" => "emitted", "rt-invoke-implicit" => "emitted", "rt-selected-semantics" => "emitted",
      "macro-forward" => "refused", "macro-first" => "emitted", "effect-refused" => "refused",
      "rt-available" => "emitted", "rt-unused-require" => "refused", "boot-core" => "refused", "boot-rt" => "refused"
    }
    expected = if System.get_env("BL_RESEARCH_PHASE_AWARE") == "on",
      do: Map.merge(expected, Map.new(["rt-cond-cycle", "rt-cond-missing", "rt-unused-require", "boot-core", "boot-rt"], &{&1, "emitted"})),
      else: expected
    Enum.each(results, fn result ->
      unless result.status == Map.get(expected, result.id, "emitted"),
        do: raise "unexpected research observation: #{result.id}: #{result.status}"
    end)
    kinds = %{
      "rt-cond-cycle" => :"cyclic-sdk-constructor-compilation", "rt-cond-missing" => :"missing-sdk-constructor-definition",
      "value-cycle" => :"constructor-machine-refused", "macro-self-cycle" => :"cyclic-sdk-constructor-compilation",
      "macro-forward" => :"sdk-stage-local-macro-not-initialized", "effect-refused" => :"constructor-machine-refused",
      "rt-unused-require" => :"cyclic-sdk-constructor-compilation", "boot-core" => :"sdk-stage-local-macro-not-initialized",
      "boot-rt" => :"cyclic-sdk-constructor-compilation"
    }
    literals = %{"rt-cond-leaf" => %{"probe" => 42}, "neutral-cond" => %{"probe" => 42},
                 "recursive-helper" => %{"answer" => 42}, "mutual-helpers" => %{"answer" => 42},
                 "rt-invoke-source" => %{"answer" => 99}, "rt-invoke-implicit" => %{"answer" => 42},
                 "rt-selected-semantics" => %{"answer" => 2}, "macro-first" => %{"probe" => 42}}
    Enum.each(results, fn result ->
      if result.status == "refused" and Map.has_key?(kinds, result.id) and Map.get(result, :kind) != kinds[result.id],
        do: raise "refusal kind changed: #{result.id}"
      if Map.has_key?(literals, result.id) and result.literal_functions != literals[result.id],
        do: raise "literal result changed: #{result.id}"
    end)
    if ir.same_invoke_ir, do: raise "language invocation collapsed into a source remote"
    hosts = if System.get_env("BL_RESEARCH_HOSTS") == "on", do: host_probes(), else: []
    File.write!(Path.join(System.fetch_env!("BL_ARTIFACT_OUTPUT"), "result.json"), Jason.encode!(%{
      version: 1, scope: "staging-hypothesis-research", compiler_key: BeamLisp.AOTCache.current_compiler_key(),
      phase_aware: System.get_env("BL_RESEARCH_PHASE_AWARE") == "on",
      cases: results, hosts: hosts, ir: ir, self_reproduction_qualified: false}, pretty: true))
    if Enum.any?(hosts, &(&1.status != "emitted")), do: raise "some pinned host artifacts refused; see per-host receipts"
  end

  def host_probes do
    # The actual seed inventory supplies exact native names and ABI options.
    # This is ordinary producer-side tooling; candidate hosts are never loaded.
    BeamLisp.Loader.ensure_loaded("seed")
    entries = BeamLisp.Ns.Rt.invoke(BeamLisp.Env.fetch_exact!("seed", "host-sources"),
      [Path.join(BeamLisp.Tiers.priv_root(), "host")]) |> BeamLisp.CompilerData.eager_to_list()
    Enum.map(entries, fn entry ->
      namespace = BeamLisp.Loader.declared_ns(File.read!(entry.source))
      before = identities()
      generations = BeamLisp.Env.namespace_generations([namespace])
      environment = BeamLisp.Env.capture()
      handle = AOT.open_workspace(%{:"phase-imports" => [{:symbol, "core"}, {:symbol, "sugar"}],
        version: 2, sources: [%{namespace: {:symbol, namespace}, file: entry.source}]}, %{})
      spec = Map.drop(entry, [:source]) |> Map.put(:namespace, {:symbol, namespace})
      started = System.monotonic_time(:microsecond)
      directory = Path.join(System.fetch_env!("BL_ARTIFACT_OUTPUT"), "host-" <> Atom.to_string(entry.module))
      result = try do
        prepared = AOT.prepare_host_unit(handle, spec)
        manifest = AOT.emit_unit(prepared, directory)
        verified = AOT.verify_unit(directory)
        unless Enum.map(manifest.modules, & &1.module) == [Atom.to_string(entry.module)],
          do: raise "host artifact changed exact module membership"
        if verified[:"native-admission"], do: raise "host bytes acquired native admission"
        %{status: "emitted", module: Atom.to_string(entry.module),
          sha256: Base.encode16(hd(manifest.modules).sha256, case: :lower),
          budget: Map.take(Process.get({:bl_artifact_workspace, handle}).budget,
            [:remaining, :"walk-steps", :"allocation-nodes", :"allocation-bytes", :"fresh-symbols", :"new-atoms"])}
      rescue
        error -> %{status: "refused", module: Atom.to_string(entry.module),
          message: Exception.message(error), data: inspect(Map.get(error, :data), limit: 40),
          budget: Map.take(Process.get({:bl_artifact_workspace, handle}).budget,
            [:remaining, :"walk-steps", :"allocation-nodes", :"allocation-bytes", :"fresh-symbols", :"new-atoms"])}
      after
        AOT.close_workspace!(handle)
      end
      after_identity = identities()
      unchanged = Enum.all?(before, fn {mod, digest} -> Map.get(after_identity, mod) == digest end) and
        environment == BeamLisp.Env.capture() and generations == BeamLisp.Env.namespace_generations([namespace])
      unless unchanged, do: raise "host artifact preparation changed running code/environment: #{namespace}"
      result = Map.merge(result, %{running_state_unchanged: unchanged,
        source_sha256: Base.encode16(:crypto.hash(:sha256, File.read!(entry.source)), case: :lower),
        microseconds: System.monotonic_time(:microsecond) - started})
      File.write!(directory <> ".json", Jason.encode!(result, pretty: true))
      IO.puts("host #{entry.module}: #{result.status}")
      result
    end)
  end
end

StagingResearch.run()
