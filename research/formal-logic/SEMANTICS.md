# Semantic decisions and proposed changes

The experiment runs on the immutable SDK recorded in `sdk-pin.json`. Its current
runtime observations, pure proposed profiles and backend qualifications are
different evidence. The patch in `proposals/numeric-equality.patch` is an
**unapplied, unqualified BEAM proposal**. It must not change the meaning assigned
to results obtained from the pinned SDK.

## Equality: repair the inconsistent relation

The reproduced current-runtime triple is:

```clojure
[(= 1.5M 1.5) (= 1.5 1.50M) (= 1.5M 1.50M)]
;; current: [true true false]
;; proposed exact-value profile: [true true true]
```

This is a bug: generic equality is not transitive. The immediate cause is the
Decimal/Decimal representation exception in `priv/boot/rt.bl:k-eqv`, around
lines 2070–2096. The generic comparator already compares all finite numbers by
their exact rational values (`ratio`, `number-num-cmp`, around 1660–1690).
Floats use their actual IEEE value, never their printed approximation.
`semantic-key` and `semantic-hash` use that same exact rational projection.

**Recommendation:** remove the Decimal exception and define generic numeric
equality by that existing exact comparator. Preserve scale in storage, printing
and arithmetic. Add `decimal/same-representation?` for coefficient-and-scale
equality, including the Java `BigDecimal.equals` oracle. These are separately
named relations, not backend choices. In particular, proposed `(= 0.1 0.1M)`
remains false; `(= 0.5 0.50M)` is true.

This also makes leaf equality agree with equality inside a vector, list or
metadata wrapper. The current sequence walk uses `k-compare` rather than the
Decimal exception; current nested equality must not be used as evidence that
the scalar exception is coherent.

Target files are `priv/boot/rt.bl`, `priv/lib/decimal.bl`, the Decimal/Num source
comments and `docs/exact-decimals.bl.md`. Focused tests are the proposed
`test/bl/numeric_equality_test.bl`, existing `test/bl/host_num_test.bl` and
`test/bl/decimal_oracle_port_test.bl`. Oracle reference answers remain unchanged;
its BL spellings of Java `.equals` call the explicit representation API.

## Hash keys and Datom

Ordinary BL maps and hash sets currently have a different key relation from
generic `=`. `rt/hash_key` strips metadata but otherwise retains raw BEAM terms;
`coll-get`, `coll-assoc` and `BeamLisp.Set` delegate to native maps/MapSet.
Consequently, even before the proposed fix, `(= 1 1.0)` is true while
`(get {1 :present} 1.0)` is nil. The JS runtime documents and implements a
separate `keyEq` relation. This is an existing, deliberate representation
boundary and a language-design limitation; it does not explain or excuse a
nontransitive generic equality relation.

The proposed equality patch does **not** redesign hash collections. A unified
language key relation needs a separate decision and implementation that retains
original keys, checks collisions and covers composite values. Replacing stored
keys directly with `semantic-key` tokens would expose implementation keys and
lose that contract. Whether generic equality should imply interchangeable
ordinary map/set keys remains an explicit qualification gate, not a law this
prototype presently satisfies.

For the proposed language profile, prefer generic-value keys for user-facing
maps/sets and a named raw-key interoperability profile where native BEAM
identity matters. Universe admission must use the selected key relation too:
`[1 1.0]` cannot be two distinct generic-value keys merely because raw hashing
keeps them apart. The current fixtures use unambiguous keyword/integer labels.

Datom already has specialized equality keys. `datom.index/value-key` uses
numeric semantic keys; `datom.codec` encodes numeric Decimal scale variants to
the same ordered index bytes; its hash join buckets by semantic key and still
unifies candidates. The current regression
`test/bl/datom/query_composite_join_test.bl:semantic-key-collisions-do-not-establish-equality`
expects a scale-variant lookup not to match. Under the proposed profile it must
match, with direct scan and hash join agreeing. Stored payloads must still
round-trip their original coefficient and scale.

**Inference to qualify:** removing the equality exception requires no index
format bump or reindex because it changes unification, not codec bytes. Preserve
`datom.codec/INDEX-VERSION` and the immutable `datom.identity/value-v1` contract.
Check this inference with `decimal_codec_port_test.bl`,
`datom/sequential_key_test.bl`, composite joins, uniqueness/upsert cases and
lossless payload tests. Existing index uniqueness may already collapse scale
variants; the changed query relation must agree with that behavior.

## Presence, failure and model scope

| Distinction | Interface decision |
| --- | --- |
| Missing key versus present nil | Independent presence term; lookup returns typed Option. Some nil and None differ. |
| Strict versus lenient access | Current nullable `vector-nth` and defaulting `vector-nth-or` retain their profile; proposed `vector-at` explicitly fails outside its index domain. |
| Runtime result versus exception | `:defined` is a Boolean term. Inactive payloads cannot establish equality or impose constraints. |
| Runtime validity versus encoding limit | `:within` is separate. A valid vector append can leave represented capacity without raising. |
| Bounded safety versus induction | Trace checks carry depth and stuttering scope. Initiation, preservation for every transition and initial-state feasibility are separate induction gates. |
| Value versus outcome equivalence | `formal.value/equivalent` compares raisedness and successful results. It currently does not compare exception type, message, effects or termination. |
| Counterexample versus live execution | A model must be independently replayed before being called a validated witness; a transition-model trace is not a recorded BEAM trace. |

