"""Generate a bounded sampler or call-time probe around real unit restoration."""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--mode', choices=['plain', 'sample', 'calls'], required=True)
parser.add_argument('--out', required=True, type=Path)
args = parser.parse_args()
start = finish = ''
if args.mode == 'sample':
    start = r'''
parent = self()
sampler = spawn(fn ->
  loop = fn loop, counts, iterations ->
    receive do
      {:finish, ref} -> send(parent, {:samples, ref, counts, iterations})
    after 10 ->
      counts = Enum.reduce(Process.list(), counts, fn pid, counts ->
        if pid == self() do counts else
          case Process.info(pid, [:status, :current_stacktrace]) do
            [status: status, current_stacktrace: stack] when status in [:running, :runnable] ->
              own = Enum.any?(stack, fn {m,_,_,_} -> String.starts_with?(Atom.to_string(m), "Elixir.BeamLisp") end)
              key = {status, Enum.take(stack, 12)}
              if own and (map_size(counts) < 8192 or Map.has_key?(counts, key)),
                do: Map.update(counts, key, 1, &(&1+1)), else: counts
            _ -> counts
          end
        end
      end)
      loop.(loop, counts, iterations+1)
    end
  end
  loop.(loop, %{}, 0)
end)
Process.put(:restoration_sampler, sampler)
'''
    finish = r'''
ref = make_ref(); send(Process.get(:restoration_sampler), {:finish, ref})
receive do
  {:samples, ^ref, counts, iterations} ->
    IO.puts("RESTORE-SAMPLES " <> Jason.encode!(%{iterations: iterations}))
    for {{status, stack}, count} <- Enum.take(Enum.sort_by(counts, &elem(&1,1), :desc), 100) do
      frames = Enum.map(stack, fn {m,f,a,where} -> %{module: Atom.to_string(m), function: Atom.to_string(f), arity: a, location: inspect(where)} end)
      IO.puts("RESTORE-SAMPLE " <> Jason.encode!(%{samples: count, status: status, frames: frames}))
    end
after 5000 -> raise "restoration sampler did not flush"
end
'''
elif args.mode == 'calls':
    start = '''mods = [BeamLisp.AOT, BeamLisp.Env, BeamLisp.LazySeq, BeamLisp.LazyMemo,
      BeamLisp.PackageAuthority, BeamLisp.Refs, BeamLisp.BuildPlan, File, :crypto, :beam_lib]
for mod <- mods do
  Code.ensure_loaded(mod)
  :erlang.trace_pattern({mod, :_, :_}, true, [:local, :call_time])
end
Process.put(:restoration_profile_modules, mods)
:erlang.trace(:all, true, [:call, :silent])
'''
    finish = ''' :erlang.trace(:all, false, [:call, :silent])
rows = for mod <- Process.get(:restoration_profile_modules), {fun,arity} <- mod.module_info(:functions),
  {:call_time, records} = :erlang.trace_info({mod,fun,arity}, :call_time), is_list(records), records != [] do
  {count,elapsed} = Enum.reduce(records,{0,0},fn {_pid,n,sec,us},{c,t} -> {c+n,t+sec*1_000_000+us} end)
  %{function: inspect(mod) <> "." <> to_string(fun) <> "/" <> to_string(arity), calls: count, exclusive_us: elapsed}
end
for row <- Enum.take(Enum.sort_by(rows,& &1.exclusive_us,:desc),100), do: IO.puts("RESTORE-CALL " <> Jason.encode!(row))
'''


def bl(code):
    return '(erlang/apply :Elixir.Code :eval_string (list '+json.dumps(code)+'))'


source = Path(__file__).with_name('restore.bl').read_text()
args.out.write_text(source.replace(';; PROFILE-START', bl(start) if start else '')
                   .replace(';; PROFILE-FINISH', bl(finish) if finish else ''))
