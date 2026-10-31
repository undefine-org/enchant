# Comparing BL with Bend without confusing the workloads

## What the comparison is for

“Better than Bend on almost everything it claims to be good at” is a direction,
not yet an experimentally decidable proposition. Turn it into a finite capability
matrix and preregistered workloads. For each, state what BL must support, what
counts as correctness, and what measurable improvement counts as a win.

A universal ranking over all possible programs cannot be established by a finite
benchmark suite. A decisive result on a declared corpus is attainable. Keep the
ambition broad while making each published claim narrow enough to verify.

## Current evidence and hypotheses

| Dimension | BL evidence | Assessment and missing evidence |
|---|---|---|
| Live application iteration | REPL/runtime model and generation-aware evidence | Promising advantage; measure complete edit-to-result workflow |
| Concurrent application ownership | proc.task and execution/environment machinery | Strong foundation; adversarial lifecycle tests still matter |
| Numerical region execution | Exact byte-pipeline experiments and native eligibility | Mechanism demonstrated; broad source extraction remains a gap |
| GPU language execution | No general integrated route established by this investigation | Treat as a gap, not an implicit benefit of BEAM parallelism |
| Required mathematical contracts | Automatic analysis exists; docs describe optional proofs | Required-law acceptance and inductive proof coverage need dedicated work |
| Agent usability | Structured source, introspection, shared live environment | Hypothesis until measured with equivalent tasks and budgets |
| Rendering workflow | scenario.film exports existing media | Useful integration substrate; not a custom drawing engine |

Bend's current documentation describes a native and GPU path alongside an
explicit proof workflow. It also acknowledges boundaries in numerical types,
tooling, and incremental compilation. Read those as a scope definition, not a
reason to dismiss its core contribution. [Primary overview and limitations](https://github.com/bendlang/bend/blob/295e996574573e3a88827b1cf7045b437333c8f0/README.md).

The guide documents independent parallel calls, an affine value discipline,
GPU dispatch, and a balance-sensitive fork/join scheduler. These are different
from BEAM's preemptible application processes. [Primary guide](https://github.com/bendlang/bend/blob/295e996574573e3a88827b1cf7045b437333c8f0/guide/GUIDE.md).

## Concurrency is not numerical throughput

An application may need many long-lived independent conversations, each waiting
on the network and preserving its own authority. Another may need a billion
arithmetic operations over contiguous floats. Both can use many cores, but their
cost structures are different.

BEAM processes support isolation, scheduling, and lifecycle management. They do
not make boxed arithmetic, generic dispatch, repeated allocation, or data copies
free. Spawning a task for every pixel is likely to spend substantial effort on
coordination that a coarse raster kernel avoids. Conversely, a fast fork/join
kernel does not automatically supply the operating model for a live service.

BL's strategic architecture should use each mechanism at the right granularity:
application ownership and responsiveness in BEAM, substantial admitted numerical
work in generated loops or kernels, with explicit boundaries and accounting.

## The native evidence must retain its baseline

The retained fusion experiment concerns one exact byte map/filter/wrapping-sum
pipeline, not floating point, rasterization, or arbitrary user callbacks. At
1 MiB, it reports approximately:

| Path | Whole-call time |
|---|---:|
| RT/transducer baseline | 149.210 ms |
| Fused BEAM | 50.066 ms |
| Resident native, including port boundary | 5.264 ms |
| Native inner kernel, separately measured | 2.535 ms |

These are historical reported medians, not reruns here. The actual experiment
records admitted inputs, oracles, sample ranges, and cold startup separately.
See [the retained report](../../rt-selfhost/fusion/RESULTS.md).

The result supports investing in fusion and representation. It does not establish
that BL beats Bend or C. The older offload experiment's much larger speedup used
a different baseline; do not substitute that ratio for the end-to-end figure.
Do not generalize a crossover observed on one host into a language-wide constant.

## Automatic analysis and explicit proof are complementary

Discovering that a function is pure, bounded, or terminating can make a system
safer and faster with little author effort. Requiring a proof that every legal
sequence of game moves preserves an invariant is a different obligation.

A solver may automatically discharge a formula within a supported theory. That
is not the same as proving an arbitrary recursively defined proposition.
Recursive structures, induction, quantifiers, arithmetic, and external effects
each introduce separate coverage and trust questions. Plan for both automated
discharge and a way to supply/check explicit evidence where automation stops.

There must be a visible difference between “could not prove this optional
optimization safe” and “could not establish this required application invariant.”
The first can use the ordinary implementation. The second must block the
protected acceptance boundary. This distinction belongs in BL's own design
regardless of the competitor.

## Correctness has a trusted boundary

A checked law only constrains what it says under its stated assumptions. A law
that sorting returns an ascending list permits a function that always returns an
empty list unless preservation of elements is also required. A program can be
correct relative to an inadequate specification.

Trace the actual trust chain: source resolution, translation into the proof
model, solver/kernel, generated artifact, runtime, and external inputs. A theorem
about mathematical integers does not authorize wrapping machine arithmetic.
A proof that a pure calculation terminates does not prove a remote provider
returns, or that an OS subprocess is physically cancelled on timeout.

A differential oracle is valuable regression evidence, but finite agreement is
not a proof of universal backend equivalence. Avoid promoting a successful
fixture matrix into a theorem about the entire compiler.

## Agent friendliness needs its own evidence

The meaningful unit is a successful, reviewed change: specify intent, inspect
state, edit code, obtain diagnostics, repair it, validate required contracts, and
produce a reproducible artifact. Source brevity alone is a weak proxy.

BL may reduce cost by keeping a live inspectable environment and reusing stable
analysis. It may also lose time to cold startup, stale cache mistakes, broad
invalidation, or opaque errors. Measure those rather than assuming a REPL wins.
An agent's ability to inspect structured objects is valuable only if it can bind
them to the exact running revision it is changing.

The renderer track provides an excellent demonstration of this workflow. It is
one case in the comparison corpus, not a substitute for native or proof evidence.
