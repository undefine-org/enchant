from pathlib import Path
root=Path.cwd();sdk=Path('/nix/store/w4aa6066zjkx78b591r21xn3fdg4fra0-beam-lisp-sdk-selection');out=root/'.local/fixed-cost'
code=r'''
invoke = BeamLisp.Launcher.default_seam(:invoke)
fetch = fn ns, name ->
 value = BeamLisp.Env.fetch!(ns,name)
 Process.put({:cost_name,value},ns <> "/" <> name)
 value
end
profile = fn value, argv ->
 for ns <- ["build", "application-product", "artifact"], do: BeamLisp.Loader.ensure_loaded(ns)
 parent=self()
 tracer=spawn(fn ->
  loop=fn loop, stacks, rows ->
   receive do
    {:trace_ts,pid,:call,{m,f,args},{a,b,c}} ->
     label=if f==:managed!,do: Path.basename(List.last(args)),else: Atom.to_string(m) <> "." <> Atom.to_string(f)
     loop.(loop,Map.update(stacks,pid,[{label,a*1_000_000_000_000+b*1_000_000+c}],fn old -> [{label,a*1_000_000_000_000+b*1_000_000+c}|old] end),rows)
    {:trace_ts,pid,:return_from,_mfa,_result,{a,b,c}} ->
     case Map.get(stacks,pid,[]) do
      [{label,started}|rest] -> loop.(loop,Map.put(stacks,pid,rest),[%{phase: label,elapsed_us: a*1_000_000_000_000+b*1_000_000+c-started}|rows])
      [] -> loop.(loop,stacks,rows)
     end
    {:finish,ref} -> send(parent,{:cost_rows,ref,Enum.reverse(rows)})
   end
  end
  loop.(loop,%{},[])
 end)
 patterns=[{BeamLisp.Ns.Body.Artifact,:managed!,6},{BeamLisp.Ns.Body.Artifact,:"verify-application!",3},
 {BeamLisp.Ns.Body.Artifact,:"prepare-application!",1},{:"Elixir.BeamLisp.Ns.Body.Application-product",:prepare!,1},
 {:"Elixir.BeamLisp.Ns.Body.Application-product",:select!,2},{:"Elixir.BeamLisp.Ns.Body.Application-product",:build!,1}]
 for p <- patterns,do: :erlang.trace_pattern(p,[{:_,[],[{:return_trace}]}],[:local])
 :erlang.trace(:all,true,[:call,:timestamp,{:tracer,tracer}])
 results=for repeat <- 1..3 do
  started=System.monotonic_time(:microsecond)
  result=invoke.(value,argv)
  %{repeat: repeat,result: inspect(result),elapsed_us: System.monotonic_time(:microsecond)-started}
 end
 :erlang.trace(:all,false,[:call])
 ref=make_ref();send(tracer,{:finish,ref})
 receive do {:cost_rows,^ref,rows} -> IO.puts("APPLICATION-COST-PROFILE " <> Jason.encode!(%{runs: results,phases: rows,memory: :erlang.memory(:total)})) after 5000 -> raise "cost tracer did not flush" end
 0
end
BeamLisp.Launcher.start_app!(System.argv(),%{fetch: fetch,invoke: fn value,argv ->
 if Process.get({:cost_name,value})=="bl.cli/run-argv",do: profile.(value,argv),else: invoke.(value,argv)
end})
'''
boot=(sdk/'boot.exs').read_text();assert boot.count('BeamLisp.Launcher.start_app!(System.argv(), %{})')==1
(out/'app-profile.exs').write_text(boot.replace('BeamLisp.Launcher.start_app!(System.argv(), %{})',code))
(out/'app-profile-bl').write_text((sdk/'bin/bl').read_text().replace(str(sdk/'boot.exs'),str(out/'app-profile.exs')))
(out/'app-profile-bl').chmod(0o755)
