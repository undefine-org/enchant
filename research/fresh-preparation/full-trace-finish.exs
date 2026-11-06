:erlang.trace(self(),false,[:call,:return_to,:monotonic_timestamp])
:erlang.trace_pattern({BeamLisp.AOT,:prepare_unit,2},false,[:local])
# Flush this process's trace messages before requesting the complete report.
ref=:erlang.trace_delivered(self())
receive do {:trace_delivered,_,^ref}->:ok after 3000->raise "trace flush failed" end
finished=make_ref();send(Process.get(:full_preparation_tracer),{:finish,finished})
receive do
 {:full_preparation,^finished,nil,rows} ->
  expected=String.to_integer(System.fetch_env!("PERF_EXPECT_UNITS"))
  if length(rows)!=expected,do: raise "preparation count #{length(rows)} != #{expected}"
  IO.puts("FULL-PREPARATION " <> Jason.encode!(%{units: length(rows),prepare_us: Enum.sum(Enum.map(rows,& &1.prepare_us))}))
 after 3000->raise "preparation tracer did not finish"
end
