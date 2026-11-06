for module <- [BeamLisp.AtomGuard,BeamLisp.Loader,BeamLisp.AOT] do
 path=Path.join(System.fetch_env!("PERF_COMPILED"),Atom.to_string(module) <> ".beam")
 {:module,^module}=:code.load_binary(module,String.to_charlist(path),File.read!(path))
end
root=BeamLisp.AOT.physical_sdk_path(BeamLisp.Tiers.priv_root())
path=BeamLisp.Loader.source_path("core")
workspace=BeamLisp.AOT.open_workspace(%{version: 2,"phase-imports": [{:symbol,"core"},{:symbol,"sugar"}],roots: [root],sources: [%{namespace: {:symbol,"core"},file: path}]},%{})
w=Process.get({:bl_artifact_workspace,workspace})
previous=BeamLisp.Env.capture();context=Process.get(:bl_sdk_constructor_context);view=BeamLisp.Env.fork(:global)
check=fn condition,message -> if not condition,do: raise(message) end
before_count=fn -> elem(:erlang.trace_info({BeamLisp.Ns.Reader,:read_string,2},:call_count),1) end
try do
 BeamLisp.Loader.without_initialization(fn -> BeamLisp.Env.with_env(view,fn ->
  Process.put(:bl_sdk_constructor_context,%{input: w.inputs["core"],"compiler-env": view,"artifact-workspace": workspace,"artifact-inputs": w.inputs,"phase-imports": w[:"phase-imports"],"phase-aware": true,units: %{},compiled: %{},compiling: BeamLisp.Set.new([]),clauses: %{},"seen-macros": BeamLisp.Set.new([]),"kernel-modules": BeamLisp.Set.new([]),"kernel-leases": [],"macro-steps": 16384,"new-atoms": 128,expanded: 0})
  BeamLisp.AOT.constructor_install_kernel!();BeamLisp.AOT.constructor_kernel_phase_state!()
  :erlang.trace_pattern({BeamLisp.Ns.Reader,:read_string,2},true,[:local,:call_count])
  BeamLisp.AOT.with_source_snapshot(fn ->
   source="(ns cache.guard) (defn answer [] 42) ^{:private true} hidden #_discarded #?(:clj branch :default ignored)"
   a=BeamLisp.AOT.constructor_read_forms(source,"cache.bl",:host)
   count=Process.get(BeamLisp.AtomGuard.count_key())
   check.(before_count.()==1,"first read did not parse once")
   b=BeamLisp.AOT.constructor_read_forms(source,"cache.bl",:bare)
   check.(a==b and before_count.()==1,"cross-entry reuse changed forms or reparsed")
   check.(count==Process.get(BeamLisp.AtomGuard.count_key()),"guard accounting/reset sequence changed")
   changed=BeamLisp.AOT.constructor_read_forms(String.replace(source,"42","43"),"cache.bl",:host)
   check.(changed != a and before_count.()==2,"changed bytes reused stale forms")
   attributed=BeamLisp.AOT.constructor_read_forms(source,"other.bl",:host)
   check.(attributed != a and before_count.()==3,"changed attribution reused stale forms")
   expected=BeamLisp.AOT.constructor_reader_direct(source,"other.bl",:host)
   check.(attributed==expected,"attribution differs from original reader")
   entries=map_size(Process.get(:bl_constructor_reader_cache).entries)
   for _ <- 1..2 do
    try do BeamLisp.AOT.constructor_read_forms("(ns", "invalid.bl",:host);raise "accepted invalid syntax" rescue e in BeamLisp.Reader.SyntaxError -> e end
    check.(map_size(Process.get(:bl_constructor_reader_cache).entries)==entries,"failed parse was cached")
    check.(Process.get(:bl_constructor_reader_guard_capture)==nil,"failed parse leaked guard recording")
   end
   interval=Application.get_env(:beam_lisp,:atom_check_interval)
   fraction=Application.get_env(:beam_lisp,:atom_high_water_fraction)
   try do
    Application.put_env(:beam_lisp,:atom_check_interval,1);Application.put_env(:beam_lisp,:atom_high_water_fraction,0.0)
    failed=before_count.()
    host=try do BeamLisp.AOT.constructor_read_forms(source,"cache.bl",:host);:accepted rescue e in BeamLisp.Reader.AtomLimitError -> e end
    check.(is_map(host),"cached host read skipped current atom limit")
    check.(before_count.()==failed,"high-water cache hit reparsed instead of replaying")
    check.(Process.get(BeamLisp.AtomGuard.count_key())==1,"refusal happened at a different guard event")
    bare=try do BeamLisp.AOT.constructor_read_forms(source,"cache.bl",:bare);:accepted rescue e in BeamLisp.AtomGuard.LimitError -> e end
    check.(is_map(bare),"bare read changed guard exception mapping")
   after
    if interval==nil,do: Application.delete_env(:beam_lisp,:atom_check_interval),else: Application.put_env(:beam_lisp,:atom_check_interval,interval)
    if fraction==nil,do: Application.delete_env(:beam_lisp,:atom_high_water_fraction),else: Application.put_env(:beam_lisp,:atom_high_water_fraction,fraction)
   end
   IO.puts("READER-GUARDS " <> Jason.encode!(%{status: "passed",guard_events: count,cache_entries: entries,cache_bytes: Process.get(:bl_constructor_reader_cache).bytes}))
  end)
  check.(Process.get(:bl_constructor_reader_cache)==nil,"Source pass retained reader cache")
 end) end)
after
 :erlang.trace_pattern({BeamLisp.Ns.Reader,:read_string,2},false,[:local,:call_count])
 for lease <- Process.get(:bl_sdk_constructor_context,%{})[:"kernel-leases"] || [],do: BeamLisp.Env.release_code!(lease)
 if context,do: Process.put(:bl_sdk_constructor_context,context),else: Process.delete(:bl_sdk_constructor_context)
 BeamLisp.Env.destroy(view);BeamLisp.Env.bind(previous);BeamLisp.AOT.close_workspace!(workspace)
end
nil
