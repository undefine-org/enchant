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
ref = make_ref(); send(Process.get(:compiler_child_sampler), {:finish, ref})
receive do
  {:samples, ^ref, counts, iterations, dropped} ->
    rows = Enum.sort_by(counts, &elem(&1,1), :desc)
    observations = Enum.reduce(rows, 0, fn {_, count}, total -> total+count end)
    memory = File.read!("/proc/self/status") |> String.split("\n") |> Enum.filter(&String.starts_with?(&1, ["VmHWM:", "VmRSS:", "VmSwap:"]))
    IO.puts("CHILD-SAMPLES " <> Jason.encode!(%{iterations: iterations, observations: observations, distinct: map_size(counts), dropped: dropped, memory: memory, beam_memory: :erlang.memory(:total)}))
    for {{status, stack}, count} <- rows do
      frames = Enum.map(stack, fn {m,f,a,where} -> %{module: Atom.to_string(m), function: Atom.to_string(f), arity: a, location: inspect(where)} end)
      IO.puts("CHILD-SAMPLE " <> Jason.encode!(%{samples: count, status: status, frames: frames}))
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
driver = (root/'scripts/produce-sdk.bl').read_text()
marker = '(let [_ (selfbuild/timed'
assert driver.count(marker) == 1
header, body = driver.split(marker)
profile = (header+'\n(BeamLisp/eval '+json.dumps(shadow)+')\n'
           '(ns tooling.profile-produce-sdk (:require [profile-selfbuild :as selfbuild] [seed :as seed] [drop :as drop]))\n'
           +marker+body)
args.out.write_text(profile)
args.out.with_suffix('.start.exs').write_text(start)
args.out.with_suffix('.finish.exs').write_text(finish)
