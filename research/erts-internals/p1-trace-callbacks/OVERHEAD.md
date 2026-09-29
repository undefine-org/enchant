# p1 v2 — removing the overhead and the global lock

v1 of the ERTS resource-cycle collector worked, but it had four costs:

- **(a)** a global mutex, taken on every traced allocation and every
  destruction;
- **(b)** two extra words in *every* NIF resource on the node, traced or not;
- **(c)** O(every traced object) work per collection round;
- **(d)** observability that only worked through NIF entry points, so you had
  to load a NIF just to look.

v2 removes all four **without dropping any guarantee**. Everything v1 freed,
v2 frees. Everything v1 kept alive, v2 keeps alive. The soundness argument
from the [README](README.md) §3 is unchanged in substance.

This page covers where each cost went, why it is safe, and the measurements.

- Patch: [`../otp/patches/0001-resource-cycles-trace-callbacks.patch`](../otp/patches/0001-resource-cycles-trace-callbacks.patch)
  (tracked tree: `~/.cache/bl/otp/otp-OTP-29.0.1`, commits `6ae441f` and `e8450ee` on top of
  v1 `b753189` and pristine `335a8b7`)
- Probes: `nif/rc_test.erl` (23)
- Benches:
  - `nif/rc_bench.erl`
  - `nif/rc_hot.erl`
  - `nif/rc_par.erl`
  - `nif/rc_churn.erl`

## 1. What v1 cost, and why

| cost | v1 mechanism | who paid |
|---|---|---|
| global lock | a single open-addressing hash set of tracked objects behind `rc_lock`: insert on `track`, delete in the destructor, and a full copy under the lock at every round | every traced alloc and destroy, on every scheduler, serialised |
| 2 words per resource | `ErtsResource` gained `rc_type` and `rc_tracked` | **every NIF resource on the node** (crypto, ssl, every library), not only traced ones |
| O(live) rounds | trial deletion over a snapshot of *everything tracked* | the collector thread: 50 ms per round at 100k live cells, one round per "threshold" allocations |
| NIF-only observability | `enif_resource_cycles_info/graph/collect/subscribe` | anyone who wanted to look had to write or load a NIF |

The bench numbers made (a) concrete. Eight processes allocating 50k traced
cells each took **1.3–1.5 s on v1 against ~0.4–0.6 s pristine**, because
every allocation queued on one mutex.

## 2. The v2 design, cost by cost

### (a) No global lock: per-scheduler shards

Every scheduler (normal, dirty-CPU and dirty-IO), plus one slot for unmanaged
threads, owns a **shard**, padded to a cache line:

```
RcShard { mutex lock;          // census list only
          RcLink head;         // census: tracked objects (for full rounds)
          atomic stack;        // candidate stack (Treiber, lock-free push)
          atomic pending;      // pushes since the last drain
          atomic inflight; }   // releases in progress (see §4)
```

- **`track`** links the object into the calling scheduler's census list. The
  lock is the scheduler's own, so the only contention is with the collector
  when it walks that shard.
- **Destruction** unlinks the object from the shard it was tracked on, which
  is recorded in the object's link.
- **Candidate pushes** are one CAS on the local stack; no lock.
- **The collector** drains each stack with a single `xchg`.
- **The census walk** (full rounds and graphs only) drops the shard lock every
  256 objects and keeps its place with a cursor node in the list. It never
  holds a scheduler's lock for more than one batch.

