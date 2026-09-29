-module(rc_par).
-moduledoc "Parallel traced allocation: 8 processes x 50k cells (shard contention). Median of 5, ms.".
-export([run/0]).
run() ->
    F = fun() -> S = self(), T0 = erlang:monotonic_time(microsecond),
          Ps = [spawn_link(fun() -> L = [rc_cell:new(I) || I <- lists:seq(1, 50000)],
                                    S ! {d, self(), length(L)} end) || _ <- lists:seq(1, 8)],
          [receive {d, P, _} -> ok end || P <- Ps],
          erlang:monotonic_time(microsecond) - T0 end,
    Ts = lists:sort([F() || _ <- lists:seq(1, 5)]),
    io:format(" par8x50k_ms=~p", [lists:nth(3, Ts) div 1000]).
