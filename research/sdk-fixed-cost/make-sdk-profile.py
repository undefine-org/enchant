from pathlib import Path
import json
root=Path.cwd()
source=(root/'scripts/produce-sdk.bl').read_text()
marker='(let [_ (selfbuild/timed'
assert source.count(marker)==1
start='''mods = [BeamLisp.AOT, BeamLisp.PackageAuthority, BeamLisp.Refs, BeamLisp.BuildPlan, File, :crypto, :beam_lib, :beam_disasm]
for mod <- mods do
  Code.ensure_loaded(mod)
  :erlang.trace_pattern({mod, :_, :_}, true, [:local, :call_time])
end
:erlang.trace(:all, true, [:call, :silent])
Process.put(:fixed_cost_profile_modules, mods)
'''
finish=''' :erlang.trace(:all, false, [:call, :silent])
rows = for mod <- Process.get(:fixed_cost_profile_modules), {fun, arity} <- mod.module_info(:functions),
  {:call_time, records} = :erlang.trace_info({mod, fun, arity}, :call_time), is_list(records), records != [] do
  {count, elapsed} = Enum.reduce(records, {0,0}, fn {_pid,n,sec,us},{c,t} -> {c+n,t+sec*1_000_000+us} end)
  %{function: inspect(mod) <> "." <> to_string(fun) <> "/" <> to_string(arity), calls: count, exclusive_us: elapsed}
end
rows = Enum.sort_by(rows, & &1.exclusive_us, :desc)
IO.puts("SDK-COST-PROFILE " <> Jason.encode!(Enum.take(rows, 100)))
'''
def bl(code):return '(erlang/apply :Elixir.Code :eval_string (list '+json.dumps(code)+'))\n'
out=root/'.local/fixed-cost/produce-sdk-profile.bl'
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(source.replace(marker,bl(start)+marker)+bl(finish))