The remaining **cold** state (the type list, subscribers, requests, the last
round's stats) sits behind `rc_ctl`. That lock is taken only by
`set_hooks`, `system_info` / `system_flag`, and the collector thread. **No
allocation, release or destruction path takes `rc_ctl`.**

### (b) Untraced resources pay nothing: the link lives at the end of traced objects only

v2 removes both words from `ErtsResource`. A traced type (one that called
`enif_set_resource_cycle_hooks`) gets an `RcLink` appended **after the user
data** (and after the monitor block, if any). The link is 56 bytes and holds:

- the census links;
- the stack link;
- a back pointer;
- the type;
- a state word;
- the shard number;
- the user data size.

The binary carries a new flag, `BIN_FLAG_RC_TRACED`. It is set at allocation,
before the object is published.

`enif_alloc_resource` gains one predictable branch (`type->rc != NULL`).
`enif_sizeof_resource` returns the stored user size for traced objects, so a
NIF sees exactly the size it asked for. `global.h` changes by **one pointer
in `ErlNifResourceType`** (not in each resource).

### (c) O(candidates) rounds: Bacon–Rajan candidate roots

A garbage cycle comes into existence at the last *external* decrement of one
of its members. That decrement leaves the count above zero, because the
cycle's own edges still hold it. So **every release that leaves a traced
object's count above zero records the object as a candidate**. A round
examines the candidates and what they reach, and nothing else.

Recording on release requires that every place ERTS drops a count goes
through a hook. The audit (every `refc_dec*` / `bin_release` / `bin_free` on
`intern.refc` in `erts/emulator/beam`) found that they all funnel into
`erts_bin_release()`. That covers:

- the process GC sweep;
- message, heap-fragment and env cleanup (`erts_cleanup_offheap_list`);
- ETS (`db_cleanup_offheap_comp`, `erts_cleanup_offheap`);
- `enif_release_resource`;
- persistent_term literal areas;
- port data;
- dist.

The only exceptions were three raw sites, which v2 routes through it:

- `erts_iref_storage_clean` (`erl_bif_unique.h`, now via `erts_ref_bin_release`);
- `free_binary` (`erl_io_queue.c`);
- `enif_free_iovec` (`erl_nif.c`).

The fourth decrement site is `driver_binary_dec_refc` (`io.c`), which must
return the new count. It calls the traced variant `erts_rc_dec_refc` instead.

```c
erts_bin_release(Binary *bp) {
    if (ERTS_UNLIKELY(bp->intern.flags & BIN_FLAG_RC_TRACED)) {  // +1 load, +1 test
        erts_rc_release(bp);
        return;
    }
    ...unchanged...
}
```

`erts_rc_release` (traced objects only):

- If the count is > 1 (so this release will not free the object) and the
  object is tracked and not already buffered, it sets `BUFFERED` with one
  atomic OR and pushes the object once. The candidate is deduplicated.
- It then decrements.
- The flag and the push happen **while the releaser still holds its count**,
  so the object cannot be freed under the push.

**The round**, per candidate:

1. Pin the candidate: refc++ unless 0 (dying objects are never resurrected).
2. Trace it. Each traced, tracked target not yet in the round is pinned and
   added. This is safe because the holder being traced holds a count and is
   locked by its own `trace` callback.
3. Everything else is unchanged from v1: outside counts, BFS marking, the
   A-then-B validation, and clearing.

A node **outside** the round that holds a count on a node inside it shows up
as `outside > 0`, which makes the inside node a root. Seeing too much as a
root is **always safe**. It only means the next round with the right
candidates frees that node.

**The budget.** A partial round adds at most `budget` nodes (default 65 536).
Past that, untraced nodes become opaque roots, so the round stays sound but
may be incomplete. The round then:

- records those nodes again, so they are retried;
- counts an `overflow`;
- asks for one **full** round (a census snapshot with no budget) once the
  candidates that have passed since the last full round add up to the live
  count. That makes the full-round cost amortised O(1) per candidate.

An explicit `collect` request that overflows runs the full round immediately,
so a caller that asks for a collection always gets a complete one.

**Freed-while-buffered.** An object whose count reaches zero while it sits on
a stack keeps its memory until the collector drains the stack. Two paths race
here, and each does one atomic read-modify-write:

- the destructor does `DEAD |= …` and frees the memory only if `BUFFERED` was
  clear;
- the drain does `BUFFERED &= ~…` and frees the memory only if `DEAD` was set
  and the pin failed.

Exactly one party frees. The *user destructor* still runs at the usual time;
only the ERTS block outlives it by up to one drain.

### (d) Observability without a NIF

The NIF entry points are gone. Everything goes through the emulator:

```erlang
erlang:system_info(resource_cycles) -> #{enabled, auto, rounds, full_rounds,
    collected, aborted, overflows, candidates, scanned, live, pending,
    threshold, interval_ms, budget, shards, last => Round, types => [...]}

erlang:system_flag(resource_cycles, Op)
  {collect, Pid} | {collect, Pid, full} -> Ref
       Pid ! {resource_cycles, Ref, collected, Round}
  {graph, Pid} -> Ref                     %% dry full round, nothing cleared
       Pid ! {resource_cycles, Ref, graph, #{nodes, edges, parent}}
  {subscribe, Pid} | {unsubscribe, Pid} -> ok     %% up to 16 subscribers
       Pid ! {resource_cycles, round, Round}      %% after every round
  {auto, Bool} | {threshold, N} | {interval, Ms} | {budget, N} -> Old
```

Requests are asynchronous. The BIF enqueues the request and wakes the
collector; the reply arrives as a message. That means a long round never
blocks a scheduler, and a request never needs a dirty NIF.

`Round` is:

```erlang
#{round, kind => partial | full, candidates, nodes, roots, garbage,
  collected, aborted, opaque, overflow, usec}
```

`rc_ctl.erl` wraps these calls for Erlang, and `bl/erts/rc.bl` wraps them for
beam-lisp.

### The collector thread's schedule

Idle costs nothing. With no candidates pending, the thread sleeps with **no
timeout**.

- The first candidate pushed on any shard wakes it (`pending == 1`).
- It then **batches** for `interval` ms (default 100) so that one round
  serves many releases.
- The batch is cut short if a shard reaches `threshold` (default 4096), a
  request arrives, or the policy changes.

No wakeup can be lost: every setter publishes its work *before* setting the
event, and the loop resets the event *before* looking.

## 3. What is guaranteed, and how each part is tested

| guarantee | why it holds in v2 | probe |
|---|---|---|
| garbage cycles are freed (self, pair, 1000-ring, via closures, via maps and binaries) | every last external release records a candidate; the candidate reaches the whole cycle | `self_cycle`, `pair_cycle`, `ring_1000`, `cycle_through_closure`, `cycle_through_map_and_binary` |
| …whichever way the last count is dropped | every path funnels through `erts_bin_release` (audit in §2c) | `freed_after_ets_delete`, `freed_after_holder_exits`, `freed_after_unread_message`, `freed_after_persistent_term_erase` |
| …from any scheduler, concurrently | per-shard stacks; see §4 for the release/drain race | `parallel_shards` (16 processes × 200 cycles) |
| …with no explicit request | first push wakes the thread; batching interval | `auto_round_without_request` |
| live data is never freed | trial deletion + A-then-B validation (unchanged); nodes outside the round appear as roots | `live_cycle_survives`, `cycle_held_by_ets_survives`, `cycle_held_by_other_process_survives`, `reader_racing_rounds`, `writer_racing_rounds` |
| a partial round is local | only candidates and what they reach | `partial_round_is_local`: 1 dropped pair among 20 000 live cells → a partial round of < 100 nodes, 2 collected |
| budget overflow stays sound and completes | opaque roots; re-record; explicit request → full round | `budget_overflow_completes` (budget 64, 500-ring) |
| untraced types are not examined | no link, no flag, `track` refuses | `untraced_type_ignored` (1000 `rc_plain` cells → live += 0) |
| policy works | `auto` off → garbage waits; a request still collects | `auto_off_then_request` |
| observability | graph verdicts + why-tree; subscription | `graph_explains_liveness`, `subscription_delivers_rounds` |

Results:

- **Patched:** 23/23. Before the §4 fix, 10/10 runs of the (then 19-probe)
  suite were green and a later run failed once. After the fix, **15/15
  consecutive runs of the full 23-probe suite are green**.
- **Stock:** every leak probe reports the exact expected leak
  (`{pass,{leaked_on_stock,N}}`), and every liveness probe passes.

## 4. The one race found, and how it was closed

The first v2 build failed `parallel_shards` once in about 20 runs: 8 of 3200
cells were left alive after a full settle, with `pending = 0` and 5370
collected. The cause:

1. A cell is on a stack (`BUFFERED`).
2. The collector drains it (clears `BUFFERED`) and pins it.
3. Meanwhile a release on another scheduler had read `BUFFERED` as set,
   **skipped the push**, and was just about to decrement.
4. The round reads the count *before* that decrement lands, sees `outside = 1`
   (the process that is about to let go), and keeps the cell as a root.
5. The decrement lands. The cell is now garbage, and nothing will ever
   revisit it.

**Fix.** Each release is bracketed by its shard's `inflight` counter
(increment before the check, decrement after the decrement). At the end of a
round, while it still holds its pins, the collector:

1. waits until it has seen every shard's `inflight` at zero (`rc_quiesce`;
   releases never block inside the bracket, so the wait is short);
