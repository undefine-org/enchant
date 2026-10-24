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
