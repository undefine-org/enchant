-module(rc_bench).
-moduledoc """
What the collector costs. Best of 5 per cell; prints a table.

  plain       alloc µs/op of an UNTRACED resource type (the cost every NIF
              pays whether or not it uses cycle collection)
  traced      alloc µs/op of a traced cell (link + track + first-release
              candidate push)
  par traced  the same from 8 processes at once (shard contention)
  1 in N      one round when 1 garbage pair is dropped among N live cells:
              v2 examines candidates only (`nodes` shows how many)
  full N      one round over N live cells (v1's only kind of round)
  reclaim N   from dropping N cells in 2-cycles to all destroyed

Runs on stock (plain/traced/par only), v1 and v2 (collect/graph via
rc_ctl on v2; v1 is detected and skipped for round columns).
""".
-export([main/0, run/0, full_round_us/1, one_in_n/1]).

main() -> run(), halt(0).

run() ->
    Api = rc_cell:api(),
    Kind = case {Api, rc_ctl:available()} of
               {stock, _} -> stock;
               {patched, true} -> try rc_ctl:set(budget, 65536) of
                                      _ -> v2
                                  catch error:badarg -> v1
                                  end
           end,
    Sizes = [1000, 10000, 100000],
    Rows = [row(Kind, N) || N <- Sizes],
    io:format("~n~-5s ~7s ~8s ~8s ~10s ~16s ~12s ~12s~n",
              ["emu", "cells", "plain", "traced", "par", "1-in-N us/nodes",
               "full us", "reclaim us"]),
    [io:format("~-5s ~7w ~8.2f ~8.2f ~10.2f ~16s ~12s ~12s~n",
               [Kind, N, P, T, Par, fmt(One), fmt(Full), fmt(Rec)])
     || {N, P, T, Par, One, Full, Rec} <- Rows],
    Rows.

fmt(none) -> "-";
fmt({U, Nodes}) -> io_lib:format("~w/~w", [U, Nodes]);
fmt(X) -> integer_to_list(X).

row(Kind, N) ->
    P = best(5, fun() -> alloc_us(fun rc_cell:plain/1, N) end),
    T = best(5, fun() -> alloc_us(fun rc_cell:new/1, N) end),
    Par = best(5, fun() -> par_alloc_us(N) end),
    case Kind of
        v2 -> {N, P, T, Par, best(5, fun() -> one_in_n(N) end),
               best(5, fun() -> full_round_us(N) end),
               best(5, fun() -> reclaim_us(N) end)};
        _ -> {N, P, T, Par, none, none, none}
    end.

best(K, F) -> lists:min([F() || _ <- lists:seq(1, K)]).

%% Keep `Live` reachable until here. `_ = length(Live)` is NOT enough: the
%% compiler drops it as dead code and the GC frees the cells early.
keep(Live) -> put({?MODULE, keep}, Live), Live.
release(Live) -> Live = erase({?MODULE, keep}), ok.

alloc_us(New, N) ->
    erlang:garbage_collect(),
    {T, Cells} = timer:tc(fun() -> [New({v, I}) || I <- lists:seq(1, N)] end),
    _ = length(Cells),
    T / N.

par_alloc_us(N) ->
    Self = self(),
    Per = N div 8,
    T0 = erlang:monotonic_time(microsecond),
    Pids = [spawn_link(fun() ->
                Cs = [rc_cell:new({v, I}) || I <- lists:seq(1, Per)],
                Self ! {done, self(), length(Cs)}
            end) || _ <- lists:seq(1, 8)],
    [receive {done, P, _} -> ok end || P <- Pids],
    (erlang:monotonic_time(microsecond) - T0) / (Per * 8).

drain() -> erlang:garbage_collect(), _ = rc_ctl:collect(), ok.

one_in_n(N) ->
    Live = keep([rc_cell:new({v, I}) || I <- lists:seq(1, N)]),
    drain(),
    (fun() -> A = rc_cell:new(a), B = rc_cell:new(b),
              rc_cell:put(A, B), rc_cell:put(B, A) end)(),
    erlang:garbage_collect(),
    #{usec := U, nodes := Nodes} = rc_ctl:collect(),
    release(Live),
    {U, Nodes}.

full_round_us(N) ->
    Live = keep([rc_cell:new({v, I}) || I <- lists:seq(1, N)]),
    drain(),
    #{usec := U, nodes := Nodes} = rc_ctl:collect(full),
    release(Live),
    {U, Nodes}.

reclaim_us(N) ->
    drain(),
    Base = rc_cell:live(),
    (fun() -> [begin A = rc_cell:new(a), B = rc_cell:new(b),
                     rc_cell:put(A, B), rc_cell:put(B, A) end
               || _ <- lists:seq(1, N div 2)], ok end)(),
    erlang:garbage_collect(),
    T0 = erlang:monotonic_time(microsecond),
    _ = rc_ctl:collect(),
    wait_down(Base),
    erlang:monotonic_time(microsecond) - T0.

wait_down(Base) ->
    case rc_cell:live() =< Base of
        true -> ok;
        false -> timer:sleep(1), wait_down(Base)
    end.
