# Incremental build pipeline prototype

This branch routes SDK restoration, application preparation, source priming and
SDK image assembly through one bounded task executor. Nix and the existing
artifact coordinator retain placement, durable job ownership and product custody.

The build tier discovers namespaces from flat file basenames, so these drivers
are named `build-inputs`, `build-execution` and `build-image`. No runtime host,
bootstrap floor or external package was added.

```mermaid
flowchart LR
  C[Checkout request] --> J[Existing artifact coordinator]
  J --> N[Nix build server]
  N --> I[Shared input observations]
  I --> P[Serial compiler preparation]
  P --> R[Bounded verified restoration]
  R --> W[One unit publisher]
  W --> A[Bounded image assembly and native proof]
  A --> S[One metadata publisher]
  S --> D[SDK and portable products]
  F[Content-addressed source facts] --> P
  F --> D
```

## Ownership and reuse

- `build-inputs/capture` resolves each input namespace once and hashes each
  resolved source path once per observation pass. Unit reuse compares exact
  constructor inputs, compiler/runtime identities and source resolution. A
  separate final observation validates the complete produced input set.
- `build-execution/reduce!` uses the existing native Task entry underlying
  `proc.task`, which is available before the SDK libraries have been compiled.
  Tasks retain Env and executable lifetime. Every completion opens another
  slot; the caller consumes results with bounded outstanding preparation.
  Failure stops and awaits owned tasks and drains their private result messages.
- SDK compiler workspaces stay on one owner. Workers verify and copy immutable
  retained units into private unit directories. The owner writes flat outputs
  and rejects conflicting module ownership. Application dependency waves and
  the toolchain barrier remain ordered; initializer publication retains
  source-plan order through a bounded ready window.
- `build-image/assemble!` gives each worker a small batch of at most sixteen
  complete units with disjoint image files. Task captures contain only that
  batch, avoiding repeated transfer of the whole SDK manifest. It calls the
  existing assembler, source relocator and native SDK
  inventory writer. Each native proof validates actual source and emitted bytes,
  including complete companion membership. The caller merges disjoint ownership
  and writes deterministic SDK and precompiled metadata after preparation succeeds.
- Source parts are primed before the compiler child. The same content-addressed
  frames feed its freshness checks, final image priming and the next unit-store
  archive. Both exact content and the existing build generation select reuse;
  missing or corrupt frames parse normally. Volatile timing stays in logs.
- The closed Nix worker moves the retained unit directory into its final output
  instead of copying it twice. SDK image copying requests filesystem reflinks
  with an ordinary-copy fallback. Portable ELF mutations retain separate bytes.

## Validation

Run the complete managed qualification under a process-tree cap:

```sh
scripts/bl-mem
systemd-run --user --collect --wait --pipe --working-directory="$PWD" \
  --property=MemoryMax=4G --property=MemorySwapMax=0 \
  --property=RuntimeMaxSec=10800 \
  python3 test/scripts/build_pipeline_vertical.py \
    --sdk /nix/store/RETAINED-SDK \
    --out .local/build-pipeline/vertical
```

The output directory must not exist. The harness makes a private engine copy;
it never edits the checkout or an immutable product. A configured remote Nix
builder and the normal `max-jobs = 0` policy are mandatory. It records actual
remote dispatch from the durable job stdout events, complete worker phase logs,
input-read counts and immutable product identities.

The run installs the changed producer through ordinary checkout preparation,
then edits existing SDK library Source and builds again. Unchanged unit archives
must remain byte-identical. Independent consumers remove SDK Source, load the
sealed units and expand a packaged macro with zero SDK compilation. An ordinary
application then builds against the exact changed SDK. Finally, fresh-VM and
warm unchanged self-builds must produce identical bytes without new SDK jobs;
the harness stops its private warm realm.

Focused controls additionally compare the new image and both metadata files
byte-for-byte against the existing serial assembler. They exercise bounded
refill while an earlier task is blocked, task cleanup on failure, preserved Env,
changed/deleted/re-resolved inputs, corrupt artifact refusal, parsed-frame reuse
and invalidation, and serial application initializers with unchanged build reuse.

## Remaining boundaries

This is a vertical prototype, not a claim that all builds or all CI lanes have
been qualified. SDK restoration and image stages cap concurrency at four;
application preparation respects its configured jobs, capped at 128, with at
most twice that many active-or-ready items awaiting ordered publication. There is no
new persistent scheduler or per-file cold VM.

Nix evaluation and durable coordination still run on the work server. Realization
runs on the configured build server. Compiler P/B/C qualification and actual
runtime-target compatibility checks remain required; this prototype does not
weaken them. SDK and portable images still require distinct sealing because their
native ELF bytes differ. Worker phase time, end-to-end request time and unchanged
warm linking must be reported separately.
