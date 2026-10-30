# Scene renderer and live preview: implementation proposal

## Product goal and scope

Give a human or agent a short path from structured scene code to a frame they
can inspect, revise, and export. The first result should be a working creative
tool, with a small independently authored explainer demonstrating its workflow.
It does not require a general native compiler, GPU backend, or new proof kernel.

Initial scope: deterministic 2D motion graphics, static and animated text,
shapes, diagrams, scene transitions, timestamp seeking, and offline export.
Defer arbitrary 3D scenes, a nonlinear editing suite, multiplayer editing, and
physically based rendering. These can become separate consumers later.

Keep application logic, scene construction, revision management, orchestration,
and reports in BL. Reuse an existing graphics mechanism when it accelerates
delivery; document its role. A browser preview can be useful without turning the
project into an independent JavaScript scene-authoring language.

## Time and scene semantics

Use frame indices and a rational frame rate as the export clock. For frame k
at fps n/d, sample time is k*d/n seconds. Scenes occupy half-open intervals
[start,end); define the final frame and transition overlap explicitly. A preview
wall clock chooses which timestamp to request, not the meaning of a scene.

The core conceptual operation is:

```text
scene(revision, time, assets, seed) -> display list + inspectable scene metadata
```

This is proposed notation, not an existing BL API. Rendering time t must not
require replaying all preceding frames. Stateful simulations may use a separate
explicit, versioned checkpoint model; do not accidentally hide mutable simulation
state inside ordinary scene functions.

At a fixed revision and asset set, arbitrary seek order should give equivalent
scene values. Derive random choices from stable object identity and an explicit
seed. A call to global random on every preview would make both debugging and
frame comparison unreliable.

## Scene representation

Start with an inspectable value model. Each object has a stable id, primitive,
geometry, style, transform, ordering, and optional clip. A display list has
explicit ordering; maps alone must not determine compositing order.

Initial primitives: group, rectangle, rounded rectangle, circle/ellipse, line,
polyline/path, text, and image. Add opacity, stroke, fill, clipping, and affine
transforms. A diagram is composition of these primitives, not a new renderer.

Text needs a real policy: packaged font identity, fallback behaviour, shaping,
measurement, wrapping, baseline, and alignment. Make layout errors inspectable.
Do not let browser-only font fallback produce exports that silently differ.
Declare which script coverage the first implementation supports.

Separate logical coordinates from raster scale. For example, a 1080-square scene
may preview at 540 square without changing line breaks or object positions.
Texture detail can have a quality setting, but that setting belongs in the
artifact identity. Define colour space and alpha convention before adding
multiple raster backends. A premultiplied-alpha buffer must not be interpreted
as straight-alpha by an encoder or compositor.

Authoring helpers should cover easing, interpolation, stagger, hold, reveal,
slide, crossfade, drawing a path over time, and typing/revealing text. Helpers
must specify behaviour before and after their interval, including zero duration.
Avoid evolving the public API around one demo's hard-coded scene names.

## Backend selection and first implementation

First audit existing BL-to-JS, browser, desktop, and graphics integration. Choose
one canonical path with the fewest moving parts; do not implement three engines
before seeing the first film. SVG is a reasonable first candidate for this
visual workload because it preserves an inspectable scene and text/vector
composition. Canvas/native rasterization may win if available infrastructure
makes it simpler. This choice remains an implementation experiment.

Whatever path is selected, implement a backend-neutral scene value and explicit
renderer capabilities. Unsupported primitives should produce useful diagnostics.
Do not silently omit objects. A canonical export backend is acceptable initially;
if preview uses another, define and test the expected visual differences.

Pixel buffers should remain packed at the graphics boundary. Avoid per-pixel
BEAM terms and per-pixel process messages. Parallelize coarse independent frames
or tiles with bounded queues after measuring where time actually goes.

## Preview loop

Provide play/pause, seek/scrub, frame stepping, a timestamp/frame field, scene
navigation, and a clear current revision. The workflow should allow requesting
one frame, several diagnostic timestamps, or a contact sheet without exporting
the entire film.

Maintain explicit revision identity. A render request includes revision,
timestamp, asset hashes, seed, backend, and quality. A completed old request may
be cached but must not replace a newer requested frame in the preview.

