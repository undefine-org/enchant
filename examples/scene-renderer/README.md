# Scene Studies

A BL-authored, deterministic 12-second motion study with an SVG display backend,
canonical librsvg PNGs, browser transport controls, and silent FFmpeg export.
There is no Bend/compiler dependency and no paid service.

From the repository root, with the checkout's OTP/Elixir dependencies prepared:

```sh
scripts/bl-mem
systemd-run --user --collect --wait --pipe --working-directory="$PWD" \
  --setenv=PATH="$PATH" --property=MemoryMax=4G --property=MemorySwapMax=512M \
  ./bin/bl --cold -p examples/scene-renderer run examples/scene-renderer/build.bl -- /tmp/bl-scene
python3 -m http.server 4048 --bind 127.0.0.1 --directory /tmp/bl-scene
# Open http://127.0.0.1:4048; Ctrl-C stops the static server.
python3 examples/scene-renderer/raster.py export /tmp/bl-scene --out /tmp/scene-study.mp4
```

Dependencies: Python 3 (standard library only), Fontconfig `fc-match`, DejaVu Sans,
`rsvg-convert` (librsvg), FFmpeg with libx264, and ffprobe. Set `SCENE_RSVG` to an
absolute rasterizer path if needed. All child commands inherit PATH. The host used
for the initial check has these tools in Nix store paths; they are not vendored.
The checkout must already have its required native runtime and native transport
built. Having Cargo on PATH may trigger the runtime's automatic native refresh;
that is unrelated to scene rendering. Never copy another checkout's runtime code.

For automatic edit refresh, use the BL server/watcher instead of Python's server:

```sh
scripts/bl-mem
systemd-run --user --collect --wait --pipe --working-directory="$PWD" \
  --setenv=PATH="$PATH" --property=MemoryMax=4G --property=MemorySwapMax=512M \
  examples/scene-renderer/preview.sh /tmp/bl-scene
```

This binds loopback port 4048. The wrapper owns a private native-transport runtime,
reuses a serial warm compiler worker, and stops that worker on exit. On Linux, a private-runtime process sweep also
drains compiler scopes that the checkout launcher moved out of the parent cgroup. Stop the
systemd unit as well when checking through a detached command: the wrapper also cleans up its separately scoped compiler. No service is required merely to create a frame or export.
Edit `scene_demo/film.bl`; the watcher coalesces changes while a build runs. An
invalid build writes `status.json` and leaves the published manifest untouched.
The browser polls once per second, keeps one image decode in flight and one latest
pending request, and retains the last valid image on error. Frame-number input,
scrubber, previous/next frame, scene buttons, and play/pause all use the same clock.

BL constructs scene values, validates geometry and identities, evaluates the
rational frame clock, writes SVGs, owns revision publication, and orchestrates the
raster worker. `live.hiccup` escapes XML. librsvg handles shapes, clipping,
transforms, alpha, font shaping and rasterization. Python serially invokes that
backend and FFmpeg; it never authors scenes. JavaScript only transports already
evaluated frames. `scenario.film` was audited and is left unchanged: its witnessed
media/narration model is different. PNG sequences/MP4s can be supplied as media
without misrepresenting scene frames as scenario witnesses.

Each completed revision is published by directory rename followed by atomic
manifest rename. Completed directories are reused without rewriting their frames.
The digest includes the demo, scene core, hiccup serializer, builder, worker,
preview shell, captured font bytes, and rasterizer version. Sources and font hash
are retained in provenance; a source-change guard rejects a build changed during
rendering. Export reads the manifest once and uses that immutable directory, so
later scene edits cannot alter an export. Only one build/export should write a
given output directory at once. Partial `.pending-*` directories after a failure
are unpublished and may be deleted. Old completed revisions are retained; remove
the output directory to reclaim them.

Logical dimensions are 800×450; 30/1 fps; frames 0–359 sample k/30 seconds. Scenes
occupy [0,4), [4,8), [8,12), with a short fade through paper at scene boundaries.
Coordinates and object order are explicit; scene evaluation needs no replay and
uses no ambient random source. `seed=0` is recorded; there is no random effect yet.
Inspect `<revision>/scene.json` for object values at one second, or individual SVGs.
The PNG directory is canonical for preview and export. Native SVG browser rendering
is useful for inspection but is not promised to match librsvg text exactly.

