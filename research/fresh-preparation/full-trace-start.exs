parent=self()
tracer=spawn(fn ->
 loop=fn loop,pending,rows ->
  receive do
   {:trace_ts,^parent,:call,{BeamLisp.AOT,:prepare_unit,[_handle,namespace]},started} -> loop.(loop,{namespace,started},rows)
   {:trace_ts,^parent,:return_to,_caller,ended} when pending != nil ->
    {namespace,started}=pending
    row=%{namespace: inspect(namespace),prepare_us: System.convert_time_unit(ended-started,:native,:microsecond)}
    IO.puts("FULL-PREPARE " <> Jason.encode!(row))
    loop.(loop,nil,[row|rows])
   {:finish,ref} -> send(parent,{:full_preparation,ref,pending,Enum.reverse(rows)})
   other -> raise "unexpected preparation event: #{inspect(other)}"
  end
 end
 loop.(loop,nil,[])
end)
:erlang.trace_pattern({BeamLisp.AOT,:prepare_unit,2},true,[:local])
:erlang.trace(self(),true,[:call,:return_to,:monotonic_timestamp,{:tracer,tracer}])
Process.put(:full_preparation_tracer,tracer)