2. re-records every node whose count is now **below** what the round saw.

Any release that skipped a push has finished by then, so its decrement is
visible, and the node is recorded again. After the fix there were 15/15
green runs of the full suite, each of which includes `parallel_shards`.

Cost of the fix: two uncontended atomics on the releasing scheduler's own
cache line, per traced release only.

## 5. Measurements

The host was at **load average 46–58** throughout (other work). Wall-clock
numbers are therefore noisy; stock-vs-stock spread was up to ±40%. The cost
claims below rest on **instruction counts** (`perf stat -e instructions:u`,
3 runs each, busy-wait disabled with `+sbwt none +sbwtdcpu none +sbwtdio none`),
which do not depend on load.

"pristine" is OTP 29.0.1 **rebuilt from the same tree with the same flags**,
so compiler and flag differences from the distro build do not pollute the
comparison. The binaries are kept at `~/.cache/bl/otp/{pristine,v1,v2}/beam.smp`.

### Hot paths every program runs (instructions, millions, 3 runs)

| workload (×10) | pristine | v1 | v2 |
|---|---|---|---|
| boot + halt | 746 744 747 | 735 758 735 | 737 737 739 |
| 200k sub-binaries + GC (`erts_bin_release` on plain binaries) | 2090 2085 2100 | 2097 2077 2080 | 2073 2097 2121 |
| 100k **untraced** resources + GC | 7217 7209 7368 | 7249 7246 7289 | 7228 7258 7232 |
| 100k **traced** cells + GC | 7206 7219 7238 | 8100 8129 8169 | 7733 7671 7679 |