Text policy: one captured DejaVu Sans regular font, explicit positions, alphabetic
baseline, no implicit wrapping or fallback fonts. The rasterizer uses an isolated
Fontconfig directory containing that captured font. The demo uses Latin text,
arrows and a bullet; broader scripts, font selection, measurement and automated
wrapping remain future work. Colours are sRGB; SVG uses straight-alpha compositing,
and the demo's paper background makes exported PNGs opaque. H.264 export is lossy
yuv420p and silent; PNG hashes, rather than MP4 bytes across machines, identify
canonical rendered frames. The manifest records exact encode arguments and output
hash and verifies decoded frame count, dimensions and duration through ffprobe.

Current limitations: eager full-film rasterization makes edit refresh slower than
on-demand frame rendering; no image asset primitive, audio, SVG path validation,
automatic layout, or generalized film authoring CLI. Do not infer performance
superiority from this integration. This is a small useful vertical slice.

Focused verification:

```sh
./bin/bl --cold -p examples/scene-renderer test test/bl/scene/core_test.bl
node test/scripts/scene_preview.mjs
```

Run BL checks under the same cgroup cap. `check.sh` combines the focused BL tests,
frame generation and export; it runs serially and starts no persistent services.

A self-contained preview can be opened directly in a browser, without a server:

```sh
python3 examples/scene-renderer/portable.py /tmp/bl-scene /tmp/scene-preview.html
```

It captures one publication and embeds its PNGs; it supports playback and seeking,
but edit refresh belongs to the live server. The first demo bundle is about 13 MB.
The retained evidence under `research/scene-renderer-and-bend/scene-renderer/evidence`
contains a frame, browser screenshot, 12-second MP4, export manifest, and initial
measurements. `test/scripts/scene_live.py` exercises invalid/valid edits against
an owned running watcher; `scene_browser.mjs` exercises Chromium via CDP on 9224.
Both expect port 4048. `scene_export.py ROOT OUT.mp4` verifies revision isolation
while encoding. Close all test services after using these scripts.

## Art-directed edition

`scene_demo/editorial.bl` is the newer visual study. It uses the composable
`scene.atelier` grammar and explicit `scene.material` values: paper, halftone,
hatching, graph paper, cutouts, ink strokes, annotations, reveal and stagger.
Fonts are packaged under `assets/fonts` with their OFL licenses. No network or
system font fallback is required for this edition.

```sh
# Run under the same cgroup cap and after scripts/bl-mem:
./bin/bl --cold -p examples/scene-renderer run examples/scene-renderer/editorial.bl -- /tmp/bl-field-notes still
# Or render 96 frames / 4 seconds at 24 fps and encode a high-quality MP4:
./bin/bl --cold -p examples/scene-renderer run examples/scene-renderer/editorial.bl -- /tmp/bl-field-notes film
```

The result has the same preview/manifest structure as the first demo. The film
is `OUT/field-notes.mp4`. Rasterization uses 2× sampling and Lanczos reduction;
static seeded paper texture is resolved once per revision, with no texture flicker.
The second build's frame/asset provenance is independent from the earlier demo.
For the design reasoning and evidence boundaries, see `ART-DIRECTION.md` in the
renderer research folder. Use the lossless PNG to judge fine texture; MP4 is lossy.

## Living postcard studio

The A1 playground now has options-map cards, canonical Pango wrapping and vector
text outlines, measured layout, keyed local identities, attached connectors,
cue-relative entrances, theme variants, selected-frame rendering, and an inspector.
The larger proposed motion algebra and arbitrary source-property tracing remain
future work. See `priv/lib/scene/README.md` for the actual implemented surface.

```sh
scripts/bl-mem
systemd-run --user --collect --wait --pipe --working-directory="$PWD" \
  --setenv=PATH="$PATH" --property=MemoryMax=4G --property=MemorySwapMax=512M \
  examples/scene-renderer/studio.sh /tmp/bl-postcard-studio
# Open http://127.0.0.1:4048
```

