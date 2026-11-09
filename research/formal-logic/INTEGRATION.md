# Moving Enchant's formal consumers to portable terms

This is a source audit and a concrete cutover design. The implementation under
`research/formal-logic/src/formal/` is experimental. Loading it does **not**
migrate the default compiler oracle, its pool, existing verifier consumers, or
their caches. The current default remains `oracle/pool-handler` →
`z3pool/check`, with SMT-LIB text at that boundary. The explicit historical
`oxiz.oracle/with-oracle` bridge still reads text and re-emits model text; it is
compatibility evidence, not the new term path.

The new path is `formal.query` → `formal.logic` → owned `formal.backend` →
typed DAG → native Z3 C API or OxiZ `Context`. Both adapters construct native
terms without an SMT-LIB script parser/printer fallback. Portable BL terms
contain no native pointer. ETF and native AST construction still cost time:
this is neither shared-heap passing nor a zero-copy NIF. OxiZ's own
`Context::check_sat` additionally invokes internal published-model honesty
machinery that can render/read models; the claim concerns our interface,
not every implementation detail inside OxiZ.

## Exact consumers and pieces to replace

These are source entry points in this checkout, not a claim that every example
or test listed below has been rerun through the new interface.

| Consumer | Current seam | Concrete term cutover |
| --- | --- | --- |
| `priv/lib/oracle.bl`: `obligation`, `ask`, `session`, `scoped`, `here-verdict` | Obligations eagerly render scripts; handlers accept `[text model?]`; verdicts parse model/core text | Accept a `formal/query` value as the effect payload. Keep one explicit handler receiving a complete question and returning structured evidence. `formal.backend/with-session` owns native state; `formal.logic/solve-in` interprets proof polarity and replay |
| `priv/lib/system/smt.bl`: `translate-node`, `of-node`, `of-source`, length/variant/inlining siblings | Resolved compiler ANF becomes untyped SMT forms, with `:untranslatable` | Retain compiler ANF and source-clause resolution. Replace the output algebra with checked `formal.term`/`formal.value` constructors. Preserve unsupported results, origins, partiality and semantic profiles |
| Same file: `datatype-decl`, `variants-map`, `defn->define-fun` | Native datatype and helper definitions become SMT declaration forms | Nullary enums have native term routes. Payload sums currently need explicit `formal.data` encodings. Nonrecursive helper bodies become checked summaries/substitution with hygienic binders, rather than a printed `define-fun` |
| `priv/lib/system/core.bl`: `preserves?`, `establishes?`, `prove-box`, `preserves-joint?`, `establishment-verdict`, `step-obligation` | Prelude declares state/primed values and `Inv`; scoped named assertions express a counterexample | Build state terms once. Use `q/prove` for preservation/establishment and `q/sat` for feasibility, with named assumptions and observations. Preserve the distinction between initial feasibility and establishment |
| Same file: `k-induction-check`, `verify-process`, `discover-invariant`, `verify-capacity`, `synthesize-capacity`, `verify-content` | Repeated oracle sessions over generated declarations, copied names, length abstractions and quantified content laws | Use portable state vectors and checked substitution. Feed explicit procedure questions to `formal.transition` or `formal.logic`; record induction depth, abstraction and capacity scope on every result |
| Same file: `sufficient?`, `fireable?`, `guard-implies?`, `repair-transition`, `joint-fireable?`, `guard-implies-multi?`, `guards-overlap?` | SAT and UNSAT answers have different intended polarities | Replace each with `q/sat` or `q/prove` deliberately. `:sat` is a feasible witness, not automatically a refutation; `:unsat` is not universally a failed program |
| `priv/lib/veritas.bl`: `try-symbolic`; `veritas/property.bl`: `prove` | Translated forms feed oracle; SAT models are converted to test inputs | Request descriptor observations, retain independent validation, and emit an executable counterexample only when decoding and replay cover the question's domain |
| `priv/lib/veritas/mock.bl`: `synth`, `synth-invalid`, `synth-boundary`, `check`; `veritas/fault.bl`: `isolate` | Raw scalar model maps drive synthesis/mock data and fault explanations | Use `q/sat` with explicit domains/partiality, projection enumeration or finite optimization. Preserve absent/nil/default and representation limits instead of manufacturing a value from missing model fields |
| `priv/lib/datom/time.bl`: `overlap-verdict`, `consistent?` | Oracle satisfiability decides overlap/missing intersections and temporal constraints | Build exact integer/order questions with `q/sat`; propagate unknown/unsupported rather than converting them to consistency or disjointness |
| `priv/lib/system/linear.bl`: `size-lemma`; `priv/std/reload/migrate.bl`: `verify-migration`/`z3/prove-equiv` call | Arithmetic obligations and raisedness/value equivalence use the legacy ABI | Construct `q/prove` or `q/equivalent`; include effects, definedness and resource assumptions in the descriptor and identity |
| `priv/lib/z3.bl`: `check`, `check-model`, `prove-equiv`, `command`, `push`, `pop`, `check-here`, `check-assuming`, `check-core` | Script compatibility API, sometimes raw strings and low-level conversation effects | Keep this as an explicitly legacy escape hatch during transition. New common consumers receive queries, not arbitrary backend commands |
| `priv/std/z3pool.bl` and `priv/host/z3_port.bl` | Lease registry, borrower custody, process lifetime, text framing and hard deadline | Preserve custody/backpressure/deadlines while replacing only the native transport implementation. The new owner is per session; a bounded reusable worker pool has not been implemented |
| `priv/lib/system/decide.bl`, `system.ledger` | Form classifier and one-direction bounded SAT witness rung; cost/fragment ledger | Classify typed DAG operations/sorts. Reuse the independent evaluator for proposed witnesses; a missed search never proves UNSAT. Record backend, profile, scope and validation with fragment/cost |

