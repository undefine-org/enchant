# Compute track: integrating Mojo and MAX into Beam Lisp

Research date: 2026-10-24. No compiler installation, build, GPU workload, or BL
runtime check was performed. This is a feasibility assessment with explicit
unverified boundaries, independent of the scene-renderer branch.

## Announcement verified

Chris Lattner posted the main announcement on October 23:
[opening Mojo and MAX](https://x.com/clattner_llvm/status/2113639627445965251),
then [hardware and compute scope](https://x.com/clattner_llvm/status/2113640127562162437).
X returned 403; the original text and dates were retrieved through FxTwitter.
The latter distinguishes public NVIDIA/AMD/Apple support from other targets.
These are announcement claims, not evidence that every target is usable here.

The first-party release is [Modular 26.7, October 22](https://www.modular.com/blog/26-7).
Mojo's full compiler opened earlier, on
[August 18](https://www.modular.com/blog/mojo-open-source). The new change includes
MAX's previously closed graph compiler, runtime, and hardware implementation.

Inspected Modular revision: `da0db31d422e19ad5952d8d106b6da1d6899cf0a`.
The [repository map](https://github.com/modular/modular/blob/da0db31d422e19ad5952d8d106b6da1d6899cf0a/README.md)
identifies Mojo, GraphCompiler, MLRT, driver, accelerator kernels, and framework
components. Treat this source pin separately from the 26.7 release binary.

## Source availability and integration rights

Mojo uses Apache 2.0 with LLVM exceptions. MAX has mixed licensing; component
headers matter. The newly opened internals use the custom
[MAX License](https://www.modular.com/legal/max-license), dated October 21.
It permits application/object-code distribution subject to conditions, restricts
modified-source distribution, and places branding requirements on certain hosted
AI services. Its AI clause expressly permits interoperability development while
restricting using MAX to generate a replacement. Separately licensed components
retain their own terms. This makes integration materially different from
vendoring all internals into an unrestricted BL source distribution.

Architectural implication: prefer an independently maintained BL adapter and
upstream runtime dependency over a fork of MAX internals. This is a product
choice informed by the license text, not a legal clearance for a particular
shipping arrangement. Recheck exact artifact licenses before redistribution.

## Three distinct integration routes

### M1: Mojo kernels with a narrow native ABI

Compile generated or authored Mojo functions and expose an explicit C-compatible
boundary. [Compilation documentation](https://mojolang.org/docs/tools/compilation/)
includes shared-library/object outputs. The inspected compiler test includes
exported C-ABI functions. Neither fact independently proves that our desired GPU
library links and runs inside a BEAM host with no additional runtime setup.

BL supplies packed inputs, metadata, bounded execution, and result ownership.
A small native bridge handles ABI and resources. Reuse
[vm.native](../../../../priv/std/vm/native.bl) and existing host lifetime machinery
where possible. Do not expose raw executable pointers as normal BL values.

This is the most direct kernel interoperability spike. It can avoid Python at
runtime if the specific compiled artifact and dependencies support that route.
Prove that with an actual link/load test rather than inferring it from “C ABI.”

### M2: MAX graph execution with a native bridge

The [MAX C API](https://max.modular.com/api/c/) exposes context/model/tensor/device
operations. The checked-in
[C example](https://github.com/modular/modular/blob/da0db31d422e19ad5952d8d106b6da1d6899cf0a/max/examples/capi/README.md)
compiles a graph through Python, saves a device-specific artifact, and executes
it from C. That establishes a route for native execution, not a stable native
API for constructing and compiling arbitrary BL graphs.

Separate compile-time and runtime dependencies. A Python-assisted build pipeline
can still produce a Python-free execution path. If avoiding Python in both is a
requirement, it is additional work and must have its own test. Audit public API
coverage before binding internal GraphCompiler C++ classes.

This route buys graph optimization, library operations, and mature device
execution mechanisms. It is particularly relevant to tensor/model workloads.
It does not automatically compile arbitrary BL recursion, maps, or effects.

### M3: BL region IR lowered to the compiler stack

Longer term, keep BL as the sole authoring language for supported computations.
The frontend proves/checks region obligations, selects representations, and emits
a backend form. Initial code generation can produce Mojo source plus stable
ABI wrappers. Direct MLIR integration can follow if it has a maintainable seam.

The [compiler map](https://github.com/modular/modular/blob/da0db31d422e19ad5952d8d106b6da1d6899cf0a/Mojo/docs/compiler/README.md)
identifies MLIR tools that are internal rather than public SDK interfaces.
Open compiler source helps investigation; it does not establish a stable
embedding API or ABI for every dialect/pass. Treat direct internal-IR emission
as a maintenance commitment, not the easiest first-party integration.

## What first party and seamless should mean

A first-party compute subsystem should provide BL values for devices, typed
buffers, computation descriptions, and asynchronous results; integrated tooling
for diagnostics, build/install, dependencies, and inspection; and BL-owned
lifecycle/authority semantics. Users should not manually run a separate Python
program to execute an ordinary supported BL operation.

First party need not mean every instruction is implemented in BL or lives on a
BEAM scheduler. An official backend can execute in a supervised native worker.
In-process execution is a separate deployment/performance policy. Choosing one
must not change the language meaning or hide transfer cost.

Proposed architecture:

```text
BL source and required contracts
        |
resolved region IR, numeric/layout/ownership obligations
        |
backend admission + cost/availability choice
        +-- generated BEAM / existing native path
        +-- generated Mojo + versioned native ABI
        +-- MAX graph/artifact adapter
                    |
          owned device context, buffers, events
```

All names are conceptual; no new compute API is shipped by these notes.
Keep backend choice separate from application semantics. A manually authored
foreign kernel is useful interoperability but not automatic BL lowering.

## Hard engineering boundaries

- **Data representation:** dtype, shape, strides, alignment, byte order,
  mutability, aliasing, and device residency are part of the contract. Avoid a
  host list allocation per element and avoid serializing entire tensors via JSON.
- **Ownership:** retain backing storage until all device events using it finish.
  BEAM binaries must remain immutable; GPU writes need owned native buffers.
  Resource destruction and hot reload cannot free code/context beneath a kernel.
- **Scheduling:** do not block normal BEAM schedulers on compilation or GPU waits.
  Native workers or asynchronous bridges should report completion as messages.
  A dirty NIF is not automatically cheap, cancellable, or isolated from VM crashes.
- **Faults and cancellation:** dropping interest differs from physical device
  cancellation. A caller dying must not prematurely free shared device storage.
  Replay only operations whose effects and input identities permit it.
- **Numerics:** specify integer overflow and float width, rounding, NaNs, FMA,
  reduction order, and fast-math permissions. Exact BL arithmetic cannot be
  silently replaced with wrapping SIMD. Preserve refusal and fallback reasons.
- **Caching:** include source/dependency identity, numeric policy, dtype/layout,
  compiler/runtime versions, target architecture, driver compatibility, and
  relevant flags. Record which artifacts are device-specific.
- **Distribution:** enumerate compiler, runtime, accelerator libraries, drivers,
  licenses, and per-platform availability. A thin binding alone does not solve
  deployment or guarantee all machines get the same capabilities.

Zero-copy must be verified per boundary. MAX 26.7 specifically distinguishes
CUDA device-pointer borrowing from other staging/copy paths in its
[release notes](https://max.modular.com/releases/v26.7/). No general zero-copy
claim follows for a BEAM binary, a discrete GPU, or a different device backend.

## Small decisive experiments

M0: Pin SDK/source versions and inspect exact artifact licenses and installed
hardware. This host exposes NVIDIA and Intel DRM devices, but mojo and
nvidia-smi were not found on PATH. Device nodes alone do not establish supported
GPU architecture or working drivers. Do not assume this host can benchmark MAX.

M1: Export a scalar/packed-buffer CPU Mojo function, load it through a minimal
bridge, verify reference results, and enumerate runtime dependencies. Measure
cold compile, warm empty call, marshalling, and actual work separately.

M2: Repeat with a small GPU vector transform and many operations on resident
buffers. Verify correctness and lifetimes on owner death, revision change, and
shutdown. Test device absence and errors. Measure host/device transfers separately.

M3: Build one MAX vector graph through the documented pipeline, execute through
the C API from BL, and determine exactly what remains Python-dependent. Audit
whether current public interfaces can construct the desired graph without it.

M4: Extract one ordinary BL region to generated Mojo. Compare the exact same
source semantics across reference, BEAM, CPU-native, and GPU paths. A source-
authored kernel wrapper alone does not satisfy this milestone.

M5: Real workloads: packed byte processing, dense transforms/reductions, procedural
pixels, and irregular work. Use the existing evaluation protocol and include
whole-call cost, tail latency, memory, and unrelated BEAM process responsiveness.

## Decision

This is a credible way to avoid building a hardware compiler and kernel ecosystem
from scratch. Recommend a versioned BL backend architecture with Mojo-kernel
and MAX-graph spikes evaluated separately. Do not commit to a monolithic runtime
rewrite or internal MLIR dependency before those measurements. Integrating a
compute platform does not establish any logical correctness theorem; keep the
logic track's evidence and acceptance independent.
