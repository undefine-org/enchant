-module(rc_cell).
-moduledoc "Stubs for rc_cell.c; see that file for the contract.".
-export([new/1, put/2, get/1, live/0, api/0, plain/1]).
-nifs([new/1, put/2, get/1, live/0, api/0, plain/1]).
-on_load(init/0).

init() ->
    Dir = filename:dirname(code:which(?MODULE)),
    erlang:load_nif(filename:join(Dir, "rc_cell"), 0).

new(_) -> erlang:nif_error(not_loaded).
put(_, _) -> erlang:nif_error(not_loaded).
get(_) -> erlang:nif_error(not_loaded).
live() -> erlang:nif_error(not_loaded).
api() -> erlang:nif_error(not_loaded).
plain(_) -> erlang:nif_error(not_loaded).
