-module(rc_observe).
-moduledoc """
Look at the resource-cycle collector the way a developer debugs a leak.

  summary()        one line: live / rounds / collected / aborted / last round
  why(Resource)    the path from a ROOT (held from outside) to Resource --
                   the answer to "why is this still alive?"
  garbage()        resources the next round would free, right now
  dot(File)        the traced-resource graph as Graphviz (roots green,
                   live grey, garbage red), edges as held references
  watch(Ms)        print every round's summary for Ms milliseconds

Everything reads the collector's own view (system_flag(resource_cycles,
{graph, Pid}): a dry full round), so what you see is what it will decide.
No NIF is involved: rc_ctl wraps system_info/system_flag.
""".
-export([summary/0, why/1, garbage/0, dot/1, watch/1, snapshot/0]).

summary() ->
    case erlang:system_info(resource_cycles) of
        #{live := L, rounds := R, collected := C, aborted := A,
          last := #{kind := K, nodes := N, garbage := G, usec := U}} ->
            io:format("live=~p rounds=~p collected=~p aborted=~p "
                      "last: ~p nodes=~p garbage=~p ~pus~n",
                      [L, R, C, A, K, N, G, U])
    end.

snapshot() ->
    #{nodes := Nodes, edges := Edges, parent := Parents} = rc_ctl:graph(),
    {list_to_tuple(Nodes), Edges, list_to_tuple(Parents)}.

why(Resource) ->
    {Nodes, _Edges, Parents} = snapshot(),
    case index_of(Resource, Nodes) of
        none -> not_traced;
        Ix -> path(Ix, Nodes, Parents, [])
    end.

path(Ix, Nodes, Parents, Acc) ->
    N = element(Ix + 1, Nodes),
    Step = maps:with([verdict, refc, internal, outside], N),
    case {maps:get(verdict, N), element(Ix + 1, Parents)} of
        {garbage, _} -> {garbage, [Step]};
        {root, _} -> {alive, [Step#{held_from_outside => maps:get(outside, N)}
                              | Acc]};
        {live, P} -> path(P, Nodes, Parents, [Step | Acc])
    end.

garbage() ->
    {Nodes, _, _} = snapshot(),
    [maps:get(resource, N) || N <- tuple_to_list(Nodes),
                              maps:get(verdict, N) =:= garbage].

index_of(R, Nodes) -> index_of(R, Nodes, 1).
index_of(_, Nodes, I) when I > tuple_size(Nodes) -> none;
index_of(R, Nodes, I) ->
    case maps:get(resource, element(I, Nodes)) of
        R -> I - 1;
        _ -> index_of(R, Nodes, I + 1)
    end.

dot(File) ->
    {Nodes, Edges, _} = snapshot(),
    Colour = #{root => "palegreen", live => "lightgrey", garbage => "salmon"},
    NodeLines =
        [io_lib:format("  n~p [label=\"~p\\nrefc=~p in=~p out=~p\" "
                       "style=filled fillcolor=~s];~n",
                       [I - 1, element(2, maps:get(type, N)), maps:get(refc, N),
                        maps:get(internal, N), maps:get(outside, N),
                        maps:get(maps:get(verdict, N), Colour)])
         || {I, N} <- lists:enumerate(tuple_to_list(Nodes))],
    EdgeLines = [io_lib:format("  n~p -> n~p;~n", [F, T]) || {F, T} <- Edges],
    ok = file:write_file(File, ["digraph resource_cycles {\n", NodeLines,
                                EdgeLines, "}\n"]),
    {nodes, tuple_size(Nodes), edges, length(Edges)}.

watch(Ms) ->
    ok = rc_ctl:subscribe(),
    Deadline = erlang:monotonic_time(millisecond) + Ms,
    watch_loop(Deadline),
    rc_ctl:unsubscribe().

watch_loop(Deadline) ->
    Left = Deadline - erlang:monotonic_time(millisecond),
    receive
        {resource_cycles, round, R} ->
            io:format("round ~p~n", [R]), watch_loop(Deadline)
    after max(Left, 0) -> ok
    end.
