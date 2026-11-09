# Term-based formal logic: implementation contract v1

This project explores a backend-independent formal interface for Enchant. The
existing OxiZ experiment is retained as historical evidence. One integration
committer owns this worktree; independent agents own the files assigned below.
Builds, VM checks, and publication are serialized by the root session. No agent
produces an SDK. Project checks reuse `sdk-pin.json`.

## Layers and ownership

1. `formal.term` (root): pure typed immutable expressions, signatures, sort
   checking, substitution, free variables, independent evaluation, DAG export.
2. `formal.value`, `formal.collections`, `formal.data`, `formal.numeric`
   (language_features agent): language profiles, partial results, finite-domain
   collections and derived Boolean laws. No solver I/O.
3. `formal.query`, `formal.backend`, `formal.logic`, `formal.source` (root):
   assertions/obligations, effectful owned sessions, evidence, proof/search
   procedures, source ANF integration. No SMT-LIB text on the new path.
4. Rust `src/formal/*` and `src/bin/formal-worker.rs` in the existing worker
   crate (native_backends agent): protocol, native Z3/OxiZ term adapters.
   Preserve legacy `src/main.rs`, `engine.rs`, and `wire.rs` unchanged. Add only
   `libloading = "=0.8.9"`; keep existing dependency features/profile intact.
5. Atlas, source inventory script, review dossier and research case catalog
   (theory_atlas agent). Distinguish proposals, implementations, observations,
   and qualification. Source discovery uses the project's pinned Codebase API.

## Sorts and terms

Sorts are canonical vectors: `[:bool]`, `[:int]`, `[:real]`, `[:string]`,
`[:bv width]`, `[:fp exponent significand]`, `[:rounding]`,
`[:array key-sort value-sort]`, `[:seq element-sort]`,
`[:uninterpreted name]`, `[:enum name [constructor-names...]]`.
ADT/recursive sort declarations are an extension with explicit capability
status, not silently replaced by an enum. Names and operation tags on the wire
are binaries; no arbitrary user atom interning. Numeric literal strings passed
to a native numeral constructor are permitted; SMT-LIB scripts are not.

A term is ordinary immutable BL data:

```clojure
{:formal/term 1 :op :add :sort [:int] :args [x y] :data nil}
```

Origins attach to assertions and source maps, outside semantic term identity.
There are no native handles inside portable terms. Workers retain a separate
generation-checked mapping from DAG IDs to native ASTs. Variables use `:var`,
their data is a binary name. Literals use `:bool`, `:int`, `:real`, `:text`,
`:bv`, `:fp-bits`, `:rounding`. Real data is `[numerator denominator]`, BV data
is an arbitrary integer, FP data is the unsigned IEEE bit pattern. Common ops:

* `:not :and :or :implies :xor :eq :distinct :ite`
* `:add :sub :neg :mul :div :mod :lt :le :gt :ge :to-real :to-int :is-int`
  (`:div`/`:mod` mean SMT Euclidean integer arithmetic; language variants are
  explicit profile lowerings, never aliases).
* `:array-const :select :store`
* `:str-concat :str-len :str-contains :str-prefix :str-suffix :str-at
  :str-substr :str-index :str-replace` (SMT codepoint semantics, not graphemes).
* `:bv-add :bv-sub :bv-mul :bv-and :bv-or :bv-xor :bv-not :bv-neg
  :bv-shl :bv-lshr :bv-ashr :bv-ult :bv-ule :bv-slt :bv-sle :bv-concat
  :bv-extract :bv-zero-extend :bv-sign-extend` (indexed op parameters in data).
* `:seq-empty :seq-unit :seq-concat :seq-len :seq-nth :seq-extract`.
* `:uf` has data `{:name binary :domain [sorts] :range sort}`.
* `:bound` has binary data with a binder-unique name. `:forall`/`:exists`
  have one Boolean body arg and data `[[binder-name sort]...]`. The binder
  nodes are native constants abstracted by native quantifier constructors;
  free bound nodes must be refused before solving. Do not silently turn them
  into free variables. Trigger support is a separately declared capability.
* FP arithmetic/predicates use `:fp-add :fp-sub :fp-mul :fp-div :fp-neg
  :fp-eq :fp-lt :fp-le :fp-is-nan :fp-is-inf :fp-to-ieee-bv`; arithmetic args
  start with a rounding-mode term where required. IEEE equality and bitwise
  structural equality are different operations.

Unimplemented operations return explicit `:unsupported` evidence. No erased
constraint, invented sort, approximation, or backend-specific text escape.

Root term API, available for independent feature modules:

```clojure
t/Bool t/Int t/Real t/String
(t/bv-sort width) (t/array-sort key-sort value-sort) (t/seq-sort element-sort)
(t/variable name sort) (t/bool value) (t/int value) (t/text value)
(t/real numerator denominator) (t/literal sort value)
(t/term? x) (t/sort-of x)
(t/app op result-sort args data) ; checked primitive escape within the catalog
(t/eq a b) (t/not x) (t/implies a b) (t/ite condition yes no)
(t/all terms) (t/any terms) (t/distinct terms)
(t/add a b) (t/sub a b) (t/neg a) (t/mul a b)
(t/lt a b) (t/le a b) (t/gt a b) (t/ge a b)
(t/div a b) (t/mod a b)
```

