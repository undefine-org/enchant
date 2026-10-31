# Evaluation protocol: making the goal decidable on a declared corpus

## Claim form

Every claim has five fields: capability, workload/domain, correctness criterion,
resource conditions, and comparison result. For example: a particular source-
derived byte pipeline completes faster end-to-end at declared sizes on a pinned
host, with identical results under declared wrapping arithmetic.

That claim is testable. “BL is faster” without a domain is not. “Better on almost
everything” becomes a collection of such claims with predeclared coverage and
aggregation. Do not choose weights after seeing the results.

## Two comparison lanes

The language lane compares source, compiler, runtime, and proof mechanisms on
matched work. The product lane compares the complete task with available
libraries and tooling. A BL graphics library may make a better product even
when its kernel is external. Record both conclusions without conflating them.

Implement equivalent algorithms first. If a different algorithm is a legitimate
advantage of one environment, report it in a separate application comparison.
Never hide a BVH, lower resolution, different convergence threshold, or omitted
proof obligation inside a language speedup claim.

## Proposed corpus

| Family | Cases | Correctness and stress points |
|---|---|---|
| Byte pipelines | map/filter/sum, checksum, histogram | Empty input, wrap/range semantics, scalar vs large output |
| Dense numerical work | vector transforms, dot/reduction, small matrix batches | Precision, reduction order, packing, transfer |
| Uniform pixel work | Mandelbrot-style image, procedural texture | Exact dimensions, iteration limit, colour mapping |
| Irregular numerical work | Variable-depth rays or bounded search | Divergence, imbalance, termination bounds |
| Scene rendering | Fixed text/path/alpha/transition film | Same assets, timestamps, quality, visible output |
| Stateful application | Concurrent jobs with one failed worker | Accepted-result preservation, isolation, tail latency |
| Required scalar laws | Bounds, arithmetic invariants | Real violations, unknown theory, timeout |
| Required recursive laws | Permutation/sortedness, state invariant | Induction, missing assumptions, invalid proofs |
| Agent changes | New scene, refactor, invariant-preserving feature | Same intent, budget, tools, and acceptance checks |

Not all families will be supported immediately. Unsupported is an explicit
capability result, not an infinite timing sample to blend into a speed average.
Use real consumer cases as well as small examples that isolate a mechanism.

## Versioning and environment

Record repository commits and dirty-tree status for both sides, release/build
identities, compiler flags, OTP, Rust, clang, drivers, operating system, CPU/GPU,
core/thread count, RAM, swap pressure, and power/performance mode. Keep raw
commands and data with the report. Pin font/image assets for visual cases.

The current docs source pin is not an executable baseline. The video release
and a current Bend build must be separate labels if both are evaluated. Check
actual command syntax against the pinned tool rather than copying old Bend 1
instructions into a Bend 2 run.

Use the checkout ./bin/bl. Before any BL processes, inspect scripts/bl-mem.
Avoid competing cold VMs and cap heavy runs as required by root AGENTS.md.
Use private runtime directories and cleanup handlers for any test daemons.

## Timing boundaries

Report these separately where applicable:

1. Cold process start and source/dependency load.
2. Analysis/type/proof checking.
3. Code generation and native/GPU compilation.
4. Warm dispatch, queue wait, marshalling, transfer, execution, and result decode.
5. End-to-end artifact production, including encoding when comparing film export.
6. Warm edit-to-accepted-result latency and invalidation scope.

A one-time compile cost can be amortized only when the use case reuses the code.
A warm BL realm and a cold Bend compiler are different product states; report
each honestly. Kernel-only numbers are useful diagnostic companions, not
substitutes for application-visible time.

Rotate run order, separate warmup, retain samples, and report medians and spread.
For service workloads include tail latency and unrelated-client responsiveness.
Estimate uncertainty before declaring a small difference a win. Rerun noisy
cases under comparable conditions; do not discard slow samples without a
predeclared reason and retained record.

## Memory and resource accounting

Count the entire process tree, sidecars, browser workers, compiler, and encoder.
Include GPU memory and transfer/resident allocation where available. Account for
swap, retained code, caches, and idle workers. A tiny wrapper's BEAM reductions
do not measure CPU work performed in its native child.

Report peak and retained memory separately. Exercise many revisions, then close
the preview/application and verify owned resources are released. A fast warm
system that grows without bound is not a complete win.

## Correctness before speed

Choose independent oracles, known closed forms, boundary fixtures, and randomized
inputs. For image tests, define acceptable differences before measuring. Some
backends require tolerance; others can be exactly reproducible when pinned.
Byte-identical encoded videos are not required unless encoder determinism is
part of the contract.

For contracts, seed both real violations and unsupported propositions. Verify
that unknown/timeout is not accepted. Include specification weakening, stale
proof reuse, dependency changes, missing law coverage, and unsafe/foreign
assumptions. Run tests against the actual protected publication boundary.

For cancellation, distinguish no longer awaiting a result, suppressing its
publication, stopping managed work, and physically stopping native/provider work.
Only claim the level that the implementation verifies.

## Agent-workflow comparison

Use identical task descriptions, initial repositories, models, budgets, and
access to documentation. Record interactions, tool cost, elapsed time, attempts,
contract/test outcomes, and final artifact quality. Include repeated trials;
one lucky prompt is a demo, not a language ranking.

Useful tasks include changing text/layout without breaking timing, adding a game
rule while preserving reachability restrictions, optimizing a kernel without
changing arithmetic, and repairing a failed worker without duplicating effects.
The acceptance checks must not become weaker for the more convenient language.

## Result states and publication

Use: unsupported, incorrect, inconclusive, equivalent within uncertainty,
measured improvement, or measured regression. Capability coverage and performance
are separate columns. Publish counterexamples and refusal reasons alongside wins.

A milestone is met when its predeclared cases pass and its resource/quality
conditions hold. A project-level claim must name the completed milestones and
remaining gaps. Results expire as meaningful current comparisons when versions
or conditions change; retain historical reports rather than rewriting them.
