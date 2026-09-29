-module(rc_churn).
-moduledoc """
Worst case for candidate rounds: a long LIVE chain whose head is rewritten
10 000 times. Each rewrite drops a count on chain[1], so chain[1] becomes a
candidate that reaches the whole chain. Reports rounds, nodes examined, and
collector time; with budget B a partial round stops at B nodes and a full
round is scheduled only once enough candidates have passed to pay for it.
""".
-export([run/1]).
run(N) ->
    Cells = [rc_cell:new(I) || I <- lists:seq(1, N)],
    chain(Cells),
    put(keep, Cells),
    erlang:garbage_collect(), _ = rc_ctl:collect(full),
    ok = rc_ctl:subscribe(),
    #{rounds := R0, scanned := S0, overflows := O0} = rc_ctl:info(),
    Head = hd(Cells), Second = lists:nth(2, Cells),
    T0 = erlang:monotonic_time(microsecond),
    [rc_cell:put(Head, {next, Second, K}) || K <- lists:seq(1, 10000)],
    T1 = erlang:monotonic_time(microsecond),
    timer:sleep(1500),
    ok = rc_ctl:unsubscribe(),
    Rounds = drain([]),
    #{rounds := R1, scanned := S1, overflows := O1} = rc_ctl:info(),
    io:format("chain=~p puts=10000 mutator_us=~p rounds=~p scanned=~p "
              "collector_us=~p max_nodes=~p overflows=~p~n",
              [N, T1 - T0, R1 - R0, S1 - S0,
               lists:sum([maps:get(usec, M) || M <- Rounds]),
               lists:max([0 | [maps:get(nodes, M) || M <- Rounds]]), O1 - O0]),
    _ = erase(keep), ok.
chain([A, B | T]) -> rc_cell:put(A, {next, B}), chain([B | T]);
chain(_) -> ok.
drain(Acc) -> receive {resource_cycles, round, M} -> drain([M | Acc]) after 0 -> Acc end.
