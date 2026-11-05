from pathlib import Path
import json
root=Path.cwd();source=(root/'.local/fixed-cost/produce-sdk.original').read_text();marker='(let [_ (selfbuild/timed';assert source.count(marker)==1
start=r'''
parent=self()
sampler=spawn(fn ->
 loop=fn loop, counts, records, iterations ->
  receive do
   {:finish,ref} ->
    rows=for {key,n} <- counts,do: %{samples: n,stack: Map.fetch!(records,key)}
    rows=Enum.sort_by(rows,& &1.samples,:desc)
    send(parent,{:sdk_samples,ref,%{iterations: iterations,rows: Enum.take(rows,100)}})
  after 10 ->
   {counts,records}=Enum.reduce(Process.list(),{counts,records},fn pid,{counts,records} ->
    if pid==self(),do: {counts,records},else:
     case Process.info(pid,[:status,:current_stacktrace]) do
      [status: status,current_stacktrace: stack] ->
       own=Enum.any?(stack,fn {m,_,_,_} -> String.starts_with?(Atom.to_string(m),"Elixir.BeamLisp") end)
       image=Enum.any?(stack,fn {m,_,_,_} -> String.contains?(Atom.to_string(m),"Build-image") end)
       if own and (status==:running or image) do
        value=%{status: status,image: image,frames: Enum.map(Enum.take(stack,12),fn {m,f,a,where} -> %{module: Atom.to_string(m),function: Atom.to_string(f),arity: a,location: inspect(where)} end)}
        key=:erlang.phash2(value)
        if map_size(counts)<8192 or Map.has_key?(counts,key),do: {Map.update(counts,key,1,&(&1+1)),Map.put(records,key,value)},else: {counts,records}
       else {counts,records} end
      _ -> {counts,records}
     end
   end)
   loop.(loop,counts,records,iterations+1)
  end
 end
 loop.(loop,%{},%{},0)
end)
Process.put(:fixed_cost_sdk_sampler,sampler)
'''
finish='''ref=make_ref();send(Process.get(:fixed_cost_sdk_sampler),{:finish,ref})
receive do {:sdk_samples,^ref,report} -> IO.puts("SDK-SAMPLE-PROFILE " <> Jason.encode!(report)) after 5000 -> raise "SDK sampler did not stop" end
'''
def bl(code):return '(erlang/apply :Elixir.Code :eval_string (list '+json.dumps(code)+'))\n'
(root/'.local/fixed-cost/produce-sdk-sampler.bl').write_text(source.replace(marker,bl(start)+marker)+bl(finish))