The studio uses Python's standard library with shared Pango/Cairo libraries,
preferably discovered from the selected `rsvg-convert` closure via `ldd`. It shapes
only when content changes, samples an immutable evaluated tree on seek, and keeps
one render admitted globally. Its 540px preview uses the same 1080-unit layout.
Playback coalesces pending times; it does not promise 24 rasterized frames per
second. The displayed timestamp reports the frame actually shown. Content errors
keep the last valid picture and revision. The inspector exposes semantic IDs,
logical/ink/effect bounds, anchors, and the recorded font/color origin.

Text, cards, style, seed, cue, and stagger edits are supported in the page. BL
source changes require restarting this studio session: it freezes code/resources
at startup and does not yet implement coherent hot replacement of authored code.
The wrapper takes an exclusive output-directory lock and drains processes carrying
its private runtime environment on exit. Use one studio per output directory.
The loopback endpoint has no authentication and is intended for a local developer
session, not public hosting.

Each code snapshot retains worker/source bytes and font bytes. Each content revision
retains its normalized config, provenance, and only the requested preview frames.
The manifest publishes after a successful render. The source snapshot still has
the load-before-capture qualification documented in the research; it is not a new
proof of arbitrary executable capture. Cold startup loads the BL code once, and
all accepted requests in that session use its retained task environment.

A selected still can also be authored without a service:

```sh
./bin/bl --cold -p examples/scene-renderer run examples/scene-renderer/postcard.bl -- /tmp/bl-postcard
# Add 'long' or 'blueprint' after the output directory for those specimens.
```

Run these BL commands under the same resource cap. Focused checks are
`test/bl/scene/layout_test.bl`, `test/bl/scene/postcard_test.bl`,
`test/scripts/scene_text.py`, and (against an owned studio)
`test/scripts/scene_studio.py` / `scene_studio_browser.mjs`.

A six-second quality export from the new authoring API is available with:

```sh
./bin/bl --cold -p examples/scene-renderer run examples/scene-renderer/postcard.bl -- /tmp/bl-postcard-export film
```

Use the same cgroup cap. This produces 144 frames at 24/1 fps, a 1080px PNG
sequence rendered at 2× internally, `living-postcard.mp4`, and a manifest. It
captures fonts, worker/source bytes, and normalized content before rendering.
The still modes and film mode use the same measured component tree and sampling
function. The studio's Export button now captures the exact accepted preview
revision, renders its 144 quality frames in a separately admitted worker, and
offers the MP4 when encoding completes. Preview edits may continue during that
export; they do not alter its prepared composition. One export runs at a time.
An unpreviewed/invalid edit cannot silently export a previous composition.
Status progresses through queued, rendering, encoding, and ready/failed; rendering
does not yet report per-frame progress. Stop the studio unit to drain both workers.
The whole service must stay under its resource cap. Source hot replacement remains
open. Real export checks are in `test/scripts/scene_studio_export.py`.

On the validation host, the toolchain was not initially on PATH. The exact
host-specific environment used for checks was:

```sh
export PATH="/nix/store/wdzz6qm2jd36jjx94q7377zf23ggk036-elixir-1.20.4/bin:/nix/store/n849kp6a9lac3shjw3ycdl1b4sl1kw0l-erlang-29.0.1/bin:$PATH"
export SCENE_RSVG=/nix/store/ii7wr6b6b8c5fq1ci26rw7amkb4apwm8-librsvg-2.62.3/bin/rsvg-convert
```

Other machines should prepare the declared dependencies normally. These paths
record the measured host; they are not portable package-install instructions.

## Botanical motion: the visual-language track

`scene_demo/growth.bl` is a separate twelve-second composition, not a postcard
studio preset. It uses canonical outlined typography, procedural leaves and
petals, hatched surfaces, a halftone sun, paper grain, geometric iris clipping,
camera scaling, and cue/clip clocks. It requires the same dependencies as A1.