What the table shows:

- **Untraced code pays nothing measurable.** The plain-binary and
  untraced-resource rows sit inside run-to-run noise (about ±1%) on every
  build. The flag test in `erts_bin_release` is one load from a line the
  release was about to write anyway.
- **Traced allocation overhead drops from +12.4% (v1) to +6.3% (v2)**,
  measured end to end on a workload where the traced object is the whole
  cost (tiny cells, created and freed). That is about 0.5k instructions per
  cell per lifetime. What remains:
  - the shard lock (uncontended);
  - the list link and unlink;
  - the destructor's state RMW.

  It is not the global lock.
- One client-side detail matters. Calling `track` **after**
  `enif_release_resource` (as CPython does with `PyObject_GC_Track` at the
  end of construction) means the allocation release is never recorded as a
  candidate. Tracking first made every new object a candidate that the next
  round traced for nothing: that measured 8000M instructions against 7680M.
  `rc_cell.c` shows the right order, and the header documents it.

### Contention: 8 processes × 50k traced cells, wall ms, median of 5, 3 runs

| pristine | v1 | v2 |
|---|---|---|
| 525 393 456 | 1320 1450 1511 | 608 420 555 |

The global lock is gone. v2 is within the noise of pristine; v1 was 3× slower.

### Rounds (`rc_bench`, best of 5, µs; `nodes` = objects examined)

