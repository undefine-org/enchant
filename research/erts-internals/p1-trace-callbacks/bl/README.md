# `erts.rc` — the resource-cycle collector from beam-lisp

`bl/erts/rc.bl` is a beam-lisp namespace for **seeing and steering** the
ERTS resource-cycle collector (p1). It uses no NIF and no Elixir. It calls
two emulator entry points:

```clojure
(erlang/system_info :resource_cycles)             ; counters, policy, census
(erlang/system_flag :resource_cycles (tuple …))   ; requests and knobs
```

On a stock emulator both calls raise `badarg`. In that case `available?` is
`false`, and every other function returns `:unavailable` rather than
throwing. Library code can therefore call it unconditionally.

It lives in `research/` until `lazy_memo` registers hooks (p1 "Next steps").
At that point it moves to `priv/lib/erts/rc.bl` unchanged.

## Using it

Put the folder on the load path, e.g. an `env.bl` with
`:paths [".../p1-trace-callbacks/bl"]`, then:

```clojure
(ns my.app (:require [erts.rc :as rc]))

(rc/available?)          ;=> true on a patched emulator, false on stock
(rc/stats)               ;=> {:rounds 12 :collected 340 :live 1200 :pending 0
                         ;    :last-kind :partial :last-nodes 4 :last-usec 18 …}
(rc/types)               ;=> [{:module :rc_cell :name :rc_cell :live 1200 :collected 340}]
```

### "Did this leak?"

```clojure
(rc/leak-check #(run-my-workload))
;=> {:result … :delta {[:lazy_memo :MemoCell] 0}}   ; 0 = nothing left behind
```

`leak-check` settles the heap and runs rounds until the per-type census
stops moving, then does the same after `f`. Destructors run as scheduler aux
work, so it waits for the counts rather than trusting one read. It counts
**traced** resources only; cycles are included, because the collector is
what frees them.

### "Why is this still alive?"

```clojure
(rc/why cell)
;=> {:alive [{:verdict :root :outside 1 :refc 2 :internal 1 :type [:rc_cell :rc_cell] …}
;            {:verdict :live :outside 0 :refc 1 :internal 1 …}]}
```

The first step is the object held **from outside** the traced graph (a
process heap, ETS, a message, a native handle). The steps after it are the
chain of traced resources that reach `cell`. Other possible answers:

- `{:garbage step}`: the next round frees it;
- `:not-traced`: not a tracked resource.

The path is the collector's own BFS tree from a dry full round, so it is
exactly what the collector would decide.

### Look at the whole graph

```clojure
(def g (rc/graph))              ; dry full round: nothing is cleared
(rc/summary g)                  ;=> {[:rc_cell :rc_cell] {:root 2 :live 5 :garbage 1}}
(rc/garbage g)                  ;=> [#Ref<…>]  what the next round frees
(File/write! "rc.dot" (rc/dot g))   ; roots green, live grey, garbage red
```

Pass `g` to `why`, `garbage` and `summary` to answer several questions from
one snapshot. A graph is a full round (O(live) on the collector thread), so
don't poll it in a loop. `stats` and `watch` are cheap.

### Watch rounds as they happen

```clojure
(rc/watch 5000)   ;=> [{:round 41 :kind :partial :candidates 3 :nodes 3
                  ;     :garbage 2 :collected 2 :usec 14 :overflow false} …]
```

Or subscribe a long-lived process (up to 16 subscribers):

```clojure
(rc/subscribe!)   ; then (receive [:resource_cycles :round r] …)
(rc/unsubscribe!)
```

### Steer it

```clojure
(rc/collect!)              ; a round that starts after this call; returns it
(rc/collect! :full)        ; examine every traced object
(rc/set! :interval 20)     ; batch window, ms            → previous value
(rc/set! :threshold 1024)  ; per-scheduler candidates that cut the batch short
(rc/set! :budget 16384)    ; nodes a partial round may examine
(rc/set! :auto false)      ; no automatic rounds (requests still work)
(rc/with-policy {:auto false} (bench))   ; restored on every exit
```

## Round and graph shapes

| key | meaning |
|---|---|
| `:kind` | `:partial` (candidates and their reach) or `:full` (every traced object) |
| `:candidates` | objects recorded by releases since the last round |
| `:nodes` | objects the round examined (candidates plus what they reach) |
| `:roots` | nodes held from outside the graph, or opaque |
| `:garbage` / `:collected` | found unreachable / actually cleared after validation |
| `:aborted` | garbage candidates rejected because a racing reader or writer touched them (retried next round) |
| `:overflow` | the partial round hit `:budget`; a full round follows |
| `:usec` | the round's wall time on the collector thread |

In the graph, each node has:

| key | meaning |
|---|---|
| `:refc` | counts held on the node (the collector's own pin removed) |
| `:internal` | how many of those are held by traced resources in the graph |
| `:outside` | `refc − internal`; `> 0` makes the node a `:root` |
| `:verdict` | `:root`, `:live` or `:garbage` |

`:parent` is the BFS tree (`-1` for roots and garbage).

## Tests

`bl/rc_test.bl` has 7 deftests. The first one runs on any emulator; the
other six run only when the collector is available:

```sh
research/erts-internals/p1-trace-callbacks/run.sh bl
#   patched drop: 18 assertions pass; with DROP_STOCK=<stock drop>: 4 pass
```

The tests use `rc_cell` (the C probe NIF in `../nif`) as the traced type,
loaded from `RC_CELL_DIR` (set by `run.sh`).