`examples/oracle/*`, `examples/system/z3-conversation.bl`,
`test/bl/system/{oracle*,z3*,smt*,anf_smt*}`, `smt_parity_test.bl`,
`host_z3_port_test.bl`, and `decimal_oracle_port_test.bl` are regression
consumers of these contracts. Their presence is a migration checklist, not
qualification of the experimental worker.

## Write the question once

A preservation obligation can already be expressed without backend syntax:

```clojure
(ns account-proof
 (:require [formal.term :as t] [formal.query :as q]
           [formal.logic :as logic] [formal.backend :as backend]))

(def balance (t/variable "account.balance" t/Int))
(def amount (t/variable "account.amount" t/Int))
(def next-balance (t/sub balance amount))

(def preservation
 (q/prove (t/ge next-balance (t/int 0))
  {:id :account/withdraw-preserves-balance
   :assumptions
    [(q/assertion "invariant" (t/ge balance (t/int 0)))
     (q/assertion "amount-nonnegative" (t/ge amount (t/int 0)))
     (q/assertion "guard" (t/le amount balance))]
   :observe {"balance" balance "amount" amount "next" next-balance}
   :profile :bl/int-bool-intrinsics-v1
   :scope {:mode :exact :state-domain :unbounded-integers}}))

;; opts selects an owned artifact and deadlines, not a different proposition.
(logic/run {:backend :z3} preservation)
(logic/run {:backend :oxiz} preservation)

;; A sequential session shares imported native DAG identities.
(backend/with-session {:backend :z3}
 (fn [session]
  [(logic/solve-in session preservation)
   (logic/solve-in session
    (q/sat {:id :account/withdraw-is-fireable
            :assumptions [(t/ge balance (t/int 0))
                          (t/ge amount (t/int 0)) (t/le amount balance)]
            :observe {"balance" balance "amount" amount}
            :profile :bl/int-bool-intrinsics-v1
            :scope {:mode :exact :state-domain :unbounded-integers}}))]))
```

