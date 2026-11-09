# Enchant formal logic, expressed as language terms

This is the expanded OxiZ experiment: one typed, term-based BL interface with
native Z3 and OxiZ backends. It prototypes language semantics, verification
procedures and native theory access together. **The existing compiler/oracle
defaults have not been migrated or given a new trust policy.**

The design review is in [ATLAS.bl.org](ATLAS.bl.org), its machine-readable
catalogue in [atlas.json](atlas.json), and the semantic decisions in
[SEMANTICS.md](SEMANTICS.md). The catalogue has 46 interface families, with
implemented fragments and deferred work distinguished per family. It does not
claim 46 complete solver theories. [CONTRACT.md](CONTRACT.md) defines the shared
data contract; [INTEGRATION.md](INTEGRATION.md) describes the production cutover.

Owner: the integration session on `prototype/oxiz-worker`. The requested
worktree is `/home/othman/code/undefine/enchant--oxiz-prototype`; retirement is
merge/archive after the requested prototype review, then worktree removal.
Runtime source is unchanged. [sdk-pin.json](sdk-pin.json) retains the qualified
SDK, verified by the runner; this project produces no SDK.

## The common BL interface

```clojure
(ns example
  (:require [formal.api :as formal] [formal.term :as t]
            [formal.value :as v] [formal.collections :as maps]
            [formal.data :as data]))

(def inputs
  (formal/symbols "ledger"
    {:accounts {:kind :map :keys [:alice :bob] :item t/Int}
     :who {:kind :key :universe [:alice :bob]}
     :amount t/Int}))

(def obligation
  (formal/question inputs
    {:id :read-after-write
     :claim (fn [{:keys [accounts who amount]}]
              (v/equal
                (data/unwrap (maps/map-lookup
                               (maps/map-assoc accounts who amount) who))
                amount))}))

(formal/describe obligation)              ; inspect pure data, profiles, bounds
(formal/check {:backend :z3} obligation)
(formal/check {:backend :oxiz} obligation) ; identical question and interpretation
(formal/compare obligation)               ; agreement and replay remain distinct
```

The map theorem is exact over its declared two-key universe. Map payloads have
independent presence, so a missing entry and an entry holding nil differ. A
symbol declaration does not manufacture every possible BL runtime value.

The architectural seams are:

| Piece | Owns | Common contract |
| --- | --- | --- |
| `formal.term` | Checked primitives and immutable DAG | sort, operation, arguments, literal/index data |
| `formal.value` and theory modules | Language meaning | payload, `defined`, `within`, constraints, domain/profile, scope |
| `formal.source` | Reviewed compiler ANF lowering | declared scalar bindings, explicit unsupported result |
| `formal.query` | The question | named assumptions, claim, observations, profile, bounds and origin |
| `formal.logic` | Shared proof/search methods | feasibility, proof interpretation, witness replay, result provenance |
| `formal.backend` | OTP custody and native lifecycle | generation, DAG import, scoped assertions, check, observations |
| Rust adapters | Solver-specific native objects | direct Z3 C API or OxiZ Context; no SMT script fallback |

Terms contain no pointers, native handles or owner PIDs. Session registries
intern shared subterms once and import only new nodes. Native generations
prevent stale handles; reset preserves the portable terms. Source origins stay
outside semantic term identity. The wire is bounded packet-4 ETF with binary
user names and a fixed atom vocabulary. The solver runs outside the BEAM.
Hard deadlines close and retire the owner; EOF terminates even a busy worker.

The facade accepts native scalar sorts and schemas for nullable values,
Options, finite keys/maps/sets/bags/relations, bounded vectors/bytes, tagged
sums and fixed-scale Decimal values. Theory modules remain independently
usable pure functions. Builder callbacks construct a model; this does not
certify the implementation of an arbitrary BL callback.

## Which interfaces this opens

“Implemented” below means a concrete prototype fragment, with the scope of its
receipt; the atlas carries the detailed contracts and open questions.

