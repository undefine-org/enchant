# Renderer implementation evidence — 2026-10-24

The bootstrap pause is superseded by the user's implementation authorization.
Work is confined to this renderer branch; no Bend comparison/compiler files or
unrelated runtime source changes were imported.

R0 is implemented: `scene.core` serializes validated, ordered BL scene objects via
existing `live.hiccup`; librsvg 2.62.3 is the selected graphics dependency. A
reproducible 800×450 frame includes text, shapes, rotation/translation and clipping.
The raster backend, rather than BL numerical code, does font shaping and pixels.
Browser SVG/live patch support, JS compilation, Wry desktop integration and
scenario.film were inspected. The SVG route had the smallest dependency surface.

R1 has a deterministic vertical slice: half-open time intervals, rational frame
clock, interpolation/easing, stable ids, geometry validation and a 12-second,
three-section original film with fade transitions. Eighteen focused assertions
passed, including arbitrary seek order, scene boundaries and invalid geometry.
Text/layout is deliberately explicit; generalized wrapping, images and broader
script policies remain outside this first slice. Fonts are captured per revision
rather than vendored; the canonical rasterizer sees only that captured font.

R2 has a BL HTTP server/watcher and browser transport UI: seek, step, play/pause,
frame number, scene navigation, revision and diagnostics. Builds are serial; pending
changes coalesce. Atomic publication retains the previous revision on an invalid
edit. Image admission has one in-flight decode and one latest pending request.
Async tests verify stale results cannot publish. A real Chromium 155 smoke test
against the BL server passed load/seek/step/navigation/playback/rapid-scrub/close.
An invalid edit retained the old manifest in 1.763 seconds; a subsequent valid
edit published a new revision in 11.306 seconds. The test restored the source.

R3 has canonical PNGs shared by preview and offline export, serial bounded
rasterization/encoding, source/font hashes, backend version and export provenance.
ffprobe verified 360 decoded frames, 800×450, 30 fps and 12 seconds. An integration
check changed the publication during export; the result kept its captured revision.
The MP4 is silent H.264/yuv420p. It is not byte-equivalent to PNGs; the retained
PNG hashes identify the canonical pixels. The standalone portable preview bundles
those PNGs and supports inspection without any running service.

R4 has initial evidence, not completed performance qualification. The first full
generation took 15.161 seconds with a reported cgroup peak of 239.1 MB. Ten selected
SVG rasterization samples and machine data are in evidence/checks.json. First-build
and warm-edit figures are single samples, not distributions. Full-film eager
rasterization is the obvious next optimization candidate; measure on-demand frame
rendering before considering a different graphics backend. No comparative speed
claim follows from these results.

Services were stopped after checks. Checkout warm VMs move into separate capped
scopes; cgroup teardown alone did not stop two owned compiler VMs. They were
identified by their unique private runtime environment and stopped explicitly.
The wrapper now has a bounded realm-stop attempt plus a private-runtime process
sweep; that sweep was checked against an owned sleeper. Unrelated VMs were left
alone. The working checkout was prepared with installed third-party dependency
symlinks and a locally compiled lazy_memo native runtime; these are ignored build
artifacts, not imported runtime source edits.

Remaining work includes stronger source/executable snapshot identity at the tiny
load-before-capture boundary, concurrent-publisher exclusion, broader SVG value
validation, font/layout coverage, on-demand preview latency, measured edit/export
distributions, and a richer demo. Do not treat this first useful slice as closure
of every acceptance item in DESIGN.md. Source changes during generation are
rejected; completed revision directories are reused without rewriting pixels.

See examples/scene-renderer/README.md for reproducible commands and test entrypoints.

## Art-direction continuation

The user rejected the initial demo's visual quality and specifically asked for
first-principles reconstruction and Lisp abstractions. The full-resolution source
video was sampled again, including an inspected 1080px close-up. The new original
`scene_demo/editorial.bl` uses reusable `scene.atelier` composition and explicit
`scene.material` values. It packages Instrument Serif, DM Sans and Patrick Hand
with licenses, and adds seeded paper grain, halftones, hatching, graph-paper lines,
ink edges, layered cutouts and staggered motion. See ART-DIRECTION.md for the
observed/inferred boundary and the compositing/sampling rationale.

