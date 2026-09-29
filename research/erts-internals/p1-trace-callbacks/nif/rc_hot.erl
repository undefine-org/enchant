-module(rc_hot).
-export([run/1]).
run(Which) ->
    Bin = binary:copy(<<1>>, 4096),
    F = case Which of
        subbin -> fun() -> _ = lists:foldl(fun(_, A) -> [binary:part(Bin, 0, 100) | A] end, [], lists:seq(1, 200000)), erlang:garbage_collect() end;
        plain -> fun() -> _ = [rc_cell:plain(I) || I <- lists:seq(1, 100000)], erlang:garbage_collect() end;
        traced -> fun() -> _ = [rc_cell:new(I) || I <- lists:seq(1, 100000)], erlang:garbage_collect() end
    end,
    [F() || _ <- lists:seq(1, 10)], ok.