This replaces the `Inv`/primed-declaration/text machinery for this obligation;
the original program's invariant, guard and next-state extraction still need
to produce the terms. A disappearing constraint or unreviewed call must not
be replaced with `true` or an unconstrained UF.

The experimental source seam already uses the real compiler's ANF:

```clojure
(ns source-proof
 (:require [formal.term :as t] [formal.source :as source]
           [formal.logic :as logic]))

(let [x (t/variable "source.x" t/Int)
      prepared (source/equivalence-problem
                 "(+ x 0)" "x" {"x" x}
                 {:id :source/add-zero
                  :scope {:mode :exact :state-domain :unbounded-integers}})]
 (if (= :translated (:status prepared))
  (logic/run {:backend :z3} (:problem prepared))
  prepared))
```

`formal.source/prepare` currently handles a declared Int/Bool intrinsic
environment, local expressions/conditionals and reviewed calls, with selected
nil/keyword domains. It is narrower than today's `system.smt` helper inlining,
variant selectors and length abstractions. Port those ANF branches and checked
summaries explicitly before changing their existing consumers. Preserve
source maps on assertions and descriptors; they do not belong in term equality.

`q/equivalent` compares raisedness and successful values. It does not certify
arbitrary side effects, process interactions, divergence or resource behavior.
Those require the corresponding effect/transition model and explicit bounds.

## Ownership and cancellation: audit against the legacy 45 assertions

The historical [qualification receipt](../oxiz-prototype/evidence/qualification.json)
records **45 passing assertions in `oxiz.worker-test`** at its named commits.
Those assertions exercised the older form worker. They are not 45 lifecycle
cases and are not a qualification receipt for `formal.backend`.

The new owner's source preserves the important structure:

* `native-owner` alone opens/connects the port and exchanges packets. It
  monitors its borrower; `handle-call` checks the actual calling PID.
* `exchange!` checks port custody, monitors the port, enforces one absolute
  hard deadline and accepts only that port's response/exit events.
* Borrower death during a busy exchange closes the port before killing the
  owner. Idle borrower death stops the owner; termination closes the port.
* The Rust stdin reader exits the **whole OS process** on EOF independently
  of the solving thread, so port closure can cancel a noncooperative search.
* Any failed native exchange closes the port and retires the owner. The BL
  registry commits only on `:ok`; a partially imported request is never
  retried in that process. A foreign caller's refusal does not retire the
  rightful borrower's context.

| Legacy assertion group | New equivalent/invariant | Source-audit status / qualification still needed |
| --- | --- | --- |
| Structured models, closing lease stops OS process | Observation tags and `with-session` finalizer; SAT separate from availability | Implemented; recheck normal exit and exceptions for both native backends |
| One context, scoped declaration rollback | One native process; import before push; only scoped assertions roll back | Intentional semantic change: immutable DAG nodes/declarations persist after scope. Reset advances generation; source terms can be reimported |
| Assumptions do not persist | Z3 native check-assumptions; OxiZ temporary push/assert/check/pop | Implemented; add consecutive checks on one session for both paths |
| Named core values | Z3 private fresh tracking literals → binary labels | Implemented. OxiZ typed native core getter is unavailable, so core-kind is unsupported; do not preserve the old test's native-core expectation by parsing text |
| Unsupported/ill-sorted scripts retire context | Typed frontend/native validation; any partially applied fault retires | Arrays are now a real native capability, not intrinsically invalid. Test malformed node/sort/arity, changed IDs, unknown operations and UF signature redeclarations instead |
| Foreign borrower refusal | PID check at owner call and port custody check | Implemented; session maps contain mutable host bookkeeping and are not a transferable security capability |
| Borrower killed while idle | Monitor → stop → terminate → close | Implemented by inspection; observe actual OS death for each backend |
| Deadline while real solver busy | Independent hard deadline → close → EOF watchdog | Same design; repeat the real busy-solver cancellation probe, not only an immediate UNSAT/timeout |
| Borrower killed while solver busy | Borrower DOWN is handled inside the blocking exchange | Implemented by inspection; repeat OS-process disappearance and no late response |
| Existing verifier bridge, memo bypass | Historical bridge remains text-based | Do not substitute its passing result for term-only `system.core` cutover evidence |
| Shadow comparison | `formal.logic/compare` keeps Z3 decision and OxiZ candidate separate | Implemented; all answers remain explicitly untrusted exploratory data |