Changing scene code should publish a coherent new revision. On an invalid edit,
keep the last valid frame visible and show the current diagnostic. Never blend
objects from two revisions into one apparently valid frame. For an export,
capture the executable dependencies and assets once so edits during the run
cannot alter later frames. Reuse the existing execution/environment ownership
mechanisms where applicable, rather than inventing a second lease system.

Scrubbing can generate requests faster than they complete. Coalesce pending
preview requests and prioritize the latest timestamp; use bounded admission.
A stopped wait does not imply physical cancellation of native work. Follow the
qualification already documented in proc.task. Dropping a stale result is often
sufficient for preview; draining outstanding work is necessary during teardown.

Inspectability matters: expose object ids, bounds, evaluated properties,
scene-local time, clipping, and revision. An agent should be able to ask why a
label is off-screen without reverse-engineering pixels alone.

## Export and existing film infrastructure

A frame sequence or raw stream is a valid first export boundary. Treat encoding
as a separate stage with explicit dimensions, frame rate, pixel format, duration,
and audio policy. FFmpeg is an acceptable encoder; its use does not establish
that rendering itself is native BL.

scenario.film already orchestrates witnessed media, narration, subtitles, and an
optional Python/FFmpeg worker. Reuse its capabilities where they match. The new
renderer supplies authored scene frames, which differ from its existing source
media model. Add a narrow adapter rather than forcing one timeline abstraction
to impersonate the other. Preserve export provenance and measured durations.

Audio is optional for the first renderer. Never require a paid provider or
credentials merely to preview shapes and text. Later audio alignment can use
local files or explicit provider calls through existing facilities.

The export manifest should include scene revision, source/dependency identities,
font and image hashes, seed, renderer/backend versions, dimensions, rational
frame rate, frame count, encode arguments, and result hashes. A pixel hash can
be stable for one pinned backend/environment without promising byte-identical
MP4 output across codecs or machines.

## Delivery sequence and acceptance

### R0: Integration spike

Inspect repository instructions and available graphics routes in the new worktree.
Render one BL-authored frame containing text, shapes, transforms, and clipping.
Record the actual graphics dependency, supported platforms, and export mechanism.
Acceptance: a reproducible command creates a viewable frame; limitations are clear.

### R1: Deterministic scene core

Implement the small scene value, time helpers, validation, and fixed assets.
Build a 10–20 second film with at least three scenes: an animated diagram,
text/layout, and a transition. Acceptance: selected frames render in arbitrary
order with consistent scene values; bad times and geometry yield diagnostics.

### R2: Live preview

Add seeking, stepping, playback, current revision, and edit refresh. Acceptance:
a changed scene produces a new revision, invalid edits preserve the last valid
preview, and delayed old results never overwrite a newer frame. Exercise rapid
scrubbing and closing a preview while work remains outstanding.

### R3: Offline export

Export the exact frame range at the requested rate and resolution, with bounded
memory and a manifest. Acceptance: frame count/duration are verified with media
tools, key frames match the canonical preview path, and export remains coherent
while source code changes. Stop all owned workers during cleanup.

### R4: Workflow evidence

Measure first preview, warm edit-to-frame latency, selected-frame render,
full export, memory, and backlog behaviour. Preserve distributions and machine
information. Optimize the measured bottleneck. A slow font loader or encoder
must not be misdiagnosed as evidence for a new GPU compiler.

## Meaningful tests

Test timeline boundaries, interpolation endpoints, deterministic seek order,
asset/version identity, stale-result suppression, export consistency, and cleanup.
A few reference images cover clipping, text, transforms, and alpha. For raster
comparisons, specify whether exact equality or a documented tolerance is expected.
Avoid tests that merely mirror the display-list constructor implementation.

Use checkout ./bin/bl, inspect scripts/bl-mem before starting VMs, keep one warm
VM where possible, and cap expensive process trees. Run focused tests. This
project must not leave preview servers, browser workers, or encoders alive after
checks. No benchmark should run until resource ownership and cleanup are clear.

## Relationship to the Bend project

This renderer can later supply a real workload for native-region extraction,
packed-buffer kernels, and proof-preserving specialization. Those improvements
must preserve the authored scene's semantics. Until then, measure the whole tool
honestly and label any library acceleration. A useful first release is valuable
even when no language-performance claim has been established.
