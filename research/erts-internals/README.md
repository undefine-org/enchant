# ERTS internals: a clean layer, and what it opens

beam-lisp already leans on things ERTS does not publish: the refcount of a NIF
resource, where a resource keeps its reference number, how `term_to_binary`
treats a magic ref. The cycle collector in `native/lazy_memo/src/collector.rs`
(PLAN-151) reads a private refcount through an offset it calibrates at load.
It works, and it is the right design for stock OTP. But it is one unaudited
`unsafe` read away from a crash on the next OTP release, and it can only see
what an ETF encode shows it.

This folder asks two questions and keeps every answer in one place:

1. **How do we make the ERTS-internals layer clean and sturdy?** (cluster A)
2. **What does beam-lisp gain once that layer is clean?** (clusters B–F, bold
   by intent)

Each point has an id (`A1`, `B2`, …), a status and a pointer to where it lives.
Only **p1 (trace callbacks)** is explored so far, in depth; see
[`p1-trace-callbacks/`](p1-trace-callbacks/README.md). It is now at **v2**: no
global lock, no cost to untraced resources, O(candidates) rounds (A8 is done
inside it), a no-NIF Erlang surface, and a beam-lisp namespace `erts.rc`
([`p1-trace-callbacks/bl/README.md`](p1-trace-callbacks/bl/README.md)). Every
other point is recorded so it can be prototyped from this page alone.

