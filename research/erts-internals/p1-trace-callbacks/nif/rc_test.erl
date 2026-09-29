-module(rc_test).
-moduledoc """
Probes for the ERTS resource-cycle collector, run on stock AND patched beam.

Each probe builds garbage (or live data) through rc_cell, drops every process
reference, forces a GC of the caller, asks for a fresh round and reads
rc_cell:live/0 (cells not yet destroyed). Destructors run as scheduler aux
work, so `settle/1` polls briefly.

  run()  -> [{Probe, pass | {fail, Detail}}]   and prints a table.
""".
-export([run/0, main/0]).

main() ->
    Results = run(),
    Failed = [P || {P, R} <- Results, R =/= pass, element(1, R) =/= pass],
    halt(case Failed of [] -> 0; _ -> 1 end).

run() ->
    Api = rc_cell:api(),
    io:format("emulator api: ~p~n", [Api]),
    Probes = [{self_cycle, fun self_cycle/1},
              {pair_cycle, fun pair_cycle/1},
              {ring_1000, fun ring/1},
              {cycle_through_closure, fun closure_cycle/1},
              {cycle_through_map_and_binary, fun map_cycle/1},
              {live_cycle_survives, fun live_cycle/1},
              {cycle_held_by_ets_survives, fun ets_cycle/1},
              {cycle_held_by_other_process_survives, fun remote_cycle/1},
              {acyclic_garbage_freed_by_refcount, fun acyclic/1},
              {reader_racing_rounds, fun racing_reader/1},
              {writer_racing_rounds, fun racing_writer/1},
              {graph_explains_liveness, fun graph_why/1},
              {subscription_delivers_rounds, fun subscription/1}],
    Results = [{Name, safe(F, Api)} || {Name, F} <- Probes],
    [io:format("  ~-40s ~p~n", [N, R]) || {N, R} <- Results],
    Results.

safe(F, Api) ->
    try F(Api) catch C:R:S -> {fail, {C, R, hd(S)}} end.

%% ---- helpers ---------------------------------------------------------------

%% Drop the caller's references: GC so the heap no longer counts them.
drop() -> erlang:garbage_collect(), ok.

%% Fresh round (patched) + let destructors (scheduler aux work) run.
settle(Api) -> settle(Api, 0).

%% Wait until at most `Target` cells are alive, or 3 s. A destructor is
%% scheduled as aux work and may start late, so "unchanged for a moment" is
%% NOT "done" -- only reaching the target is.
settle(Api, Target) ->
    drop(),
    case Api of patched -> rc_cell:collect(); stock -> ok end,
    wait_live(Target, 300).

wait_live(_, 0) -> rc_cell:live();
wait_live(Target, N) ->
    case rc_cell:live() of
        L when L =< Target -> L;
        _ -> timer:sleep(10), wait_live(Target, N - 1)
    end.

%% On stock the cycle leaks: the probe reports the baseline, not a failure.
expect_freed(Api, Before, _After, Made) ->
    After = settle(Api, Before),
    case {Api, After - Before} of
        {patched, 0} -> pass;
        {stock, Made} -> {pass, {leaked_on_stock, Made}};  % the baseline
        {_, D} -> {fail, #{api => Api, leaked => D, made => Made,
                           collector => diag(Api)}}
    end.

diag(stock) -> none;
diag(patched) ->
    maps:with([rounds, collected, aborted, live, last], rc_cell:info()).

%% ---- probes: garbage cycles are freed --------------------------------------

self_cycle(Api) ->
    B = settle(Api),
    [begin C = rc_cell:new(x), rc_cell:put(C, {self, C}) end
     || _ <- lists:seq(1, 100)],
    expect_freed(Api, B, settle(Api), 100).

pair_cycle(Api) ->
    B = settle(Api),
    [begin A = rc_cell:new(a), C = rc_cell:new(b),
           rc_cell:put(A, C), rc_cell:put(C, A) end
     || _ <- lists:seq(1, 50)],
    expect_freed(Api, B, settle(Api), 100).

ring(Api) ->
    B = settle(Api),
    make_ring(1000),
    expect_freed(Api, B, settle(Api), 1000).

make_ring(N) ->
    Cells = [rc_cell:new(I) || I <- lists:seq(1, N)],
    [First | _] = Cells,
    link_ring(Cells, First),
    ok.

link_ring([Last], First) -> rc_cell:put(Last, {next, First});
link_ring([A, B | Rest], First) ->
    rc_cell:put(A, {next, B}),
    link_ring([B | Rest], First).

%% The ETF census in the Rust collector needed term_to_binary to see a
%% closure's free variables; here ERTS's off-heap list sees them directly.
closure_cycle(Api) ->
    B = settle(Api),
    [begin C = rc_cell:new(x), rc_cell:put(C, fun() -> C end) end
     || _ <- lists:seq(1, 100)],
    expect_freed(Api, B, settle(Api), 100).