| live cells | v1 round (always over everything) | v2: 1 garbage pair dropped among them | v2 full round | reclaim N cyclic (end to end) |
|---|---|---|---|---|
| 1 000 | 177–429 | **8–16 µs, 2 nodes** | 135–202 | 1–2.7 ms |
| 10 000 | 6 779–7 606 | **15–19 µs, 2 nodes** | 1 505–1 741 | 7.6–10 ms |
| 100 000 | 96 670–128 917 | **20–26 µs, 2 nodes** | 41 919–50 748 | 5.7–18.7 ms |

A partial round costs what changed, not what exists. At 100k live cells, the
round that frees one dropped cycle is **over 3 000× cheaper** than v1's round,
and it runs off-scheduler either way. A full round (for graph views, explicit
`collect(full)`, or the amortised post-overflow round) costs the same order as
v1's, which is inherent to looking at everything.

### Worst case for candidates: churn on a long live chain (`rc_churn`)

The head of a live chain of N cells is rewritten 10 000 times. Each rewrite
makes chain[1] a candidate that reaches the whole chain.

| chain | mutator µs | rounds | nodes scanned | collector µs | overflows |
|---|---|---|---|---|---|
| 1 000 | 7 654 | 1 | 999 | 250 | 0 |
| 100 000 | 11 532 | 2 | 165 536 | 175 161 | 1 |

- **Deduplication works.** 10 000 releases on one object make one candidate
  per batch, not 10 000.
- **The budget works.** At 100k the first partial round stops at 65 536 nodes
  and overflows; one full round follows. The collector's total work is under
  2 × live for the whole burst, and the mutator never waits for it. (It ran
  concurrently: 11.5 ms for 10k writes, with the collector's 175 ms spent on
  its own thread.)
- **What is left:** a live structure that is both large and constantly
  rewritten near its root still costs O(its size) per batch. Generational
  scanning (index A8, "scan old cells less often") is the next lever if a
  real workload shows it.

### beam-lisp on v2

With v2's `beam.smp` copied into a scratch copy of the `e5c05630` drop:

- `bl test ref_cycles_test.bl` → **228 passed** (48 s).
- `bl test research/…/bl/rc_test.bl` → **18 passed** on v2 and **4 passed**
  on the stock drop, where `erts.rc` answers `:unavailable`.

## 6. Remaining costs (honest list)

- **Every `erts_bin_release`** now tests one flag. It is unmeasurable in the
  instruction counts above, but it is a change to the hottest shared path in
  the patch. It must be re-measured on every OTP rebase.
- **A traced object is 56 bytes larger** (the link), and each tracked
  lifetime costs about 0.5k instructions. Per-scheduler *free-lists* of
  links, or an intrusive census that uses the allocator's own block list,
  could shave this further. Not attempted.
- **Full rounds are O(live).** They are rare by construction (graph views,
  explicit requests, amortised after overflows), but a live graph view of a
  million-object heap costs about half a second on the collector thread.
- **The graph request is a dry full round.** A partial-scope graph ("why is
  *this* alive", rooted at one object) would be O(its reach). It is the
  natural next API: `{graph, Pid, Resource}`.
- **Takeover (module upgrade)** swaps the hooks and deliberately leaks the old
  hook copy (a few bytes per upgrade), because a round may still be reading
  it. A thread-progress-deferred free would remove that leak. There is no
  probe for live upgrade under load yet.
- **`enif_trace_resource` / `enif_trace_opaque`** are still not exercised by
  `rc_cell`. `lazy_memo`'s `Cursor` is the natural first user.
- Not tried on the `debug` / `emu` flavours or on other architectures.
