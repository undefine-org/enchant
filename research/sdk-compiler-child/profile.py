"""Instrument the actual SDK compiler child without changing compiler inputs.

Only scripts/produce-sdk.bl changes in the private profiling checkout. It loads
the exact selfbuild Source under a private name, with sampling around the
existing child-produce call. The actual child, claims, inputs and artifact APIs
are unchanged. Restore the driver after production.
"""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root', type=Path, default=Path.cwd())
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
root = args.root.resolve()
start = r'''
Code.ensure_loaded!(BeamLisp.Reader)
:erlang.trace_pattern({BeamLisp.Reader, :read_string, 2}, true, [:local, :call_count])
patterns = [{BeamLisp.Reader, :read_string, 2}, {BeamLisp.Env, :fork, 1}, {BeamLisp.Env, :destroy, 1},
  {BeamLisp.AOT, :prepare_artifact_unit, 3}, {BeamLisp.AOT, :constructor_install_kernel!, 0},
  {BeamLisp.AOT, :constructor_kernel_phase_state!, 0}, {BeamLisp.AOT, :constructor_unit!, 1},
  {BeamLisp.AOT, :"stage-sdk-unit!", 2}, {BeamLisp.AOT, :compile_unit, 1},
  {BeamLisp.AOT, :seed_phase_library!, 2}, {BeamLisp.AOT, :seed_artifact_metadata!, 3},
  {BeamLisp.AOT, :capture_unit!, 2}, {BeamLisp.AOT, :artifact_inputs_valid!, 2},
  {BeamLisp.AOT, :constructor_metadata, 2}]
for pattern <- patterns, do: :erlang.trace_pattern(pattern, true, [:local, :call_time])
:erlang.trace(:all, true, [:call, :silent])
Process.put(:compiler_child_patterns, patterns)
parent = self()
sampler = spawn(fn ->
  loop = fn loop, counts, iterations, dropped ->
    receive do
      {:finish, ref} -> send(parent, {:samples, ref, counts, iterations, dropped})
    after 10 ->
      {counts, dropped} = Enum.reduce(Process.list(), {counts, dropped}, fn pid, {counts, dropped} ->
        if pid == self() do {counts, dropped} else
          case Process.info(pid, [:status, :current_stacktrace]) do
            [status: status, current_stacktrace: stack] when status in [:running, :runnable] ->
              own = Enum.any?(stack, fn {m,_,_,_} -> String.starts_with?(Atom.to_string(m), "Elixir.BeamLisp") end)
              key = {status, Enum.take(stack, 12)}
              cond do
                not own -> {counts, dropped}
                map_size(counts) < 8192 or Map.has_key?(counts, key) -> {Map.update(counts, key, 1, &(&1+1)), dropped}
                true -> {counts, dropped+1}
              end
            _ -> {counts, dropped}
          end
        end
      end)
      loop.(loop, counts, iterations+1, dropped)
    end
  end
  loop.(loop, %{}, 0, 0)
end)
Process.put(:compiler_child_sampler, sampler)
'''
finish = r'''
:erlang.trace(:all, false, [:call, :silent])
calls = for {mod, fun, arity} = pattern <- Process.get(:compiler_child_patterns),
  {:call_time, records} = :erlang.trace_info(pattern, :call_time), is_list(records), records != [] do
  {count, elapsed} = Enum.reduce(records, {0,0}, fn {_pid,n,sec,us},{c,t} -> {c+n,t+sec*1_000_000+us} end)
  %{function: inspect(mod) <> "." <> Atom.to_string(fun) <> "/" <> Integer.to_string(arity), calls: count, exclusive_us: elapsed}
end
for pattern <- Process.get(:compiler_child_patterns), do: :erlang.trace_pattern(pattern, false, [:local, :call_time])
for row <- Enum.sort_by(calls, & &1.exclusive_us, :desc), do: IO.puts("CHILD-CALL " <> Jason.encode!(row))
{:call_count, reader_calls} = :erlang.trace_info({BeamLisp.Reader, :read_string, 2}, :call_count)
:erlang.trace_pattern({BeamLisp.Reader, :read_string, 2}, false, [:local, :call_count])
ref = make_ref(); send(Process.get(:compiler_child_sampler), {:finish, ref})
receive do
  {:samples, ^ref, counts, iterations, dropped} ->
    rows = Enum.sort_by(counts, &elem(&1,1), :desc)
    observations = Enum.reduce(rows, 0, fn {_, count}, total -> total+count end)
    memory = File.read!("/proc/self/status") |> String.split("\n") |> Enum.filter(&String.starts_with?(&1, ["VmHWM:", "VmRSS:", "VmSwap:"]))
    IO.puts("CHILD-SAMPLES " <> Jason.encode!(%{iterations: iterations, observations: observations, distinct: map_size(counts), dropped: dropped, read_string_calls: reader_calls, memory: memory, beam_memory: :erlang.memory(:total)}))
    for {{{status, stack}, count}, id} <- Enum.with_index(rows) do
      IO.puts("CHILD-STACK " <> Jason.encode!(%{id: id, samples: count, status: status}))
      for {{m,f,a,where}, index} <- Enum.with_index(stack) do
        frame = %{module: Atom.to_string(m), function: Atom.to_string(f), arity: a, location: inspect(where)}
        encoded = Base.encode64(Jason.encode!(frame))
        last = div(byte_size(encoded)-1, 600)
        for part <- 0..last do
          chunk = binary_part(encoded, part*600, min(600, byte_size(encoded)-part*600))
          IO.puts("CHILD-FRAME " <> Jason.encode!(%{id: id, index: index, part: part, last: last, data: chunk}))
        end
      end
    end
after 5000 -> raise "compiler child sampler did not flush"
end
'''
source = (root/'priv/build/selfbuild.bl').read_text()
assert source.count('(ns selfbuild\n') == 1
lines = source.replace('(ns selfbuild\n', '(ns profile-selfbuild\n').splitlines()
before = next(i for i,line in enumerate(lines) if '"r = timed.' in line)
after = next(i for i,line in enumerate(lines) if '"File.write!(result,' in line)
lines.insert(after, '          '+json.dumps(finish))
lines.insert(before, '          '+json.dumps(start))
shadow = '\n'.join(lines)+'\n'
original_lines = source.splitlines()
patches = [('(ns selfbuild\n', '(ns profile-selfbuild\n'),
           (original_lines[before], '          '+json.dumps(start)+'\n'+original_lines[before]),
           (original_lines[after], '          '+json.dumps(finish)+'\n'+original_lines[after])]
check = source
bindings = ['source (File/read! "priv/build/selfbuild.bl")']
for old, new in patches:
    assert check.count(old) == 1
    check = check.replace(old, new)
    bindings.append('source (String/replace source '+json.dumps(old)+' '+json.dumps(new)+')')
assert check == shadow
driver = (root/'scripts/produce-sdk.bl').read_text()
marker = '(let [_ (selfbuild/timed'
assert driver.count(marker) == 1
header, body = driver.split(marker)
profile = (header+'\n(let ['+'\n       '.join(bindings)+'] (BeamLisp/eval source))\n'
           '(ns tooling.profile-produce-sdk (:require [profile-selfbuild :as selfbuild] [seed :as seed] [drop :as drop]))\n'
           +marker+body)
args.out.write_text(profile)
args.out.with_suffix('.start.exs').write_text(start)
args.out.with_suffix('.finish.exs').write_text(finish)
