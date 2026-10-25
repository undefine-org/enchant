# Private historical-control worker. Two instances share kernel lock inodes;
# neither changes a production module or the installed floor.
Application.load(:beam_lisp)
for app <- Application.spec(:beam_lisp, :applications) || [], do: {:ok, _} = Application.ensure_all_started(app)
BeamLisp.AOT.boot()
for ns <- ["claim", "build", "bl.cli"], do: BeamLisp.Loader.ensure_loaded(ns)

module = Module.concat([ExecutionHistory, CustodyWorker])
{:module, ^module, _, _} = defmodule module do
  def invoke(ns, name, args), do: BeamLisp.Ns.Rt.invoke(BeamLisp.Env.fetch_exact!(ns, name), args)

  def handle(%{"op" => "prepare", "cache_source" => cache, "build_source" => build, "cli_source" => cli, "output" => out}, state) do
    {ExecutionHistory.SharedRetirementProbe, path} = BeamLisp.AOT.compile_host_file(cache,
      module: ExecutionHistory.SharedRetirementProbe, output_dir: out, load?: false)
    {:module, ExecutionHistory.SharedRetirementProbe} = :code.load_binary(
      ExecutionHistory.SharedRetirementProbe, String.to_charlist(path), File.read!(path))
    BeamLisp.Compiler.eval_string(File.read!(build))
    BeamLisp.Compiler.eval_string(File.read!(cli))
    {state, %{prepared: true}}
  end

  def handle(%{"op" => "cli", "root" => root, "source" => source, "out" => out}, state) do
    ns = if state[:cli_mutant], do: "execution.history.claimless-cli", else: "bl.cli"
    BeamLisp.Loader.ensure_loaded("reload.events")
    before = Enum.count(invoke("reload.events", "journal", []))
    result = BeamLisp.with_cwd(root, fn -> invoke(ns, "run-argv", [["build", source, "--out", out, "--force", "--jobs", "1"]]) end)
    after_count = Enum.count(invoke("reload.events", "journal", []))
    {state, %{exit: result, events: after_count - before}}
  end

  def handle(%{"op" => "cli_mode", "mutant" => mutant}, state),
    do: {Map.put(state, :cli_mutant, mutant), %{mutant: mutant}}

  def handle(%{"op" => "build", "namespace" => ns, "source" => source, "out" => out}, state) do
    result = invoke(ns, "run", [%{sources: [source], out: out, jobs: 1, force?: true}])
    {state, %{built: result.built, errors: Enum.to_list(result.errors)}}
  end

  def handle(%{"op" => "artifact_scope", "destination" => destination}, state) do
    {state, %{scope: invoke("claim", "artifact-scope", [destination])}}
  end

  def handle(%{"op" => "native_scope", "project" => project, "crate" => crate}, state) do
    directory = Path.join([project, "native", crate])
    key = invoke("build", "native-key", [directory])
    root = invoke("build", "native-root", [])
    {state, %{scope: Path.join([root, key, crate])}}
  end

  def handle(%{"op" => "native_build", "project" => project, "crate" => crate}, state) do
    {state, invoke("build", "build-native-crate", [project, crate, nil])}
  end

  def handle(%{"op" => "claim", "out" => out}, state) do
    result = invoke("claim", "acquire!", [out, "independent writer"])
    context = if result[:"ok?"], do: invoke("claim", "follower-context", [out]), else: nil
    {state, %{acquired: result[:"ok?"], custody: get_in(result, [:held, :custody]),
              context: if(context, do: Base.encode64(:erlang.term_to_binary(context)))}}
  end

  def handle(%{"op" => "release", "out" => out}, state) do
    :ok = invoke("claim", "release!", [out])
    {state, %{released: true}}
  end

  def handle(%{"op" => "follow", "context" => bytes}, state) do
    context = :erlang.binary_to_term(Base.decode64!(bytes), [:safe])
    parent = self()
    {pid, monitor} = spawn_monitor(fn ->
      invoke("claim", "with-follower", [context, fn ->
        send(parent, {:held, self()})
        receive do: (:release -> :ok)
      end])
    end)
    receive do
      {:held, ^pid} -> {Map.put(state, :follower, {pid, monitor}), %{held: true}}
      {:DOWN, ^monitor, :process, ^pid, reason} -> raise "follower failed: #{inspect(reason)}"
    after 5000 -> raise "follower never entered"
    end
  end

  def handle(%{"op" => "release_follower"}, %{follower: {pid, monitor}} = state) do
    send(pid, :release)
    receive do
      {:DOWN, ^monitor, :process, ^pid, :normal} -> {Map.delete(state, :follower), %{released: true}}
      {:DOWN, ^monitor, :process, ^pid, reason} -> raise "follower failed: #{inspect(reason)}"
    after 5000 -> raise "follower did not finish"
    end
  end

  def handle(%{"op" => "late_follower", "context" => bytes}, state) do
    context = :erlang.binary_to_term(Base.decode64!(bytes), [:safe])
    Process.delete(:historical_follower_ran)
    result = try do
      invoke("claim", "with-follower", [context, fn -> Process.put(:historical_follower_ran, true) end])
      :accepted
    rescue
      error -> Map.get(error, :data, %{})[:kind]
    end
    {state, %{result: result, ran: Process.get(:historical_follower_ran, false)}}
  end

  def handle(%{"op" => "cache_root", "root" => root}, state) do
    System.put_env("BEAM_LISP_AOT_CACHE_DIR", root)
    Process.put(:"bl-osenv-overlay", %{"BEAM_LISP_AOT_CACHE_DIR" => root, "BEAM_LISP_AOT_CACHE" => "off"})
    {state, %{root: BeamLisp.AOTCache.dir()}}
  end

  def handle(%{"op" => "pin"}, state) do
    key = BeamLisp.AOTCache.compiler_key()
    :returned = BeamLisp.AOTCache.with_generation(key, fn -> :returned end)
    {state, %{key: key, idle: true}}
  end

  def handle(%{"op" => "hold_generation", "key" => key}, state) do
    parent = self()
    {pid, monitor} = spawn_monitor(fn ->
      BeamLisp.AOTCache.with_generation(key, fn ->
        send(parent, {:held, self()})
        receive do: (:release -> :ok)
      end)
    end)
    receive do
      {:held, ^pid} -> {Map.put(state, :generation, {pid, monitor}), %{held: true}}
      {:DOWN, ^monitor, :process, ^pid, reason} -> raise "generation failed: #{inspect(reason)}"
    after 5000 -> raise "generation never entered"
    end
  end

  def handle(%{"op" => "release_generation"}, %{generation: {pid, monitor}} = state) do
    send(pid, :release)
    receive do
      {:DOWN, ^monitor, :process, ^pid, :normal} -> {Map.delete(state, :generation), %{released: true}}
      {:DOWN, ^monitor, :process, ^pid, reason} -> raise "generation failed: #{inspect(reason)}"
    after 5000 -> raise "generation did not finish"
    end
  end

  def handle(%{"op" => "gc", "active" => active, "mutant" => mutant}, state) do
    module = if mutant, do: ExecutionHistory.SharedRetirementProbe, else: BeamLisp.AOTCache
    {:ok, deleted} = apply(module, :cleanup_obsolete_generations, [active, [keep_generations: 1, max_delete: 8]])
    {state, %{deleted: deleted}}
  end

  def loop(state) do
    case IO.gets("") do
      nil -> :ok
      line ->
        request = Jason.decode!(line)
        next = try do
          {next, value} = handle(request, state)
          IO.puts("BL-CUSTODY " <> Jason.encode!(%{id: request["id"], ok: true, value: value}))
          next
        rescue
          error ->
            IO.puts("BL-CUSTODY " <> Jason.encode!(%{id: request["id"], ok: false,
              error: Exception.format(:error, error, __STACKTRACE__)}))
            state
        end
        loop(next)
    end
  end