Source for the ERTS facts cited: *The BEAM Book* (Stenman,
<https://blog.stenmans.org/theBeamBook/>) ch 3, 4, 8, 10, 11.12–12, 16.3–16.4,
and the OTP 29.0.1 sources (`erts/emulator/beam/`), read at the tag that is
installed on this host.

## Can we patch ERTS? How expensive is it?

Yes, and it is cheap. Measured on this host (Ryzen AI 7 350, OTP 29.0.1,
load average ~20 from other work):

| step | time | notes |
|---|---|---|
| fetch source tarball (tag `OTP-29.0.1`) | ~1 min | 239 MB unpacked |
| `./configure` | 66 s | once per tree |
| cold `make emulator` (-j12) | ~2.7 min | only `erts/emulator`, no OTP apps |
| relink after editing one `.c` | **13–18 s** | the normal inner loop |
| rebuild after a shared header (`global.h`) | 140 s | every object recompiles |

**Nothing else is recompiled.** The patched `beam.smp` runs the *installed*
OTP libraries unchanged, because they are version-matched (same tag, same
`erts-17.0.1`). `otp/erl-patched` does exactly that: it points `erlexec` at a
`BINDIR` holding the new `beam.smp` and borrows the system `erlexec`, `epmd`,
`heart` and `inet_gethost`. For beam-lisp's own drops the same holds: copy the
patched `beam.smp` over `<drop>/erts-17.0.1/bin/beam.smp` and every `bl`
command runs on it (verified: `test/bl/ref_cycles_test.bl` is green on both).

Rules that keep this safe:

- the patch tag **must** equal the installed release (`build.sh` reads
  `releases/*/OTP_VERSION`); a mismatched emulator would load `.beam` files
  compiled for another VM;
- patches are plain `git format-patch` files in `otp/patches/`, applied to a
  pristine tree tracked in git, so they are reviewable and re-applicable to
  the next tag;
- every patched entry point is *additive* (new symbols, a new `system_info`
  item and `system_flag` flag); stock ERTS answers `badarg`, a NIF resolves
  symbols with `dlsym`, `erts.rc` answers `:unavailable` — nothing ever
  *requires* the patch.

Every build and test here runs inside a capped scope
(`systemd-run --user --scope -p MemoryMax=… -p CPUQuota=…`, host policy).

## Layout

```
research/erts-internals/
  README.md                  this page: every point, clustered
  otp/
    build.sh                 fetch → configure → apply patches → build emulator
    erl-patched              run the patched beam.smp with the system OTP libs
    patches/0001-…patch      the p1 patch (erl_nif_trace.{c,h} + ~60 hook lines
                             in 9 files; reproduces the tracked tree exactly)
  p1-trace-callbacks/
    README.md                design, soundness, API, observability, results
    OVERHEAD.md              v1 → v2: where every cost went, and the proof
    run.sh                   build the probe NIF; run on stock+patched; `bl`
    nif/rc_cell.{c,erl}      the smallest honest client (+ an untraced type)
    nif/rc_ctl.erl           the collector from plain Erlang (no NIF)
    nif/rc_test.erl          23 probes: leaks, liveness, races, every release
                             path, partial/full rounds, budget, policy
    nif/rc_observe.erl       developer tools: why/1, garbage/0, dot/1, watch/1
    nif/rc_bench.erl         alloc (untraced/traced/parallel), round costs
    nif/rc_hot.erl, rc_par.erl, rc_churn.erl   instruction-count, contention
                             and worst-case-churn benches (OVERHEAD.md)
    bl/erts/rc.bl            beam-lisp namespace `erts.rc`
    bl/rc_test.bl            its tests (patched: 18 assertions; stock: 4)
    bl/README.md             how to use it
```

---

## Cluster A — a clean, sturdy ERTS-internals layer

The aim is for beam-lisp's knowledge of ERTS internals to be **explicit,
versioned, proven per release, and removable**.

| id | point | status |
|---|---|---|
| **A1** | **Trace callbacks in ERTS** — resource types register `trace`/`clear`/`epoch`; ERTS finds garbage cycles among resources. Removes the private refcount read, the refn read and the ETF census all at once. | **prototyped, v2: [p1](p1-trace-callbacks/README.md)** |
| A2 | **One private read, not two.** On stock OTP, store each cell's key at creation (from its own `enif_make_resource` term) so calibration needs only the refcount offset; the reference-number offset disappears. | open — small change to `collector.rs` |
| A3 | **Layout derived twice.** Generate the `ErtsResource`/`magic_binary` offsets from the OTP source at the installed tag (`global.h`, `erl_binary.h`, as p1's build already has them) *and* keep the runtime calibration; load only if both agree; cache the verdict per (ERTS vsn, build-id, arch). | open |
| A4 | **One `unsafe` crate.** Move every private read behind one typed accessor crate (`erts_layout`: `refc(&ResourceArc<T>) -> isize`). No other file holds `unsafe` pointer arithmetic; an OTP upgrade review is one file. | open |
| A5 | **Debug-emulator oracle in CI.** A `debug` build (`make emulator TYPE=debug`) exposes `nif_refc` and assertions; a CI job compares calibrated reads with ground truth on every supported OTP. | open — `build.sh` needs a `TYPE=debug` switch only |
| A6 | **Cross-library participation.** Any NIF crate (datom_vector, datom_fjall, …) joins the collector through a public call: under p1 by registering hooks; on stock via `enif_dynamic_resource_call` returning its edges. | p1 gives the patched half |
| A7 | **Compiler-assisted edges.** `lower.bl` emits every beam-lisp closure. A closure stored into a cell can be compiled as an explicit `{code, env}` tuple, walkable with public NIF calls; ETF stays for foreign funs only. | open |
| A8 | **Incremental rounds.** Only cells whose refcount *dropped but did not reach 0* can be new garbage (Bacon–Rajan candidate roots); diff refcounts between rounds → O(changed) rounds; scan old, untouched cells less often (BEAM Book §12.2 generations). | **done in p1 v2** for the patched path ([OVERHEAD.md](p1-trace-callbacks/OVERHEAD.md) §3); generations still open; the stock `collector.rs` still does O(live) rounds |
| A9 | **Refc-binary-style retention.** A dead reference keeps its count until its holder next GCs (Book §11.12.3). Flag roots that never change across rounds and whose holders are beam-lisp-owned; hint a minor GC. Add a long-lived-holder test. | open — p1 `live_cycle_*` probes are the base |
| A10 | **Upstream it.** Carry p1 in drops; propose the trace API as an EEP. §16.3 shows how small a BIF is; the p1 patch is 4 hook lines + one new file. Fallback on unpatched OTP stays A2–A4. | open |

## Cluster B — values that live off the process heap

| id | point | status |
|---|---|---|
| B1 | **Off-heap persistent collections.** With resources that may safely hold terms (A1), Clojure's vector/map/set can live in Rust as refcounted, cross-process-shared resources: O(1) send (like refc binaries), structural sharing survives messages (the Book §11.12.1 blow-up disappears without `--enable-sharing-preserving`), `persistent_term`-like globals without copy-on-read. | open — needs a value-model pass (`docs/patterns/01-one-value-model.md`): equality, hashing, `case` over a resource |
| B2 | **Representation chosen by proof.** Escape analysis + footprint proof pick the cell kind: non-escaping → process-local (no resource: FUP-129 by proof), proven leaf (`(atom 0)` of sort Int) → untraced leaf (under p1: no hooks at all), escaping + may-cycle → traced resource. Collector cost → near zero for the common case. | open — p1 already makes "untraced" a per-TYPE choice |
| B3 | **Region processes.** A `bl doc run` cell, a request, a test: a process with a proven heap bound and `fullsweep_after` off, killed at the end — all its memory freed at once; owner-scoped cells (monitor-tied) make cycles inside the region free. | open |
| B4 | **Exact word accounting.** Book ch 4 gives exact sizes; `enif_term_size` (NIF 2.18, OTP 29) is a runtime oracle. `docs/memory-policy/01`'s `words-of` becomes exact, so `max_heap_size` is set by proof, and exceeding it is a bug report with a counterexample. | open |

## Cluster C — a native lazy engine that behaves like BEAM code

| id | point | status |
|---|---|---|
| C1 | **Native chunk engine with reductions.** Chunks become Rust batches that charge the scheduler (`enif_consume_timeslice`) and yield (`enif_schedule_nif`), the lesson of Book §16.3.3 (`term_to_binary`). | open |
| C2 | **Scheduler class from proofs.** `docs/memory-policy/05`'s work bounds pick normal vs dirty per operator. | open |
| C3 | **`distinct`/`Seen`-style native state everywhere.** PLAN-151 made `distinct` O(n) with one native set; the same shape fits `dedupe`, `group-by`, `frequencies`, memoize. With A1 these resources may hold anything. | partly done (Seen) |

## Cluster D — the runtime as data

| id | point | status |
|---|---|---|
| D1 | **Cell graph as datom facts.** p1's `graph` snapshot (nodes, edges, verdicts, why-alive tree) as facts; "why is this alive" becomes a datalog query returning the holding path. | **p1 ships the snapshot, `erts.rc/why` and `erts.rc/watch`**; the datom sink is open |
| D2 | **PCB fields as facts.** `high_water`, old-heap size, mbuf size, `bin_vheap` (Book §12.2) sampled into datom; `docs/memory-policy/02` (leak = monotone footprint) checked against measurement, not only proven. | open |
| D3 | **Trace-driven lowering.** Call tracing (Book ch 19) as datalog input: chunk size, recipe bypass, native offload decided from observed behaviour. | open |
| D4 | **`live-architecture` from the VM.** The architecture view reads processes/links/monitors/resources from ERTS, not from the program's self-description. | open |

## Cluster E — compiler internals as proven facts

| id | point | status |
|---|---|---|
| E1 | **Versioned private formats.** The same derive-verify-pin machinery (A3) for compiler internals: `lower.bl` already starts at `from_core` and has hit its edge cases (`raw_raise`, `build_stacktrace`). | open |
| E2 | **BEAM-asm / SSA emission on hot paths** to reach the loader's specialised instructions (Book ch 9) where Core Erlang cannot express them. | open |

## Cluster F — ERTS as part of the product

| id | point | status |
|---|---|---|
| F1 | **Patched ERTS in the drop.** Drops already build from source trees; the patched `beam.smp` is one more artifact, pinned by tag, tested by the oracle (A5). | **mechanics verified by p1** (drop copy + `bl test`) |
| F2 | **Sharing-preserving copy** (`--enable-sharing-preserving`) as a drop option if B1 is not taken. | open |
| F3 | **Debug emulator for CI** (A5) shipped as a separate drop flavour. | open |
| F4 | **Upstream path** for every patch (A10); a patch without an upstream story is a maintenance debt per OTP release. | open |

### Risks that apply to every cluster

- A private-layout path must degrade to **correct and slower** when a check
  fails, never to wrong. Holds today (the Rust collector disables itself;
  p1 clients fall back to no collection); it must stay a tested invariant.
- A patched ERTS is a per-OTP-release commitment. p1 keeps it small (one new
  file, ~60 hook lines, additive symbols) so a rebase is minutes, not days.
  v2 touches `erts_bin_release` — the hottest shared path in the patch — with
  one flag test; OVERHEAD.md §5 is the measurement to redo on every rebase.
- B1 changes equality/hashing/matching of collections; it needs design before
  code.

## Suggested order

1. **A1 → integrate p1 into `lazy_memo`** (see p1 "Next steps"): cells,
   cursors and `Seen` register hooks; the Rust calibration stays the stock
   fallback; `erts.rc` moves from research into `priv/lib`.
2. A2 + A4 + A9 (small, sturdier stock path).
3. B2 (proof-picked representation) — reuses the typing/footprint engines.
4. B1 prototype: off-heap vector + send benchmark vs on-heap; decides whether
   the bold version pays.
