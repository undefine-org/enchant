# OxiZ worker prototype

Owner: this Codex session, one writer on `prototype/oxiz-worker`.
Requested worktree: `/home/othman/code/undefine/enchant--oxiz-prototype`.
Base: `8e41ee0f6efef47ad8ccacd99296ac3ddb8d736f` (Enchant `main`).
Retirement: after review, merge or archive this branch, retain its evidence,
then remove the worktree. It stays available for the requested prototype review.

This project reuses the exact qualified SDK in `sdk-pin.json`; it changes no
runtime inputs and produces no SDK. The ignored `.bl/sdks`, `.bl/platforms`, and
`priv/z3` links reuse the integration checkout's retained artifacts.

This directory is a standalone project. Its runner verifies and invokes the
qualified SDK's exact launcher, never the installed drop on PATH. The current
checkout engine has a different input fingerprint from that retained SDK;
running the checkout compiler wrapper would produce an unrelated SDK. Runtime
source is unchanged, and project checks deliberately stay on the recorded pin.

Experimental only. Z3 remains the authority. OxiZ 0.3.4 has documented open
soundness and model bugs. Comparison must bypass the shared oracle memo.

## Run

From the worktree root:

```sh
research/oxiz-prototype/build
research/oxiz-prototype/run test research/oxiz-prototype/test/worker_test.bl
research/oxiz-prototype/run run research/oxiz-prototype/demo.bl
```

The build uses this repository's locked Nix Rust toolchain, Cargo.lock, one
compiler job, a 4 GiB memory cap, no swap, and a 30 minute ceiling. The runner
uses one cold VM in a private runtime directory, caps its entire process tree
at 3 GiB/no swap/180 seconds, and removes that directory afterward. No daemon
is retained. The worker path is passed explicitly through ENCHANT_OXIZ_WORKER.
The prototype is Linux-qualified; lifecycle observations use `/proc`.

## Boundary

`src/oxiz/worker.bl` owns a private OTP server and one Rust OS process per
lease. The server accepts effects only from its borrower. Monitor-based cleanup
also works when the borrower dies during a native check. Failed or timed-out
exchanges retire the context; there are no automatic retries.

Messages are packet-4 ETF, limited to 1 MiB. Names remain binaries, symbols
are tagged, and only a fixed atom vocabulary is decoded. Rust calls OxiZ's
TermManager/Solver APIs directly. It does not print or parse SMT-LIB. A
dedicated stdin reader terminates the entire worker on EOF, including a busy
solver thread. Each query or scope is one owner call and one native packet;
the hard deadline covers assertion, solving, model extraction, and cleanup.

```clojure
(ns example (:require [oxiz.worker :as solver]))
(solver/with-worker {}
  (fn [worker]
    (solver/check worker
      ['(declare-const x Int) '(assert (= x 7))])))
;; :status :sat, :model {"x" 7}, :trusted false, cost and backend identity
```

The native fragment covers Bool/Int/String declarations; Boolean operators;
integer arithmetic, comparisons, div/mod; ite; basic string operations;
nonrecursive define-fun and let; scalar uninterpreted functions; named
assertions; assumptions; and scoped declarations. Unsupported commands, sorts,
operators, arities, and type mismatches are refused explicitly. Only concrete
scalar models are projected. This is not full SMT-LIB or Z3 compatibility.
Real/FP/BV/Array/datatype/quantifier support and proof certificates are excluded.
An undecided low-level answer carries `:why :unspecified`; the adapter never
guesses whether it was a timeout or theory incompleteness.

`oxiz.oracle/ask` uses an existing obligation's original forms and bypasses
oracle memoization. The existing oracle/obligation still precomputes its text
identity; call worker/check directly to avoid that construction entirely.
`oxiz.oracle/compare` independently obtains the Z3 decision with memo disabled,
then records the untrusted candidate. Models need not be identical, so
agreement compares decisive statuses only. Agreement is not certification.

`oxiz.oracle/with-oracle` is an explicit verifier compatibility experiment. Its
existing handler ABI takes text, so it reads that text back to forms and
serializes scalar models back for the existing verdict parser. This path keeps
the text boundary and the existing reader's SMT string-literal limitations.
The tests exercise an actual guarded account invariant through this bridge.
It changes no default solver selection.

## Results

The focused file passes **45 assertions**, including native models and cores,
scope/declaration rollback, assumptions, malformed input, foreign borrowers,
normal cleanup, borrower death while idle and busy, hard cancellation during a
real pigeonhole search, memo bypass, and an existing verifier invocation.

The retained [report](evidence/report.json) compares eight cases:

| Cases | Z3 | OxiZ adapter |
| --- | --- | --- |
| LIA SAT/UNSAT, Boolean contradiction, string, define-fun | Decided | Same verdict (5 cases) |
| Negative quot/rem from the actual ANF translator | UNSAT | Unknown (2 cases) |
| Documented Boolean-argument UF gap | UNSAT | Refused: non-concrete scalar model |

The last case is an adapter error, not an observed wrong SAT verdict: this
adapter requires concrete scalar model values. A refusal gets a fresh worker
for the next corpus entry, so it cannot contaminate the comparison.

On this host, 100 tiny warm scoped integer contradictions measured a median
**127 µs OxiZ / 171 µs Z3**, maxima 244/367 µs. Each backend retained one
prelude and made one OTP owner call per question; the wire protocols differ.
The timer includes the respective adapters, and memo is disabled. The test
does not measure startup, broad solver throughput, or large problems. It is
evidence for this integration path only, not a general speed claim. Re-running
the demo refreshes the report; the observation in this paragraph describes the
first qualified sample.

Keep Z3 authoritative. The useful next language change would be a forms-first
backend seam in oracle with backend/version-scoped caching. This project proves
that the worker ownership and data boundary can work without a NIF or SDK build;
it does not qualify OxiZ as the compiler's trusted oracle.