end

key = BeamLisp.AOTCache.current_compiler_key()
# Source-component development has no packaged-floor proof. Bind its exact
# loaded replacement host, NIF identity and Source instead. This test-only mode
# does not alter SDK admission or manufacture a compiler/floor authority row.
component = System.get_env("BL_CUSTODY_COMPONENT_IDENTITY")
identity_scope = if component do
  expected = Jason.decode!(component)
  actual = %{
    "scope" => "source-component",
    "root" => Path.expand(BeamLisp.Tiers.priv_root()),
    "compiler_key" => key,
    "native_identity" => BeamLisp.LazyMemo.runtime_identity!(),
    "memo_loaded_md5" => Base.encode16(BeamLisp.LazyMemo.module_info(:md5), case: :lower),
    "memo_beam_sha256" => Base.encode16(:crypto.hash(:sha256, File.read!(List.to_string(:code.which(BeamLisp.LazyMemo)))), case: :lower),
    "source_sha256" => Map.new(["build/claim.bl", "build/build.bl"], fn relative ->
      {relative, Base.encode16(:crypto.hash(:sha256, File.read!(Path.join(BeamLisp.Tiers.priv_root(), relative))), case: :lower)}
    end)
  }
  if actual != expected, do: raise("Source-component identity changed: #{inspect(actual)}")
  "source-component"
else
  {^key, _} = BeamLisp.Bootstrap.packaged_keys!()
  "packaged-floor"
end
IO.puts("BL-CUSTODY " <> Jason.encode!(%{ready: true, identity_scope: identity_scope, os_pid: System.pid(), compiler_key: key,
  root: BeamLisp.Tiers.priv_root(), native_identity: BeamLisp.LazyMemo.runtime_identity!(),
  manifest_sha256: Base.encode16(:crypto.hash(:sha256, File.read!(Path.join(BeamLisp.Tiers.priv_root(), "bootstrap/seed/manifest.term"))), case: :lower)}))
module.loop(%{})