Feature modules may use `t/app` for vocabulary above, but must not depend on
the worker or query API. Pure term constructors reject sort/arity errors.

## Language outcomes and model bounds

A language-semantic value is a pure descriptor with `:formal/value 1`, `:value`
(a term or structured payload), `:defined` (runtime success), `:within` (inside
the representation/domain), `:constraints` (Boolean terms), `:scope` (exact,
finite-universe, bounded, or abstract, with parameters), `:domain` (decoding
and operation family), and optional `:errors` (named failure predicates).

**Runtime definedness and representation limits are independent.** Appending
past a bounded vector's represented capacity is not a language exception.
Queries carry all bounds and assumptions in their evidence. No bounded proof
is displayed as an unbounded language theorem. Model values retain absent,
nil, default, nonconcrete and unavailable distinctions.

The `formal.value` module exposes `make [payload opts]`, `lift [term]`,
`value?`, `term [value-or-term]` (requires scalar Boolean/primitive payload),
`defined`, `within`, `constraints`, `scope`, `terms` (all observable payload
leaf terms), and `decode [descriptor resolver]` (resolver takes a term and
returns a decoded native observation). Specialized collections expose their
own extensional equality; do not substitute equality of inactive payloads.
Feature constructors and operations return these descriptors consistently.

## Native protocol v1 (ETF)

The new binary is `formal-worker --backend z3 --z3-library /abs/libz3.so` or
`formal-worker --backend oxiz`. Protocol request and reply maps have fixed atom
keys; all dynamic names/op strings are binaries. Packet-4 framing and the 1 MiB
cap/EOF watchdog from the old experiment remain. Each packet's reply is a
single structured map. Errors do not silently retry a partially applied query.

Requests are tuples:

```clojure
(:hello)
(:reset generation)
(:load generation nodes assertions)
(:check generation assumptions observations solver-ms)
(:scope generation nodes assertions assumptions observations solver-ms)
```

These are native tuples made with `tuple`, proper lists with `to-list`.
`nodes` are topologically ordered `[id op-binary sort-wire [arg-id...] data]`.
Each vector in that description is a native proper list on the wire. `sort-wire`
is recursively a proper list whose first item is a binary kind name. Data is
native ETF scalar/list/map data; its keys are binaries (`"name"`, `"domain"`,
`"range"`). A repeated ID with a different definition is a protocol error.
`assertions` are `[[label-binary boolean-node-id]...]`; `assumptions` are Boolean
node IDs; `observations` are `[[label-binary node-id]...]`. Root owns all
source/shape metadata and counterexample decoding. Import nodes before the
scope push so immutable node identities/declarations survive assertion pop.
Reset invalidates every native identity and returns an incremented generation.
Stale generations are refused. Budget is 1..10000ms; BL adds its independent
hard deadline around the whole native exchange.

Successful reply common fields:

```clojure
{:ok true :protocol 1 :generation 0
 :backend {:name "z3" :version "4.16.0"}
 :status :sat|:unsat|:unknown
 :observations [["x" ["int" arbitrary-integer]]...]
 :model-status :available|:partial|:unavailable
 :core ["label"...] :core-kind :native|:unsupported
 :why {:kind :unspecified :message "..."}
 :stats {:solve-us integer :nodes integer :checks integer}}
```

Observation tags are proper lists: `["bool" bool]`, `["int" bigint]`,
`["real" numerator denominator]`, `["text" binary]`,
`["bv" width unsigned-integer]`, `["fp" exponent significand ieee-bits]`,
`["enum" sort-name constructor-name]`, `["array" default updates]`,
`["constructor" name [field-values...]]`, `["opaque" reason]`,
`["unavailable" reason]`. Native adapters can initially refuse full array/ADT
materialization: observed scalar selects/testers/fields remain useful. A
nonconcrete observation never erases a SAT verdict; availability and validation
are separate. Native OxiZ cores may be explicitly unsupported. BL can derive a
separately labelled input-cover/deletion core; it must not call that native.

Hello reports implemented operation vocabulary and backend version; the BL
qualification harness, not the README/module inventory, determines which
capabilities are verified. Capabilities include operation/sort, requested
result kind, semantic profile, encoding bounds, and evidence provenance.

## Procedures and trust

SAT status, proof goal interpretation, model availability, model validation,
certificate validation, and scope are separate fields. `prove p` asks for a
counterexample to p under explicit assumptions/constraints/within; UNSAT means
proved in that scope, SAT yields a candidate witness requiring validation.
Equivalence compares raisedness and successful results. Unsupported and
unknown never mean refuted, safe, or proved. Backend agreement is measured per
query; there is no majority vote or fallback that changes proof authority.

Cache identity includes canonical typed DAG, semantic profile/version,
encoding/domain bounds, assumptions, backend/native artifact identity,
query/result mode, and relevant solver settings. Exploratory answers never
populate the compiler's trusted proof cache.

The project must catalog every family and every claimed BL feature, but
cataloguing is not implementation/qualification. Native, encoded, bounded,
abstract, unsupported, unknown, and deliberately deferred are distinct states.