| Interface family | Prototype / remaining boundary |
| --- | --- |
| Bool and truthiness | Typed Bool; reviewed scalar ANF truthiness |
| Unbounded Int | Native arithmetic; no machine-width approximation |
| Division profiles | Partial toward-zero quot/rem, divisor-sign BL mod, separate Euclidean remainder |
| Exact rational / Real | Native rational terms; algebraic model values remain opaque |
| Decimal and quantization | Fixed-scale exact coefficients; numeric versus representation equality; contexts/rounding remain |
| Finite floats / IEEE | Native FP constructors; finite-result outcome profile; full BEAM arithmetic lowering remains |
| Fixed-width BV | Native wrapping arithmetic, comparisons, shifts, extract/concat/extend |
| Bytes / bitstrings | Bounded byte vectors; explicit BV layouts, codecs and overflow profiles |
| Codepoint text / regex | Native codepoint strings; regex constructor vocabulary remains |
| Grapheme text | Runtime canaries and reviewed boundary; grapheme decision procedure remains |
| Names / identities | Closed nominal universes; open runtime atom/symbol identity remains |
| Enums / algebraic data | Native enum plus finite tagged sums; recursive native ADTs remain |
| Products / records | Model payloads exist; standalone nominal product API remains |
| Option / Result / errors | Presence, nil, partial selectors and raisedness; exception identity remains |
| Finite lists | Native Seq probes; BL list representation and list-specific operations remain |
| Vectors | Bounded indexed values, current nth/defaults and proposed strict access |
| Lazy prefixes | Scoped proposal; productivity, effects and infinite streams remain |
| Maps | Finite presence-aware updates, lookups, cardinality and extensional laws |
| Sets | Finite characteristic vectors, algebra and cardinality |
| Bags | Finite multiplicities; explicitly weaker than queue order |
| Equality / ordering | Typed SMT identity, domain equality, outcome equivalence; generic runtime repair proposed |
| Uninterpreted functions / sorts | Native terms and explicit model opacity |
| Quantifiers | Native forall/exists, binder scope checks; triggers and completeness remain |
| Recursion / induction | State induction obligations; recursive definitions/source termination remain |
| Finite choice / PB | Bool/Int finite encodings; specialized PB/weighted APIs remain |
| Relations / orders / graphs | Finite closure, cycles, partial/strict order and delegation |
| Pattern coverage | Tagged constructor coverage, strict selectors and partial matches |
| Refinements / units / contracts | Versioned descriptor seam; dedicated units/refinement elaboration remains |
| Function equivalence / symbolic execution | Reviewed scalar ANF; successful value plus raisedness; general calls remain |
| Termination / rankings | Obligation design; whole-call-graph implementation remains |
| Size / cost | Explicit collection bounds; general cost semantics remains |
| Effects / frames / commutativity | Pure update laws; checked source effect summaries remain |
| Ownership / capabilities | Finite delegation relation; runtime admission stays operational |
| State safety | Initiation, preservation, feasibility and bounded traces |
| Temporal / fairness | Safety substrate; liveness/fairness/model checker remains |
| Actor protocols / queues | Capacity and failed-step models; live BEAM scheduling/order remains |
| Migration / simulation | Explicit model-to-model initial and step simulation; hot-load admission remains |
| Datom integrity | Source/key semantic review; database model integration remains |
| Bitemporal data | Interval/timeline interface proposal; implementation remains |
| miniKanren / residual SMT | Typed residual constraint design; scheduler/unifier integration remains |
| Horn / invariant inference | State obligations; native fixedpoint/Horn interface remains |
| Optimization / MaxSMT / Pareto | Exact bounded integer optimization; native optimization/soft constraints remain |
| Synthesis / abduction / repair | Finite grammar candidate search and universal checks; general synthesis remains |
| Enumeration / shrinking / counting | Scalar projection enumeration with UNSAT completeness; counting/shrinking remain |
| Cores / witnesses / certificates | Native Z3 cores, shared deletion explanations, independent replay; certificates remain unchecked |
| Operational observations | Captured runtime canaries; facts carry explicit assumptions and never grant authority |

