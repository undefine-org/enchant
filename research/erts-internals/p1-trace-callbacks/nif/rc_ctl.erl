-module(rc_ctl).
-moduledoc """
The resource-cycle collector from plain Erlang: no NIF involved.

Wraps erlang:system_info(resource_cycles) and
erlang:system_flag(resource_cycles, Op). On a stock emulator both raise
badarg; `available/0` answers false.

  info()          counters, policy, last round, per-type live/collected
  collect()       run a round that starts after this call; wait for it
  collect(full)   the same, examining every traced object
  graph()         a dry full round as data (nothing is cleared)
  subscribe()     receive {resource_cycles, round, RoundMap} after each round
  set(Key, Val)   auto | threshold | interval | budget -> old value
""".
-export([available/0, info/0, collect/0, collect/1, graph/0,
         subscribe/0, unsubscribe/0, set/2]).

available() ->
    try erlang:system_info(resource_cycles), true
    catch error:badarg -> false end.

info() -> erlang:system_info(resource_cycles).

collect() -> await(erlang:system_flag(resource_cycles, {collect, self()}),
                   collected).
collect(full) -> await(erlang:system_flag(resource_cycles,
                                          {collect, self(), full}),
                       collected).

graph() -> await(erlang:system_flag(resource_cycles, {graph, self()}), graph).

subscribe() -> erlang:system_flag(resource_cycles, {subscribe, self()}).
unsubscribe() -> erlang:system_flag(resource_cycles, {unsubscribe, self()}).

set(Key, Val) -> erlang:system_flag(resource_cycles, {Key, Val}).

await(Ref, Tag) ->
    receive {resource_cycles, Ref, Tag, Result} -> Result
    after 30000 -> error({resource_cycles_timeout, Tag})
    end.