`test/backend_test.bl` covers shared portable questions, vacuity, reset/stale
generations, private tracking labels, cache identity, derived procedures,
foreign borrower refusal, uncompressed ETF and reply identity/schema guards.
`test/api_test.bl` checks persistent-context meaning, replay and cache identity.
The [combined receipt](evidence/qualification.json) retains 795 passing
assertions across seven files. It does not reproduce the whole historical
busy-cancellation matrix.

Further boundary checks needed before replacing `z3pool`:

1. Extend the checked reply envelope into a complete typed observation schema,
   including malformed fake-worker responses. Protocol, generation, backend,
   result shape and compressed-reply refusal are implemented and tested.
   `binary_to_term(..., [:safe])` prevents new atoms; it does not establish
   model semantics or validate every observation's sort.
2. Preserve transport error kind and phase through every failure. The owner
   retains structured exception kinds (including hard timeout); native exit
   and framing cases need finer classification and additional checks.
3. Check zero/oversized/truncated packets, trailing ETF, native crash, stale
   generation and altered ID import. A reply that exceeds capacity currently
   ends the worker; it cannot authorize a proof or a missing-value default.
4. Make owner startup and all post-start setup one cleanup bracket; observe
   cleanup on callback exceptions and setup/handshake failure as well as the
   ordinary finalizer. Add bounded backpressure before any shared-worker pool.
5. Retain declared source identities consistently across sorts. UF signatures
   and bound sorts are checked natively; same-spelled free variables of
   different sorts must not collapse in the BL name-keyed assignment map.
   Keep binder names unique and substitution capture-avoiding.

## Persistent context, authority and cache obligations

`backend/load!` assertions are part of the effective question. `solve-in`
prepends retained assertions under `context/` labels, includes them in
preflight, roots/free variables, replay, assumptions and cache identity, and
returns a `:context` receipt with generation and assertion labels/digest.
Duplicate native scope assertions are harmless. The focused regression passes:
a loaded `x > 0` yields a conditional proof, the fresh question is refuted,
their cache identities differ, and a later SAT query observes/replays the
loaded free variable. Vacuity policy and observation names/descriptor shapes
also participate in evidence-cache identity.

The remaining obligations apply to every consumer:

* A query's identity includes typed DAG, persistent background, semantic
  profile/version, bounds, assumptions, requested observations/result mode,
  backend/library/worker artifact identity and relevant solver settings.
  `formal.query/cache-key` is a SHA-256 receipt; no compiler proof cache is
  populated by this experiment. The legacy `oracle/obligation` uses
  `phash2(text)` and its memo is not backend/profile/artifact scoped. Bypass it
  during comparison; do not repurpose it as the new proof cache.
* Hash the actual immutable native artifacts used. The prototype hashes
  worker/library files before launch; deployment should select immutable
  packaged artifacts and retain the qualified SDK selection, dependency
  features and source receipt. A version string alone is insufficient.
* `:proved`, raw UNSAT, checked SAT witness, incomplete candidate, unavailable
  observation and certificate verification are separate facts. New results
  have `:trusted false` and unchecked certificates. `formal.logic/compare`
  choosing `:authority :z3` is an experimental decision policy, not global
  compiler activation or a proof certificate.