The same `formal.query` is used for theorems, counterexamples, relation laws,
trace safety and simulation obligations. Enumeration, finite optimization,
finite grammar synthesis and deletion explanations are implemented once above
both solvers. They stop on unknown or incomplete evidence. Finite sample limits
do not turn into completeness claims; optimization only claims optimality in
its declared bounds.

## What OxiZ changes, and what belongs to BL

The native term interface is possible with **both** backends. Z3 already has a
native AST API and [user propagators](https://microsoft.github.io/z3guide/programming/Example%20Programs/User%20Propagator/).
Maps with presence, partial arithmetic, domain-aware equality, symbolic traces
and repair are BL design work; replacing Z3 does not supply these semantics.

OxiZ's concrete attraction is a Rust implementation whose internal types and
decision procedures can be developed alongside a Rust worker. That makes a
custom extension an attractive research direction. Its public theory and
propagator traits are not a verified, automatically wired plugin seam into the
main Context/Solver. A module existing in the source tree is not a callable,
qualified BL capability. Z3 also permits custom propagation; neither backend
makes distributed BL state an SMT theory automatically.

This worker pins OxiZ **0.3.4**, `oxiz-core`/`oxiz-solver` with `std` and default
features disabled. Results describe that exact feature selection, not every
OxiZ crate/feature. [Upstream documents open limits](https://github.com/cool-japan/oxiz#honest-limits),
including Bool-argument UF, scalar models and Real division. Our native probes
measure actual fragments and keep unknown/unsupported distinct from matches.
The Z3 adapter uses the exact patched library selected by the SDK runner.

## Evidence and semantic review

The retained evidence includes runtime canaries, source discovery, a language
feature matrix and native theory probes. A qualification receipt records exact
source, SDK, native artifacts, commands and result counts. The initial native
run is retained in [native-before-normalization.json](evidence/native-before-normalization.json):
it exposed a genuine NaN identity mismatch on the direct OxiZ route. Native
import now normalizes NaN literals to SMT's single NaN; raw payload identity
belongs to BV, and NaN FP observations remain opaque. This narrow correction
does not establish general symbolic FP completeness.

Results keep raw solver status, interpreted verdict, model availability,
independent replay, certificate status, authority and scope separate. A SAT
answer whose witness cannot be replayed is a `candidate`. A failed replay is
`invalid-model`. Proof preflight exposes inconsistent assumptions as `vacuous`.
Persistent session assertions participate in meaning, free-variable replay,
preflight, evidence and cache identity. Observation requests do not add facts.
All experiment answers are untrusted; promotion into compiler caches is disabled.

The semantic review recommends fixing numeric equality, choosing coherent
user-facing key equality, and keeping representation equality explicit. It
also identifies the old negative-divisor modulus translation defect. The
[reviewable equality patch](proposals/numeric-equality.patch) is **unapplied**
and BEAM-only. It includes tests/docs and Datom expectation changes. Cross-target
JS and hash-container semantics need their own qualification; the pinned
runtime observations are not relabeled as proposed behavior.

## Reproduce

From the worktree root, with only one substantive check at a time:

```sh
research/formal-logic/build
research/formal-logic/run test research/formal-logic/test/kernel_test.bl \
  research/formal-logic/test/backend_test.bl research/formal-logic/test/api_test.bl \
  research/formal-logic/test/source_test.bl research/formal-logic/test/features_test.bl \
  research/formal-logic/test/native_test.bl research/formal-logic/test/advanced_test.bl
```

The locked release build has a 4 GiB/no-swap cap, one Cargo job and a 30 minute
ceiling. Checks use the exact pinned launcher in one cold VM, a private runtime
directory, a 4 GiB/no-swap cap and a 15 minute ceiling, then remove that directory.
No daemon, SDK build or application startup is part of these checks. The
historical scalar worker remains available under `research/oxiz-prototype`.

Next integration work should qualify the reviewed semantic changes, migrate
the oracle/obligation/cache seam to this typed query contract, and add source
summaries for pure user functions and collection operations. Then the most
valuable language experiments are refinement contracts, residual miniKanren
constraints, Datom invariants and actor protocol simulations. Each can reuse
the term/value/query/evidence architecture while retaining its own semantic
and operational boundaries.
