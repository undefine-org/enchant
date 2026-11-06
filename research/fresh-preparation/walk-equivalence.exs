module=BeamLisp.AOT
path=Path.join(System.fetch_env!("PERF_COMPILED"),Atom.to_string(module) <> ".beam")
{:module,^module}=:code.load_binary(module,String.to_charlist(path),File.read!(path))
:rand.seed(:exsss,{919,124,2026})
leaf=fn -> Enum.at([nil,true,false,:atom,0,1,-12,3.5,"bytes",<<0,255>>,fn -> :never end],:rand.uniform(11)-1) end
gen=fn gen,depth ->
 if depth==0 do leaf.() else
  case :rand.uniform(5) do
   1 -> leaf.()
   2 -> for _ <- 1..:rand.uniform(4),do: gen.(gen,depth-1)
   3 -> List.to_tuple(for _ <- 1..:rand.uniform(4),do: gen.(gen,depth-1))
   4 -> Map.new(for n <- 1..:rand.uniform(4),do: {n,gen.(gen,depth-1)})
   5 -> %{__struct__: BeamLisp.UnknownConstructorContainer,value: gen.(gen,depth-1)}
  end
 end
end
nested=fn n -> Enum.reduce(1..n,:leaf,fn _,v->{v} end) end
random=for _ <- 1..600,do: gen.(gen,4)
boundaries=[List.duplicate(0,32767),List.duplicate(0,32768),Tuple.duplicate(0,65536),Tuple.duplicate(0,65537),:binary.copy("x",1048576),:binary.copy("x",1048577),nested.(128),nested.(129),Map.new(for n<-1..10000,do: {n,n}),BeamLisp.Vector.new([1,2,3]),BeamLisp.Set.new([1,2,3]),make_ref(),self()]
results=for {value,index} <- Enum.with_index(random++boundaries), fuel <- [0,1,10,1000000] do
 key={:walk_equivalence,make_ref()}
 Process.put(key,%{remaining: 2000000,"walk-steps": fuel,recipes: %{},callables: %{},exceptions: %{}})
 try do
  outcome=try do {:ok,BeamLisp.AOT.constructor_internal_cost_uncached!(value,%{:"counter-frame" => key})} catch kind,reason ->
   data=try do apply(BeamLisp.Ns.Core,:"ex-data",[reason]) catch _,_ -> nil end
   {:refused,kind,data}
  end
  counters=Process.get(key)
  {index,fuel,outcome,Map.take(counters,[:remaining,:"walk-steps"])}
 after Process.delete(key) end
end
bytes=:erlang.term_to_binary(results,[:deterministic])
File.write!(System.fetch_env!("PERF_EQ_OUT"),bytes)
IO.puts("WALK-EQUIVALENCE " <> Jason.encode!(%{cases: length(results),sha256: Base.encode16(:crypto.hash(:sha256,bytes),case: :lower),successes: Enum.count(results,fn {_,_,out,_}->elem(out,0)==:ok end)}))