* A named UNSAT core is not a proof. Replay its selected assertions with the
  original assumptions/persistent background. A deletion explanation has
  `:kind :derived-deletion`, not native provenance; unknown interrupts claims
  of subset minimality. OxiZ core support must remain explicit until a typed
  native route exists.
* Independent replay consumes native **assignments**, then evaluates the
  original portable assertions. Solver-evaluated watch expressions may help
  display a witness but do not establish independent validation. Full array,
  sequence, UF and quantified models currently exceed replay coverage; scalar
  observations alone cannot validate arbitrary extensional/quantified laws.
* Z3 observation evaluation now requests a concrete extension for omitted
  don't-care symbols. That changes model availability, not the SAT verdict,
  and does not claim a unique runtime answer. The hello limit
  `"model-completion" = "concrete-extension"` records this policy; the worker
  artifact hash also changes. The pinned [Z3 4.16 C API documentation](https://raw.githubusercontent.com/Z3Prover/z3/z3-4.16.0/src/api/z3_api.h)
  specifies completion of otherwise uninterpreted model symbols.

Before cutover, preserve the existing ledger/ceiling, effect handler interception
and deny behavior, model request semantics, borrower ownership and hard
deadlines. A new `with-formal-handler` would receive a portable query and return
evidence; table/deny handlers must intercept nested session questions too.
Do not implement that effect by serializing a typed query back to the old
`[script-text model?]` ABI.

## FP normalization is a boundary correction, not general FP qualification

The retained [pre-normalization native run](evidence/native-before-normalization.json)
exposed a wrong OxiZ SAT answer to equality of two different NaN payload
literals. Independent replay rejected it. OxiZ's `mk_fp_lit` preserves raw
sign/exponent/significand; `mk_eq` does not normalize FP literals. The main
solver's `fp_atoms_need_theory` explicitly excludes bare FP constants/variables,
allowing their equality to stay in EUF without actual FP model validation.
Lower-level FP code has the correct one-NaN equality rule, but that does not
establish that the main route invokes it.

The adapter correction recognizes an all-ones exponent and nonzero fraction at
literal import and calls native `mk_fp_nan(eb, sb)`. Every IEEE NaN encoding
denotes the same SMT FP value; its sign/payload cannot be observed as a stable
FP model identity. This is exact normalization at the boundary, not dropping a
constraint or choosing a finite approximation. Non-NaN literals retain their
bit meaning. `fp.eq`, SMT `=`, and equality of original BV payloads remain
different questions. NaN observations remain opaque.

The corpus includes negative-NaN, `fp-neg(NaN)` and UF congruence probes. The
rebuilt artifact is qualified by the combined receipt; the earlier failing
evidence remains in `evidence/native-before-normalization.json`. This
correction does not qualify arbitrary symbolic FP equalities, arithmetic,
formats, rounding or combinations. Exact Real arithmetic is likewise not a
substitute for IEEE FP runtime semantics.

## Custom theories and user propagators: what is actually available

User propagation is **not unique to OxiZ**. The pinned Z3 4.16 C API exposes
`Z3_solver_propagate_init`, fixed-value callbacks for Bool/BV, equality/final
callbacks and `Z3_solver_propagate_consequence`. A Rust worker can implement
those callbacks while the BL-facing query remains term-based. None is wired
into our thin Z3 adapter yet. See the [pinned primary API](https://raw.githubusercontent.com/Z3Prover/z3/z3-4.16.0/src/api/z3_api.h)
for the callback registration and solver-callback lifetime restrictions.

Source inspection of cached OxiZ 0.3.4 establishes these different facts:

| Seam | Verified reachability | Consequence for BL |
| --- | --- | --- |
| `Context.terms`, `declare_const`, `declare_fun`, `assert`, `push/pop`, `check_sat`, `eval_in_model` | Actual worker path; builds and existing native checks exercise it | A concrete pure-Rust adapter/term construction seam, preserving Context's rounding/model/array honesty gates |
| `oxiz_theories::user_propagator::{UserPropagator, UserPropagatorManager}` | Standalone manager with register/watch/notify/final-check APIs and local tests; no reference from main `Context`/`Solver` source found | Useful code to study, not an installed propagator in a normal `Context::check_sat` |
| `oxiz_core::theories::TheoryCombiner`, `Theory` | Can register boxed theory objects and drive explicit equality exchange; its `NoConflict` outcome expressly does not assert SAT | A standalone Rust experiment is possible; not evidence that arbitrary theories are attached to the production solve loop |
| `oxiz_solver::combination::TheoryCoordinator`, propagator managers | Separate coordinators/traits; main solver owns concrete EUF/arithmetic/BV and other specialized integrations | Connecting a new theory requires explicit solver-loop, explanation, backtracking, model and honesty-gate wiring |
| OxiZ nonlinear engine | Current dependency selection is `default-features=false, features=["std"]`; `nlsat` is a separate feature | A module inventory or term builder cannot advertise the omitted engine as enabled; enabling it changes the native artifact and needs new qualification |

Relevant primary source locations are the cached crate files
`oxiz-solver-0.3.4/src/context.rs`, `src/solver/mod.rs`,
`src/solver/check_fp.rs`, `oxiz-theories-0.3.4/src/user_propagator.rs`,
and `oxiz-core-0.3.4/src/theories/combination.rs`. Their public traits do not
constitute a verified drop-in extension route through our `Context` adapter.

The immediate common extension seam is already useful: implement BL domain
operations as typed descriptors/constraints above both backends, and qualify
them through identical `formal.query` questions. Finite maps, bounded vectors,
tagged sums, permissions and transitions use that seam now.

A subsequent native theory prototype should first choose one small domain
(for example finite permission inclusion) and a declared versioned term
catalogue. Keep its meaning and fallback encoding above the backend. For Z3,
register compiled Rust callbacks using the C API. For OxiZ, demonstrate the
actual insertion point in the main solving loop before exposing a capability.
Return lemmas/conflicts with premise IDs and test push/pop/reset, cancellation,
model replay and false assumptions. `NoConflict` or an unrun final check must
never authorize SAT. Any extension identity, semantics and encoding version
belong in capabilities/query/cache receipts.

Do not synchronously call arbitrary BL closures from native search as the
initial design: that would add reentrancy, ownership and proof obligations to
the worker protocol. Compile the selected semantics into the worker or expose
a separate, explicitly experimental lemma exchange with bounded lifetimes.
OxiZ offers easier Rust-level inspection/modification; it does not uniquely
enable a term-native BL formal interface or make an unwired trait trustworthy.

## First concrete migration batch

1. Finish custody/typed-boundary/persistent-context qualification above, while
   retaining the exact SDK and native artifact receipts. Separate native
   construction capabilities from successfully qualified theory queries.
2. Move the scalar Int/Bool preservation/establishment and feasibility
   obligations in `system.core` to the exact `formal.query` shape shown above,
   behind an explicit experimental handler. Retain legacy default behavior.
   Compare decisive statuses, checked witnesses, vacuity and costs per question.
3. Extend `formal.source` with the existing ANF helper-summary and clause
   selection logic; qualify it against current and proposed semantic canaries.
   Preserve Euclidean versus truncating division, grapheme/codepoint/byte
   operations, nil/default/presence and FP/Real distinctions in profiles.
4. Port `veritas` model consumers to descriptor observations and independent
   replay. A model that cannot construct a valid runtime test remains a
   candidate. Native ADT/recursive definitions, regex, arbitrary sequences,
   recursive summaries and proof certificates need explicit capability work;
   current finite encodings do not silently stand in for those native theories.
5. Only after those consumers and caches accept complete typed evidence,
   consider replacing the default oracle handler and pool transport. Keep the
   legacy script API explicit for existing callers until their migrations are
   complete. This document does not perform or authorize automatic promotion
   of OxiZ into the compiler's proof authority.