```sh
# Inspect scripts/bl-mem and use the cgroup cap shown above for each BL command.
./bin/bl --cold -p examples/scene-renderer run examples/scene-renderer/growth.bl -- /tmp/bl-growth-review
# Five quality specimens: 0.75, 2.8, 5, 8.2, and 11 seconds.
./bin/bl --cold -p examples/scene-renderer run examples/scene-renderer/growth.bl -- /tmp/bl-growth-film film
# 288 frames / 24 fps / 12 seconds; OUT/a-seed-of-possibility.mp4.
```

The default review mode retains explicit sample times in its manifest; its five
PNGs are specimens, not an evenly sampled five-frame film. Both modes render at
2160px and reconstruct to 1080px. Text is shaped once into reusable vector paths.
Font files and their OFL licenses are captured with the worker/source snapshots.
Use one publisher per output directory. Source-change guards retain the existing
load-before-capture qualification; this builder does not close executable capture.

`scene.clip` owns temporal scheduling, not spatial layout or property blending.
The illustration still authors its camera and geometry directly. Drawing uses
conservative dash-length budgets, not a general curve-trimming implementation.
The reveal uses geometric clips; arbitrary alpha masks and blend/effect isolation
remain future work. The film is silent. These are deliberate evidence boundaries.
See `research/scene-renderer-and-bend/scene-renderer/TRACKS.md` for the two tracks.

## The program is the sketchbook: camera-led presentation

`scene_demo/atlas.bl` authors a persistent six-plate illustrated world and a
56-second camera journey. All content exists throughout. Pans, curved travel,
proportional zoom, restrained roll, and reading holds supply the motion; this
film has no entrance/exit, fade, stroke-reveal, or animated-mask effects.

```sh
# Inspect scripts/bl-mem; use the documented cgroup cap and configured toolchain.
./bin/bl --cold -p examples/scene-renderer run examples/scene-renderer/atlas.bl -- /tmp/bl-atlas-review
./bin/bl --cold -p examples/scene-renderer run examples/scene-renderer/atlas.bl -- /tmp/bl-atlas-film film
```

Review mode creates six lossless reading frames. Film mode produces 1344 frames
at 24/1 fps, 1920×1080, silent H.264, as `OUT/presentation.mp4`. Each revision
retains `world.svg`, the 2x world atlas, `camera.json`, source/font/license bytes,
shaping provenance, selected PNGs, and `camera-report.json`. The report records
filter/density, native library identity, frame/media checks, hashes, and timing.
The worker streams packed BGRA directly to one encoder; it does not create a
Python or BEAM collection for each pixel, or store all uncompressed film frames.

This is an explicit camera-only raster-cache backend. Native Cairo resamples the
static atlas with BEST filtering; output is not promised pixel-identical to
rerasterizing vectors at arbitrary zoom. The authored track's maximum zoom is
1.08 over a 2px/world-unit atlas. Preview/export use the same camera sampler.
Use one publisher per output directory. Source-change publication guards retain
the existing startup executable-capture qualification. No general GPU/compiler
work is involved. `scene_camera.py` checks packed sampling/encoding and validation;
`camera_test.bl` and `atlas_test.bl` cover clocks, geometry, text fit, and persistence.

For the retained review page, use the range-aware developer server so browser
chapter seeking works (plain `python -m http.server` does not serve byte ranges):

```sh
python3 examples/scene-renderer/review_server.py \
  research/scene-renderer-and-bend/scene-renderer/evidence/atlas --port 4050
# Open http://127.0.0.1:4050; Ctrl-C closes the owned server.
```

The optional `--bind` selects an explicit interface for an authorized review.
This is a developer file viewer, with single-range GET/HEAD support; it is not
a public hosting/authentication product. `scene_review_server.py` tests full,
bounded, suffix, open-ended, HEAD, and invalid-range behavior.

## Continuous metamorphosis: beyond the atlas plates

The user superseded the slide/plate composition. `scene_demo/metamorphosis.bl`
authors one evolving system: 48 persistent keyed nodes, corresponding contours,
changing attachment geometry, and cameras following actual instances. Radial,
branching, ribbon, and orbital formations transform continuously. There are no
slide panels, replacement heading/body layouts, or opacity entrance/exit effects.
The camera moves through scales 0.48–4.5; foreground paths remain native vectors.

