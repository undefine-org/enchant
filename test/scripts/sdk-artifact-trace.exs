# Native observer only. These are actual publication calls, not an admission
# row or a mock compiler. The receiving build result identifies its own targets.
parent = self()
tracer = spawn_link(fn ->
  loop = fn loop, publications ->
    receive do
      {:trace, _, :call, {BeamLisp.Env, :publish_binaries!, [prepared]}} ->
        next = Enum.reduce(prepared, publications, fn {{module, _bytes}, _file}, counts ->
          Map.update(counts, module, 1, &(&1 + 1))
        end)
        loop.(loop, next)
      {:finish, caller, ticket, targets} when caller == parent ->
        selected = Map.take(publications, targets)
        send(caller, {:sdk_artifact_publications, ticket,
                      %{targets: selected, all: publications}})
        loop.(loop, %{})
      {:trace, _, :call, _} -> loop.(loop, publications)
    end
  end
  loop.(loop, %{})
end)
Process.put(:sdk_artifact_tracer, tracer)
