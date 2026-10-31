# Programme for stronger compute, proofs, and agent workflows

## Architectural direction

Keep one language meaning across execution choices. BL should own analysis,
contracts, source identity, lifetime, orchestration, and explanation. Backends
supply mechanisms for executing admitted work. A numerical extension should not
quietly create another language with different arithmetic and exceptions.

The programme has independent streams. Required-law acceptance can advance
without GPU work. Native regions can advance without the scene renderer.
Renderer delivery must not wait for either.

## C0: Establish the boundary and baseline

Pin the BL revision, competitor version, build tools, hardware, and corpus. Audit
what is shipped versus research-only. Write down the numerical and proof fragment
for every sample. Preserve unsupported cases rather than translating them into a
more convenient benchmark behind the reader's back.

Deliver a capability inventory with reproduction commands and explicit unknowns.
The first report can have many blanks; a truthful inventory is more useful than
an aspirational feature matrix presented as reality.

## C1: General pure-region extraction and generated BEAM

Recognize a deliberately bounded family of ordinary source operations from the
existing compiler IR. Begin with known resolved functions, counted loops, typed
byte views, and map/filter/reduce where evaluation order is understood. Reuse the
existing analysis and lowerers; do not install another unrelated compiler stack.

A region records operations, layouts, arithmetic, ranges, effects, exception and
early-exit order, bounds, ownership/escape, and dependency identities. Preserve
exact BL integer semantics unless a machine-width rule is explicitly requested
or justified by range evidence. Floating-point reassociation is a separate
permission because changing reduction order can change the result.

Generated BEAM is a valuable first optimized path: it can remove intermediate
collections and callback dispatch while retaining VM conventions. Acceptance:
unmodified source exposes a region and runs equivalently against the generic
reference, including invalid inputs and exception ordering. Refusal identifies
which obligation failed. Generalization must go beyond equality to one fixture.

## C2: Shared native lowering and representation

Emit native code from the same region description. Start narrow and widen only
with explicit arithmetic and memory obligations. Packed inputs/outputs and
coarse batches are essential; fast arithmetic surrounded by repeated conversions
will lose end-to-end. Output materialization matters as much as input access.

Evaluate the existing native-host and resident-worker mechanisms. A regular NIF,
dirty NIF, or external worker has different fault, scheduling, cancellation, and
lifetime properties. Choose using measured whole-call costs and application
responsiveness. Do not bypass ERTS conventions on the assumption that arbitrary
machine code can replace an OTP JIT function body.

A compiled artifact's identity includes source/dependencies, semantic and layout
versions, compiler/backend, and CPU features. Lifetime is an owned resource;
unload only after outstanding users finish. A new hot revision must not mutate
an old export's executable meaning.

Acceptance: multiple source-derived regions, independent semantic references,
randomized and boundary comparisons, resource-failure tests, and meaningful
whole-call gains. A tested fast path remains a tested implementation unless
there is an actual general correctness proof.

## C3: Bounded parallel numerical execution

Use coarse chunks and bounded queues. Distinguish pure independent work from
operations with ordering or shared state. Preserve deterministic reductions when
required. Select chunk sizes through measurement; a single size is unlikely to
serve tiny byte scans and expensive ray integrations equally.

Measure irregular work as well as balanced work. A renderer's many objects,
variable ray depth, clipping, and text layout create different cost shapes.
Work stealing or adaptive splitting may help, but they bring overhead and must
not be selected by slogans. Resource use and responsiveness are acceptance
criteria alongside throughput.

Acceptance: scaling curves, small-job behaviour, queue contention, cancellation
semantics, and error propagation. All results account for data conversion and
synchronization. A process pool's existence is not proof of good scaling.

## C4: GPU execution as a separate major stream

A credible GPU path needs more than a binding that invokes somebody else's
shader. Define the BL fragment that compiles, its types and numeric behaviour,
address spaces, layouts, aliasing/ownership, divergence model, allocation limits,
transfer/residency policy, and runtime lifetime.

Choose one initial backend based on available hardware and maintainable tooling.
CUDA, Metal, WebGPU, and other targets have different capabilities. Do not
promise all targets at once. Include a clear capability/refusal report so an
unsupported operation is not silently moved into a misleading timing lane.

Start with a meaningful independent-pixel or array kernel plus a reduction.
Later test irregular recursion and higher-order cases if those enter the stated
coverage. Treat CPU/GPU agreement according to declared numeric semantics;
bitwise equality is not automatically available for floats.

Acceptance: ordinary BL source in the declared fragment executes on GPU, with
reproducible compilation, residency/transfer accounting, correctness checks,
error handling, and a CPU fallback whose selection is visible. Separate library
GPU use from language-level lowering in published results.

## P1: Required contracts and acceptance policy

Build a first-class distinction between optional evidence and required laws.
A required contract should bind to exact code and assumptions, describe the
supported logical fragment, and return proven/refuted/unknown with provenance.
Timeout, missing coverage, and stale evidence cannot count as proven.

Enforce at the relevant boundary: publication of a revision, deployment, or
replacement of protected code. In a live system this is more specific than
“before commit”: someone may evaluate an unsafe revision without committing it.
Keep the last accepted revision available after rejection.

A protected specification must not be silently weakened to make a change pass.
Record specification changes separately and make their effect reviewable.
Apply the existing source/authority model rather than treating a filename alone
as a security boundary. This is a product requirement, not a request for a new
manual approval flow on every development edit.

Acceptance: deliberate code violations fail, stale evidence fails, missing proof
coverage fails, unsupported formulas remain unknown, and valid updates publish
with exact evidence identity. Optional optimization still has its safe fallback.

## P2: Proof coverage beyond automatic scalar reasoning

Select a small set of recursive laws: list transformation preserves elements,
append preserves length, a state machine invariant survives arbitrary legal
steps, and a bounded traversal stays within its resource contract. Determine
which require induction and how the resulting proof evidence is checked.

Explore proof-producing automation, a small explicit proof representation, or
integration with an established checker. Keep discovery/search separate from
verification. A powerful search component can be replaceable if its output has
a small, well-defined checking boundary. State all axioms and foreign assumptions.
Do not claim a new trusted proof kernel merely because a solver returns success.

Acceptance: valid inductive examples and adversarial invalid ones, reproducible
checking, inspectable dependencies, and a documented trust chain. Numerical
float claims require their own model; mathematical-real proofs are insufficient.

## A1: Explainable, incremental agent workflow

Expose what was analyzed, what changed, what was invalidated, why a backend was
chosen/refused, which contract failed, and a concrete counterexample when the
engine can produce one. Keep results structured for agents and readable for
humans. Attach each result to the right source generation.

Measure cold setup and warm iteration separately. Track unnecessary invalidation,
cache growth, retained code, cleanup, and retained authority. The best diagnostic
is often a precise explanation of missing evidence rather than an attempted
universal inference that hides assumptions.

Acceptance: equivalent change tasks reach verified completion with fewer failed
iterations or lower elapsed/resource cost, without weaker specifications.

## Shipping order and stop conditions

Start C0, then C1 and P1 independently. Use C2 after region semantics are stable;
start P2 with a deliberately small corpus. C3 follows measured real kernels.
C4 is a major effort with its own gate. A1 should accompany every stream.

Do not delay useful CPU or contract work until GPU parity. Do not call a GPU
library wrapper parity with a compiler. Do not publish a winning score for a
workload that cannot yet produce the required result. Preserve failures and
revisit them as capabilities improve.
