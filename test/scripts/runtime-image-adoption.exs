# Exercise actual native phase boundaries with the existing fences and mailbox.
# The metadata comes from a genuine captured floor; no SDK receipt is invented.
Application.ensure_all_started(:crypto)
{:ok, owner} = BeamLisp.Env.start_link([])
floor = BeamLisp.AOT.runtime_floor!()
prepared = floor.prepared
modules = Enum.map(prepared, fn {{module, _}, _} -> module end) |> Enum.sort()
identity = Enum.map(prepared, fn {{module, bytes}, _} -> {module, :crypto.hash(:sha256, bytes)} end)
fingerprints = Map.new(prepared, fn {{_, bytes}, _} -> {:ok, pair} = :beam_lib.md5(bytes); pair end)
# This is the normal publication phase. Receiver-owned acceptance follows it.
BeamLisp.Env.publish_binaries!(prepared)
parent = self()
wait = fn predicate ->
  Enum.reduce_while(1..1000, false, fn _, _ ->
    if predicate.(), do: {:halt, true}, else: (Process.sleep(5); {:cont, false})
  end)
end
count = fn ->
  :ets.tab2list(:beam_lisp_code_leases)
  |> Enum.count(fn {{module, lease_owner, _}, _} -> lease_owner == owner and module in modules end)
end
commit = fn -> BeamLisp.Env.commit_runtime_floor!(owner, modules, identity, floor.identity, fingerprints) end

# Contention is retried by the requester. The actual owner must stay responsive.
{holder, holder_monitor} = spawn_monitor(fn ->
  BeamLisp.Env.with_local_lock(:bl_code_lease_capacity_held, :bl_code_lease_capacity_lock, fn ->
    send(parent, :capacity_held)
    receive do :release -> :ok end
  end)
end)
receive do :capacity_held -> :ok after 5000 -> raise "capacity holder did not start" end
{caller, monitor} = spawn_monitor(commit)
try do
  unless wait.(fn ->
    case Process.info(caller, :current_stacktrace) do
      {:current_stacktrace, frames} -> Enum.any?(frames, fn {m, f, _, _} ->
        m == BeamLisp.Env and f == :wait_for_local_lock_retry
      end)
      _ -> false
    end
  end), do: raise("requester did not reach the outside-owner retry")
  :responsive = Agent.get(owner, fn _ -> :responsive end, 1000)
  unless count.() == 0, do: raise "contended acceptance retained code prematurely"
  Process.exit(caller, :kill)
  receive do {:DOWN, ^monitor, :process, ^caller, :killed} -> :ok after 5000 -> raise "caller did not die" end
  send(holder, :release)
  receive do {:DOWN, ^holder_monitor, :process, ^holder, :normal} -> :ok after 5000 -> raise "capacity holder did not release" end
  :absent = BeamLisp.Env.runtime_floor_state()
  unless count.() == 0, do: raise "unaccepted caller left a lease"
after
  if Process.alive?(caller), do: Process.exit(caller, :kill)
  send(holder, :release)
end

# Kill a requester after its real commit RPC is in Env's mailbox. The fixed
# owner turn must finish both retention and proof, with no caller continuation.
:erlang.suspend_process(owner)
{accepted, accepted_monitor} = spawn_monitor(commit)
try do
  queued = fn ->
    {:messages, messages} = Process.info(owner, :messages)
    Enum.find(messages, fn
      {:"$gen_call", {pid, _}, {:get, fun}} -> pid == accepted and is_function(fun)
      _ -> false
    end)
  end
  unless wait.(fn -> queued.() != nil end), do: raise "actual commit request was not queued"
  request_bytes = :erlang.external_size(queued.())
  unless request_bytes < 131_072, do: raise "raw program/floor bytes crossed the custody turn"
  Process.exit(accepted, :kill)
  receive do {:DOWN, ^accepted_monitor, :process, ^accepted, :killed} -> :ok after 5000 -> raise "accepted caller did not die" end
  :erlang.resume_process(owner)
  :ok = Agent.get(owner, fn _ -> :ok end)
  unless BeamLisp.Env.runtime_floor_key!() == floor.identity, do: raise "owner did not finish the image commit"
  :adopted = BeamLisp.Env.runtime_floor_state()
  unless count.() == length(modules), do: raise "image lease is incomplete or duplicated"
  BeamLisp.Env.put_key(:bl_runtime_initialized, true)
  # Stop a real initializer at the existing global publication fence. Death
  # must leave the image adopted, so another requester retries initialization.
  scope_holder = spawn(fn ->
    BeamLisp.Env.with_scope_lock(:global, fn ->
      send(parent, :scope_held)
      receive do :release -> :ok end
    end)
  end)
  receive do :scope_held -> :ok after 5000 -> raise "scope holder did not start" end
  {initializing, init_monitor} = spawn_monitor(fn -> BeamLisp.run_runtime_artifact("program", []) end)
  try do
    unless wait.(fn ->
      case Process.info(initializing, :current_stacktrace) do
        {:current_stacktrace, frames} -> Enum.any?(frames, fn {m, f, _, _} ->
          m == BeamLisp.Env and f == :with_local_lock
        end)
        _ -> false
      end
    end), do: raise("initializer did not reach the publication fence")
    :adopted = BeamLisp.Env.runtime_floor_state()
    Process.exit(initializing, :kill)
    receive do {:DOWN, ^init_monitor, :process, ^initializing, :killed} -> :ok after 5000 -> raise "initializer did not die" end
    send(scope_holder, :release)
    :adopted = BeamLisp.Env.runtime_floor_state()
  after
    if Process.alive?(initializing), do: Process.exit(initializing, :kill)
    send(scope_holder, :release)
  end
  [42, 99, 42] = BeamLisp.run_runtime_artifact("program", []) |> BeamLisp.Vector.to_list()
  42 = BeamLisp.Ns.Rt.invoke(BeamLisp.Env.fetch!("core", "+"), [40, 2])
  :ready = BeamLisp.Env.runtime_floor_state()
  unless count.() == length(modules), do: raise "initialization duplicated the adopted lease"
  false = BeamLisp.Env.seeded?()
  Agent.stop(owner)
  {:ok, replacement_owner} = BeamLisp.Env.start_link([])
  unless replacement_owner != owner, do: raise "Env epoch did not change"
  try do
    BeamLisp.Env.mark_runtime_initialized!(owner)
    raise "stale initializer completed a different Env epoch"
  rescue
    error in ErlangError ->
      unless Map.get(error, :original) == :runtime_floor_owner_changed, do: reraise(error, __STACKTRACE__)
  end
  :absent = BeamLisp.Env.runtime_floor_state()
  [42, 99, 42] = BeamLisp.run_runtime_artifact("program", []) |> BeamLisp.Vector.to_list()
  :ready = BeamLisp.Env.runtime_floor_state()
  IO.puts("RUNTIME-ADOPTION before-commit-death=true accepted-caller-death=true owner-responsive=true exact-lease=true private-initialization=true interrupted-initializer-retried=true stale-epoch-refused=true request-bytes=#{request_bytes}")
after
  if Process.info(owner, :status) == {:status, :suspended}, do: :erlang.resume_process(owner)
  if Process.alive?(accepted), do: Process.exit(accepted, :kill)
end