map_cycle(Api) ->
    B = settle(Api),
    [begin C = rc_cell:new(x),
           rc_cell:put(C, #{k => [C], pad => binary:copy(<<1>>, 200)}) end
     || _ <- lists:seq(1, 100)],
    expect_freed(Api, B, settle(Api), 100).

%% ---- probes: live data is never freed --------------------------------------

live_cycle(Api) ->
    A = rc_cell:new(a), C = rc_cell:new(b),
    rc_cell:put(A, C), rc_cell:put(C, A),
    _ = settle(Api), _ = settle(Api),
    case {rc_cell:get(A), rc_cell:get(rc_cell:get(A))} of
        {C, A} -> pass;
        Other -> {fail, Other}
    end.

ets_cycle(Api) ->
    T = ets:new(t, [public]),
    begin C = rc_cell:new(x), rc_cell:put(C, {self, C}), ets:insert(T, {k, C}) end,
    _ = settle(Api), _ = settle(Api),
    [{k, C2}] = ets:lookup(T, k),
    R = case rc_cell:get(C2) of {self, C2} -> pass; O -> {fail, O} end,
    ets:delete(T),
    R.

remote_cycle(Api) ->
    Self = self(),
    Holder = spawn(fun() ->
        C = rc_cell:new(x), rc_cell:put(C, {self, C}),
        Self ! {cell, C},
        receive stop -> ok end,
        _ = C
    end),
    C = receive {cell, X} -> X end,
    _ = settle(Api), _ = settle(Api),
    R = case rc_cell:get(C) of {self, C} -> pass; O -> {fail, O} end,
    Holder ! stop,
    R.

acyclic(Api) ->
    B = settle(Api),
    [begin A = rc_cell:new(x), rc_cell:put(A, rc_cell:new(y)) end
     || _ <- lists:seq(1, 100)],
    %% Freed by plain refcounting -- on stock AND patched.
    case settle(Api) - B of
        0 -> pass;
        D -> {fail, #{leaked => D}}
    end.

%% ---- probes: races ---------------------------------------------------------

%% A reader walks a live ring while rounds run back to back. It must never see
%% `reclaimed` -- that would mean the collector freed something reachable.
racing_reader(stock) -> pass;
racing_reader(patched) ->
    N = 200,
    Cells = [rc_cell:new(I) || I <- lists:seq(1, N)],
    link_ring(Cells, hd(Cells)),
    Start = hd(Cells),
    Self = self(),
    Reader = spawn_link(fun() -> Self ! {walked, walk(Start, 20000)} end),
    Collector = spawn_link(fun() -> collect_loop(40) end),
    R = receive {walked, W} -> W end,
    unlink(Collector), exit(Collector, kill), unlink(Reader),
    _ = Start,
    case R of ok -> pass; Bad -> {fail, Bad} end.

walk(_, 0) -> ok;
walk(C, K) ->
    case rc_cell:get(C) of
        {next, Next} -> walk(Next, K - 1);
        Other -> {reclaimed_while_reachable, Other}
    end.

collect_loop(0) -> ok;
collect_loop(K) -> rc_cell:collect(), collect_loop(K - 1).

%% A writer keeps rewiring a cycle it still holds, while rounds run.
racing_writer(stock) -> pass;
racing_writer(patched) ->
    A = rc_cell:new(a), C = rc_cell:new(b),
    Collector = spawn_link(fun() -> collect_loop(40) end),
    ok = rewire(A, C, 20000),
    unlink(Collector), exit(Collector, kill),
    case {rc_cell:get(A), rc_cell:get(C)} of
        {C, A} -> pass;
        Other -> {fail, Other}
    end.

rewire(_, _, 0) -> ok;
rewire(A, C, K) ->
    rc_cell:put(A, C), rc_cell:put(C, A),
    case rc_cell:get(A) of C -> rewire(A, C, K - 1); O -> {fail, O} end.

%% ---- probes: observability -------------------------------------------------

%% graph/0 must classify a held cycle as root/live and a dropped one as
%% garbage, with a parent chain explaining why the live one is alive.
graph_why(stock) -> pass;
graph_why(patched) ->
    _ = settle(patched),
    %% Build the pair in a callee so the caller's frame keeps ONLY Held;
    %% Inner is then alive solely through Held -> verdict `live`, parent Held.
    Held = (fun() -> H = rc_cell:new(held), I = rc_cell:new(inner),
                     rc_cell:put(H, I), rc_cell:put(I, H), H end)(),
    (fun() -> G = rc_cell:new(g), rc_cell:put(G, {self, G}) end)(),
    drop(),
    #{nodes := Nodes, parent := Parents, edges := Edges} = rc_cell:graph(),
    Verdicts = lists:sort([V || #{verdict := V} <- Nodes]),
    %% Held must be USED after the snapshot: `_ = Held` is dead code the
    %% compiler removes, and then the process really does not hold it.
    Held = rc_cell:get(rc_cell:get(Held)),
    Ok = Verdicts =:= [garbage, live, root]
         andalso length(Edges) =:= 3
         andalso length(Parents) =:= length(Nodes),
    case Ok of true -> pass; false -> {fail, #{verdicts => Verdicts,
                                               edges => Edges}} end.

subscription(stock) -> pass;
subscription(patched) ->
    ok = rc_cell:subscribe(self()),
    _ = rc_cell:collect(),
    R = receive {resource_cycles, #{round := N}} when N > 0 -> pass
        after 2000 -> {fail, no_message} end,
    ok = rc_cell:subscribe(undefined),
    flush(),
    R.

flush() -> receive {resource_cycles, _} -> flush() after 0 -> ok end.
