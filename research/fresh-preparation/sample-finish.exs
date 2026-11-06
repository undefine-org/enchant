ref=make_ref();send(Process.get(:perf_sampling_process),{:finish,ref})
receive do
  {:prep_samples,^ref,counts,dropped} ->
    IO.puts("PREP-SAMPLE-SUMMARY " <> Jason.encode!(%{distinct: map_size(counts),observations: Enum.sum(Map.values(counts)),dropped: dropped}))
    for {{status,frames},n} <- Enum.sort_by(counts,&elem(&1,1),:desc) do
      IO.puts("PREP-SAMPLE " <> Jason.encode!(%{status: status,samples: n,frames: Enum.map(frames,fn {m,f,a,line}->[Atom.to_string(m),Atom.to_string(f),a,line] end)}))
    end
after 3000 -> raise "sampler did not finish" end
