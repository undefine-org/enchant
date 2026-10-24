# Logic track: Bend and Beam Lisp

Research date: 2026-10-24. Source inspection only; no checker was executed.
This track is independent of GPU execution and scene-renderer delivery.

## Correct the starting comparison

BL already has inductive reasoning about transition systems. The relevant
source is [system.core](../../../../priv/lib/system/core.bl), especially
prove-box and verify-process. It checks establishment and preservation, supports
k-induction, and exposes completeness/unknown information. An unbounded safety
argument over a supported transition model is substantially more than testing
or bounded execution. The gap with Bend is not “BL cannot do induction.”

BL also has collection-content reasoning, refinement/simulation checks,
solver-backed counterexamples, effect/termination summaries, and generation-aware
callback admission. Their scopes differ. A callback receipt explicitly does not
establish arbitrary handler invariants or authorize migration. Keep those scopes
visible rather than combining all results into a generic safety badge.

## What Bend adds

The [guide](https://github.com/bendlang/bend/blob/295e996574573e3a88827b1cf7045b437333c8f0/guide/GUIDE.md)
describes propositions represented as types, proofs represented as definitions,
recursive proofs and equality rewriting. This supports explicit compositional
reasoning over recursively defined values, beyond a fixed source-to-SMT fragment.
Its checked fragment restricts recursion and tracks affine uses. That trades
expressiveness and annotation effort for a disciplined proof boundary.

The [BendTT kernel source](https://github.com/bendlang/bend/blob/295e996574573e3a88827b1cf7045b437333c8f0/bend2/bendtt.lean)
contains a separate checker and Lean soundness/consistency theorems. Its unusual
dead/live distinction is part of the argument; this is not simply conventional
universe-based dependent type theory. Inspection found no `sorry` tokens or
explicit `axiom` declarations in that file. This is source evidence, not a local
rebuild or independent audit. The parser/translation and machine-code backends
remain separate trust boundaries.

## Compare obligations, not engine names

| Question | BL mechanism established by source | Gap to investigate |
|---|---|---|
| Does a supported process preserve a scalar invariant? | Establishment plus transition preservation, optionally k-induction | Completeness and exact runtime-model correspondence |
| Does a list transformation preserve every element? | Some special collection theories exist | General user-defined structural proofs and reusable lemmas |
| Can a proof be passed as a checked value? | Evidence records exist | General proof-term typing and independent verification |
| Can an agent obtain a counterexample automatically? | Solver-backed witnesses | Quality, source mapping, reproducible replay |
| Must every protected update satisfy a law? | Some actual-code admission/lifetime gates exist | Uniform required-law acceptance for arbitrary protected definitions |
| Does evidence still describe running code? | Generation/code identity checks exist | Extend consistently across proof artifacts and foreign backends |
| Does numerical reasoning model execution exactly? | Int/Real and additional supported SMT theories | Explicit float/overflow/exception semantics |

An SMT solver and a dependent checker answer different sorts of questions.
Adding a general proof object need not replace automated discharge. Conversely,
a logic-programming or synthesis engine does not by itself verify the candidates
it discovers. Discovery can be elaborate while checking remains small.

## Concrete examples and acceptance

1. Account process: nonnegative balance under arbitrary legal transactions.
   Compare the same transition relation, input assumptions, and initial state.
   A BL inductive proof here should not be described as merely bounded testing.
2. Sorting: ascending output AND preservation of multiplicities. Empty output
   satisfies ascendingness alone. Test arbitrary lists, not only a fixed length.
3. Tree rewrite: evaluation is preserved by a recursive optimization. This tests
   structural induction, contextual substitution, and reusable helper lemmas.
4. Revision update: a proved invariant remains enforced after a dependency edit.
   This tests publication policy and evidence identity, not theorem syntax alone.
5. Floating point: algebraic associativity must not be accepted as a universal
   property of machine floating-point addition.

For every case record domain, assumptions, proof method, coverage, result,
proof artifact, trusted components, and enforcement boundary. Distinguish
proven, refuted, unknown, and partially covered. A countermodel of an induction
step may be an unreachable state; it refutes that inductive argument without
necessarily being a reachable application bug.

## Required-law acceptance is a policy layer

The useful rule is: a protected revision is publishable only when every required
obligation has current, complete, successful evidence under approved assumptions.
Unknown, timeout, stale dependencies, omitted transitions, and unmodeled init
cannot silently satisfy it. An explicitly assumed initial invariant must remain
visible as an assumption rather than being presented as proved initialization.

This matters in current BL: verify-process can report `:holds true` together with
`:complete false`, and some initialization cases are caller assumptions.
Consumers must inspect the whole scoped verdict. That shape is useful for
research diagnostics, but a required-law gate needs stricter aggregation.
This observation does not establish that existing consumers are buggy.

Keep optional optimization separate: a region can be refused and run on its
ordinary path. Required correctness cannot be recovered by executing an
unproved protected revision on a different backend.

## Numerical soundness needs an explicit audit

[system.smt](../../../../priv/lib/system/smt.bl) maps float tagsets to SMT Real.
Real arithmetic is not IEEE floating-point arithmetic. That alone is an audit
finding, not a demonstrated false accepted application: the actual supported
operations, abstractions, and consumers must be traced.

Require one of three explicit meanings: an ideal-real specification with a
proved abstraction connection; IEEE floating-point formulas; or refusal of
unsupported float claims. Do not use an ideal-real fact to authorize a machine
rewrite unless its refinement obligation is established. Apply the same
principle to exact integers versus machine-width overflow.

## Proposed order

L0: Inventory proof-producing/checking/enforcing paths and actual consumers.
L1: Required-law aggregator with precise scopes, assumptions, and dependencies.
L2: Independent evidence checking or proof-producing solver integration for a
small fragment; document the actual trusted computing base.
L3: General structural proof representation and reusable lemmas, validated against
the list/tree corpus. Evaluate established checkers before inventing a kernel.
L4: Connect proofs to actual published definitions and native artifact identity.

Preserve BL's automation and live-system evidence advantages. The target is a
small checkable semantic core with multiple discovery engines and strong runtime
binding. Do not make all dynamic BL code total or linearly typed merely to gain
a separately admitted logical fragment.