The canonical quality path renders at 2× and reconstructs at 1080 square. The
backend caches seeded material filters in a 512px packed texture tile; type and
geometry remain vector. A direct uncached master took 6.052 seconds; one complete
cached raster invocation took 2.752 seconds including texture creation and output
reconstruction. These are single observations, not comparative distributions.
A repeated raster test verified identical pixels and reuse of the texture tile.
The new film export captures code, worker, packaged font bytes and quality policy.
The earlier 800×450 demo is retained as historical pipeline evidence.

The completed editorial export was independently checked through ffprobe by the
worker: 96 frames at 24 fps, 1080 square, four seconds. Full generation took
244.805 seconds under the capped process tree, with a reported 717.2M peak. This
is an offline quality proof; interactive render latency still needs work. Twenty-
nine focused assertions passed across the original core and new editorial tests.
The contact sheet was inspected for staged assembly, clipping and stable texture.
Lossless keyframe, motion study, checks and exact export provenance are retained
in `evidence/editorial/`. No preview service or compiler VM was left running.

## A1 measurable cards and selected-frame studio

The user authorized autonomous implementation and incremental commits. The earlier
renderer and research were committed first, followed by the canonical-text/layout
slice. New code adds `scene.text`, `scene.geometry`, `scene.picture`, `scene.layout`,
`scene.motion`, `scene.inspect`, and `scene.styles.editorial`. The library README
identifies the actual implemented surface; the larger API research remains a plan.

Pango now measures and wraps paragraphs, and Cairo extracts the same shaped glyphs
as vector outlines. Layout and rendering therefore share glyph geometry instead
of relying on matching browser/librsvg text guesses. Packaged font hashes and
actual shared-library versions/paths are recorded. Six native text tests passed,
including wrapping, explicit breaks, missing resources/glyphs, and outline bounds.
Fifty-five focused BL assertions passed across the original core/editorial and
new layout/postcard tests. They exercise growth/reflow, stable local identities,
transform order, finite timing, arbitrary seeking, inspection, and cue edits that
reuse shaping even when a worker invocation would fail.

The new studio (`examples/scene-renderer/studio.sh`) lets a user change text,
reorder/insert cards, switch warm/blueprint styles, change paper seed/cue/stagger,
seek/step/play, and inspect logical/ink/effect bounds and anchors. It renders only
requested frames at 540px over an unchanged 1080-unit layout. Immutable prepared
scenes are sampled at arbitrary time. Content errors preserve the last valid
revision and picture. A dedicated retained task owns the scene state; an admission
slot remains held until actual render completion. Eight simultaneous requests
produced one success and seven busy responses. A file lock excludes a second
publisher for the same output directory. Code, worker, and font bytes are captured
at session startup; complete leaf hashes and JSON, rather than a bounded printer,
key source/config identities.

Real HTTP checks passed text growth/reflow, stable identity under reorder, coherent
style changes, invalid-edit retention, and exact repeated PNG bytes after shuffled
seeks. Chromium passed bounds overlays, seek/step, style editing, playback, rapid
scrubbing, and closing. Selected evidence is in `evidence/a1/`. In one local run,
first frame was 2.295s, a text edit 0.964s, and selected seeks had a 0.236s median
with four uncached samples and one cached sample. These are small observed samples,
not a claim that the p95 product target is achieved. Timing evidence predates the
final cue-only shaping-cache optimization, which has separate correctness tests.

A1 remains partly open: BL source changes require restarting the studio, rather
than coherent hot replacement. Snapshot source identity still has the documented
load-before-capture qualification. Property inspection records font/color role
origins, not arbitrary source-form traces. Broad sequence/parallel/event-track and
simulation APIs are not implemented. A one-shot six-second export entrypoint is
being checked separately; don't infer completion from the interactive preview.
All owned studio/browser test services were stopped; unrelated VMs were preserved.