Finite maps, sets, bags and relations are exact over their declared universe,
not over every possible BL term. Bounded vectors/bytes retain capacity and
element bounds. Abstract scopes remain abstract even when traces are bounded.
Unknown, unsupported, unavailable and outside-model are separate outcomes;
none means proved, safe or refuted.

## Numeric exceptions and integer modulus

Current Decimal arithmetic deliberately refuses Float operands. Integer lifting
is exact; converting a Float requires a named approximation operation. Keep
that refusal distinct from exact comparison of the two mathematical values.
Division by zero and nonterminating exact Decimal division are outcomes, not
free SMT values. A proof of a successful arithmetic rewrite needs its explicit
nonzero/definedness obligation; silently assuming away a possible exception is
not an equivalence proof.

There is a separate concrete bug in the old `system.smt` path:

```clojure
(mod 7 -3)   ;; BL: -2; old SMT lowering: (mod 7 (- 3)) = 1
(mod -7 -3)  ;; BL: -1; old SMT lowering: (mod (- 7) (- 3)) = 2
```

At `priv/lib/system/smt.bl:117`, Core `mod` is mapped directly to SMT Euclidean
`mod`. Thus lowering `(>= (mod a b) 0)` with `b = -3` yields a solver theorem
although runtime `a = 7` refutes it. Existing `smt-quot`/`smt-rem` reconstruct
toward-zero quotient and dividend-sign remainder correctly for nonzero divisors;
they should not be replaced with direct `div`/`mod` aliases.

For nonzero `b`, let `e = SMT.mod(a,b)`. Exact BL floor modulus is
`ite(e = 0 or b > 0, e, e + b)`. Alternatively reconstruct BL `rem` and adjust
its nonzero result to the divisor's sign, as implemented by
`formal.numeric/modulus`. The term implementation already has explicit
`:defined (b != 0)` and a versioned profile; Euclidean remainder has its own
explicit API. Fix the old lowering by removing the Core/mod table alias and
adding an exact resolved-call branch. Extend
`test/bl/system/smt_quot_rem_test.bl` with the four operand-sign examples and
universal nonzero-divisor laws: `abs(m) < abs(b)`, nonzero `m` has the divisor's
sign, and `a - m` is divisible by `b`. The proposed equality patch deliberately
does not mix this separate translator repair into its diff.

## Text and target qualification

BL string count/indexing uses graphemes; SMT string length/indexing uses Unicode
codepoints. Byte vectors are neither of those. A source lowering must name its
unit and refuse or prove any conversion; identical operation names do not make
these semantics interchangeable.

The JS Decimal equality and generic comparison currently round a Decimal to
`Number` when paired with Float (`priv/lib/js/rt.mjs`, around 576 and 651).
Changing only BEAM cannot qualify cross-target equality. A JS follow-up must
share one exact BigInt rational projection between generic equality and
comparison, extracting IEEE sign/exponent/significand with `DataView`; it must
not convert a Decimal through `Number`. Preserve its separately named key
relation until the collection decision is made. NaN/infinity and signed-zero
profiles need explicit admission policies; a finite-number proof does not
qualify them.

Native FP terms must also declare rounding and choose their equality relation.
IEEE `fp.eq` makes positive and negative zero equal and makes NaN unequal even
to itself; structural equality of IEEE bit patterns asks a different question.
Neither relation should silently inherit the finite-number generic profile.

## Gates before adopting a proposed profile

1. Preserve reproducible current-SDK canaries and label changed expectations as
   proposed. Keep the current pin and backend evidence intact.
2. Review and commit one coherent runtime/doc/test batch in the integration
   checkout. The attached patch is review material, not an applied change.
3. Batch boot/host changes before compiler-floor regeneration and produce one
   qualified SDK through the existing workflow. Record its immutable artifact
   identity and a new qualified pin; reuse it for focused checks. Do not create
   one SDK per test or agent.
4. In one capped VM, check finite-corpus reflexivity, symmetry and transitivity;
   compare-zero agreement; nested and metadata equality; equal-implies-equal
   semantic key/hash; exact/inexact Float boundaries; explicit representation
   equality; and unchanged Decimal arithmetic/rounding. Then run the focused
   Datom cases above on the same SDK, serially.
5. Qualify the corrected old modulus lowering separately, including failure
   obligations. Re-run the term profiles against both native backends with
   independent witness validation; backend agreement alone is not validation.
6. Report BEAM, JS, ordinary hash-key semantics, native backend support and
   finite/bounded scope independently. Unqualified gates remain visible.
