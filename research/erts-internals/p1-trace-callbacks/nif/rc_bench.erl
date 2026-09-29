-module(rc_bench).
-moduledoc """
What the collector costs.

  alloc: time to create N cells, each holding a small term (stock vs patched:
         the patched path adds enif_resource_cycles_track -- one mutex + a hash
         insert).
  round live:  one collector round (the collector's own `usec`) over N LIVE
               acyclic cells -- the worst case: all traced, none freed.
  reclaim all: wall time from dropping N cells held in 2-cycles until every
               one is destroyed (rounds + clear + ERTS destructors).
Best of 5 per size. Prints a table; returns the rows.
""".
-export([main/0, run/0]).

main() -> run(), halt(0).

run() ->
    Api = rc_cell:api(),
    Sizes = [1000, 10000, 100000],
    Rows = [row(Api, N) || N <- Sizes],
    io:format("~n~-8s ~9s ~12s ~14s ~16s~n",
              ["api", "cells", "alloc us/op", "round live us", "reclaim all us"]),
    [io:format("~-8s ~9w ~12.3f ~14s ~16s~n",
               [Api, N, A, fmt(RL), fmt(RG)]) || {N, A, RL, RG} <- Rows],
    Rows.

fmt(none) -> "-";
fmt(X) -> integer_to_list(X).

row(Api, N) ->
    A = best(5, fun() -> alloc_us(N) end),
    {RL, RG} = case Api of
        patched -> {best(5, fun() -> round_live_us(N) end),
                    best(5, fun() -> round_garbage_us(N) end)};
        stock -> {none, none}
    end,
    {N, A, RL, RG}.

best(K, F) -> lists:min([F() || _ <- lists:seq(1, K)]).

alloc_us(N) ->
    erlang:garbage_collect(),
    {T, Cells} = timer:tc(fun() -> [rc_cell:new({v, I}) || I <- lists:seq(1, N)] end),
    _ = length(Cells),
    T / N.

last_usec() ->
    #{last := #{usec := U}} = erlang:system_info(resource_cycles),
    U.

round_live_us(N) ->
    Cells = [rc_cell:new({v, I}) || I <- lists:seq(1, N)],
    _ = rc_cell:collect(),
    U = last_usec(),
    _ = length(Cells),
    U.

%% End-to-end: from dropping N cells held in 2-cycles to every one of them
%% destroyed. Auto rounds (threshold) may already run during the build; this
%% measures what a program observes, not one round in isolation.
round_garbage_us(N) ->
    erlang:garbage_collect(),
    _ = rc_cell:collect(),
    Base = rc_cell:live(),
    (fun() -> [begin A = rc_cell:new(a), B = rc_cell:new(b),
                     rc_cell:put(A, B), rc_cell:put(B, A) end
               || _ <- lists:seq(1, N div 2)], ok end)(),
    erlang:garbage_collect(),
    T0 = erlang:monotonic_time(microsecond),
    _ = rc_cell:collect(),
    wait_down(Base),
    erlang:monotonic_time(microsecond) - T0.

wait_down(Base) ->
    case rc_cell:live() =< Base of
        true -> ok;
        false -> timer:sleep(1), wait_down(Base)
    end.