```sh
# Inspect scripts/bl-mem and use the same capped/configured checkout commands.
./bin/bl --cold -p examples/scene-renderer run examples/scene-renderer/metamorphosis.bl -- /tmp/bl-metamorphosis-review
./bin/bl --cold -p examples/scene-renderer run examples/scene-renderer/metamorphosis.bl -- /tmp/bl-metamorphosis-film film
python3 examples/scene-renderer/review_server.py \
  research/scene-renderer-and-bend/scene-renderer/evidence/metamorphosis --port 4051
```

The film is `OUT/experience.mp4`: 48 seconds, 1152 frames at 24/1 fps, 1080p,
silent. The native worker caches Cairo vector paths, admits explicit contour
deformations, and executes BL-authored matrices and curves. Hatching and label
halos are declared styles; paper is a frozen world-local repeating material.
It rejects instance arrivals/departures and unrecognized visibility properties.
It streams packed BGRA to one encoder. PNG/video use the same drawing path.

Source/font/license bytes, shaping provenance, camera track, full motion plan,
selected lossless frames, hashes, and media checks accompany each revision.
The retained evidence includes `motion.json.gz`, a lossless compressed copy of
the full evaluated plan. Reproduce from source to recreate its paper/native-path
resources; the compressed plan alone is not a standalone executable project.
The existing startup executable-capture qualification remains. Use one publisher
per output directory and keep the whole process tree capped. New checks are
`choreo_test.bl`, `metamorphosis_test.bl`, `scene_motion.py`, and the owned-browser
`scene_metamorphosis_browser.mjs`.

## MAKE WORLDS — material-led commercial study

A 30-second / 1920×1080 / 60 fps film, with original synthesized stereo audio.
BL authors the finite numeric score, camera matrices, surface/material controls,
shaped typography and sound events. Captured GLSL deforms and lights a persistent
five-band mesh. A native EGL/GLES worker provides depth, 4x MSAA, RGBA16F lighting,
UV-locked brushed/iridescent/woven materials, orbital points and a bloom/tone pass.
Typography is a warped camera-facing compositing layer behind the sculpture;
two small signature lines sit in front. It is not physical 3D glyph geometry.
No panels, fades or stock entrance/exit presets are used.

Set the checkout Elixir/Erlang toolchain PATH as above, and explicit graphics
libraries. On the current host:

```sh
export SCENE_RSVG=/nix/store/ii7wr6b6b8c5fq1ci26rw7amkb4apwm8-librsvg-2.62.3/bin/rsvg-convert
export SCENE_EGL=/nix/store/dpi7sgi4dmnddwjwdi57d8x06sx49vkn-libglvnd-1.7.0/lib/libEGL.so.1
export SCENE_GLES=/nix/store/dpi7sgi4dmnddwjwdi57d8x06sx49vkn-libglvnd-1.7.0/lib/libGLESv2.so.2
export __EGL_VENDOR_LIBRARY_FILENAMES=/nix/store/bfkyl4qgipm1vpfls2cqr3kv0afgpbya-mesa-26.1.1/share/glvnd/egl_vendor.d/50_mesa.json
examples/scene-renderer/showcase.sh /tmp/bl-showcase review
examples/scene-renderer/showcase.sh /tmp/bl-showcase film
```

The wrapper inspects `scripts/bl-mem`, captures through one capped cold checkout
VM, and renders the captured worker/shaders under a separate 3 GiB / 256 MiB swap
/ 15-minute ceiling. Selected review frames use the canonical drawing path.
`OUT/manifest.json` identifies a **captured plan**, not a completed movie.
`REVISION/report.json` exists after successful rendering; film mode checks exact
video/audio clocks before publishing `REVISION/showcase.mp4`. Failed renders do
not replace an earlier movie. External driver/library identities remain backend
dependencies; identical GPU bytes across different hardware are not promised.
A GLES3 implementation with four-sample RGBA16F renderbuffers is required; the
worker fails explicitly if that capability is unavailable.

`scene.score` supplies continuous numeric tracks. Authoring is in
`scene_demo/showcase.bl`; `showcase.bl` captures source/font/plan identities.
The shader backend is an experimental private film executor, not a completed
public shader graph, simulation system, physical renderer, or studio integration.
