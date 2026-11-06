parent = self()
phase = :atomics.new(1, [])
Process.put(:perf_sampling_phase, phase)
sampler = spawn(fn ->
  loop = fn loop, counts, dropped ->
    receive do
      {:finish, ref} -> send(parent, {:prep_samples, ref, counts, dropped})
    after 10 ->
      {counts, dropped} = if :atomics.get(phase, 1) == 1 do
        Enum.reduce(Process.list(), {counts,dropped}, fn pid, {counts,dropped} ->
          case Process.info(pid, [:status,:current_stacktrace]) do
            [status: status,current_stacktrace: frames] ->
              own = Enum.any?(frames, fn {m,_,_,_} -> String.starts_with?(Atom.to_string(m), "Elixir.BeamLisp") end)
              if own and (pid == parent or status in [:running,:runnable]) do
                key = {status, Enum.map(Enum.take(frames,20),fn {m,f,a,where} -> {m,f,a,Keyword.get(where,:line)} end)}
                if map_size(counts) < 4096 or Map.has_key?(counts,key), do: {Map.update(counts,key,1,&(&1+1)),dropped}, else: {counts,dropped+1}
              else {counts,dropped} end
            _ -> {counts,dropped}
          end
        end)
      else {counts,dropped} end
      loop.(loop,counts,dropped)
    end
  end
  loop.(loop,%{},0)
end)
Process.put(:perf_sampling_process,sampler)
