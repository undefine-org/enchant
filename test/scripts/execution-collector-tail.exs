alias BeamLisp.LazyMemo, as: Memo
:ok = Memo.ensure_loaded!()
true = Memo.nif_loaded?()
true = Memo.nif_stats().cycle_enabled
for module <- [BeamLisp.Env, BeamLisp.Ns.Rt, BeamLisp.Ns.Core], do: false = :code.is_loaded(module)
await = fn await, action, deadline ->
  if action.() do
    :ok
  else
    if System.monotonic_time(:millisecond) >= deadline, do: raise("collector barrier timeout")
    Process.sleep(1)
    await.(await, action, deadline)
  end
end
# Direct calls make actual native resources/ledger entries. No native cycle
# collection or budget API is called during the measured window.
cycle = fn words ->
  a = Memo.nif_new(nil, [], 0)
  b = Memo.nif_new(a, [], 64)
  payload = {b, :erlang.make_tuple(words, 7), 42}
  :ok = Memo.nif_put(a, payload, :erts_debug.size(payload) * :erlang.system_info(:wordsize))
  a
end
live = cycle.(131072)
before = Memo.nif_stats()
parent = self()
{producer, monitor} = spawn_monitor(fn ->
  tail = cycle.(2097152)
  send(parent, :tail_rooted)
  receive do
    :release -> :erlang.phash2(tail)
  end
end)
receive do :tail_rooted -> :ok after 5000 -> raise "tail not rooted" end
folder = System.fetch_env!("BL_HISTORY_COLLECTOR_BARRIER")
await.(await, fn -> File.exists?(Path.join(folder, "round-finished")) end,
       System.monotonic_time(:millisecond) + 10000)
held = Memo.nif_stats()
true = held.retained_bytes >= before.retained_bytes + 16 * 1024 * 1024
true = held.cycle_runs == before.cycle_runs + 1
true = held.cycle_collected == before.cycle_collected
send(producer, :release)
receive do {:DOWN, ^monitor, :process, ^producer, :normal} -> :ok after 5000 -> raise "producer did not drop roots" end
:erlang.garbage_collect()
:ok = File.write(Path.join(folder, "continue"), "released")
mode = System.fetch_env!("BL_HISTORY_COLLECTOR_MODE")
if mode == "good" do
  await.(await, fn -> Memo.nif_stats().retained_bytes <= before.retained_bytes end,
         System.monotonic_time(:millisecond) + 5000)
else
  Process.sleep(600)
end
after_tail = Memo.nif_stats()
if mode == "good" do
  true = after_tail.cycle_runs == held.cycle_runs + 1
  true = after_tail.cycle_collected >= held.cycle_collected + 2
  true = after_tail.retained_bytes <= before.retained_bytes
else
  true = after_tail.cycle_runs == held.cycle_runs
  true = after_tail.cycle_collected == held.cycle_collected
  true = after_tail.retained_bytes == held.retained_bytes
end
# The successful follow-up settles once then sleeps; no idle polling rounds.
Process.sleep(250)
true = Memo.nif_stats().cycle_runs == after_tail.cycle_runs
{peer, payload, 42} = Memo.nif_read(live)
true = tuple_size(payload) == 131072
true = Memo.nif_read(peer) == live
true = after_tail.op_new - before.op_new == 2
for module <- [BeamLisp.Env, BeamLisp.Ns.Rt, BeamLisp.Ns.Core], do: false = :code.is_loaded(module)
IO.puts(Enum.join(["E50-RESULT", mode, before.retained_bytes, held.retained_bytes,
                   after_tail.retained_bytes, after_tail.cycle_runs - before.cycle_runs,
                   after_tail.cycle_collected - before.cycle_collected, Memo.nif_runtime_identity()], " "))
IO.puts("E50-NATIVE-TAIL-PASSED #{mode}")
