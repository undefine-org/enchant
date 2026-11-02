# Experimental scene renderer

Compose deterministic scenes in BL, inspect named objects and sample any frame.
The scene API and example tools are experimental. Use this preview for local
studies; data formats and rendering behavior may change between releases.

The generic studies cover editorial SVG, measured postcards, clip scheduling,
a camera-led atlas and persistent keyed transformations. The local postcard
studio offers selected-frame preview and a separate export worker. Font files
and OFL licenses live in `assets/fonts`. Commercial films and client assets are
kept outside this example.

The optional `hello` and `showcase` examples add a measured 60-second narrative
and a 30-second procedural material study. Both use the existing scene library,
packaged DM Sans/Instrument Serif fonts and shared text-shaping worker. The
Hello World editor interface is an authored concept, not an interactive editor.

From the repository root, enter the pinned graphics tool shell:

```sh
nix-shell nix/scene-tools.nix
scripts/bl-mem
systemd-run --user --collect --wait --pipe --working-directory="$PWD" \
  --property=MemoryMax=4G --property=MemorySwapMax=0 \
  ./bin/bl test test/bl/scene/core_test.bl test/bl/scene/camera_test.bl
```

This uses the checkout's normal SDK selection and compiler path. Graphics tools
are optional dependencies: Python 3, librsvg/Pango/Cairo, Fontconfig and FFmpeg.
The shell pins them with the repository's package lock. Text shaping uses the
four packaged font files and reports font hashes and native library versions.

Build a postcard with the same process cap:

```sh
systemd-run --user --collect --wait --pipe --working-directory="$PWD" \
  --property=MemoryMax=4G --property=MemorySwapMax=0 \
  ./bin/bl run examples/scene-renderer/postcard.bl -- /tmp/bl-postcard
```

For the local editor, run `examples/scene-renderer/studio.sh /tmp/bl-postcard-studio`
under that cap and open `http://127.0.0.1:4048`. Stop the owning command when
finished. The wrapper uses a private runtime directory and cleans up its workers.
One publisher owns each output directory. A completed revision is published by
rename; the manifest selects its frame directory. Failed work retains its
previous publication. Export selects an accepted revision independently of
preview requests.

BL owns geometry, composition and time. The Python workers execute shaped paths,
rasterization and encoding. JavaScript transports evaluated frames and editor
requests. The graphics tests cover measured text, selected samples, identities
and temporal boundaries. Browser interaction and full-film quality require
separate checks; they are not implied by a passing language test batch.

Read `priv/lib/scene/README.md` for the public API and its limits. PNG output
identifies the chosen backend/font inputs. H.264 video is silent, lossy and
subject to encoder differences across tool versions. Path topology, readable
text size and finite atlas sampling density remain explicit author choices.

## Narrative and material studies

Inside `nix-shell examples/scene-renderer/gpu-tools.nix`, run either capped wrapper:

```sh
examples/scene-renderer/hello.sh /tmp/bl-hello review
examples/scene-renderer/showcase.sh /tmp/bl-showcase review
```

The shell supplies `SCENE_RSVG`, `SCENE_EGL`, `SCENE_GLES` and the Mesa EGL
vendor configuration. Review mode captures and renders only selected PNGs,
with at most 64 captured frames. Replace `review` with `film` for a complete
H.264/AAC export with synthesized audio; this takes longer. Rendering runs in
one bounded worker after the capped capture VM exits. A sparse review plan is
refused as input to film export.

For a custom review selection, invoke the BL capture entry with
`OUT review 0,990,1980,3599` (Hello World) or
`OUT review 0,600,1200,1799` (showcase). The worker defaults to the captured
selection. Full film capture always evaluates every frame in its exact clock.

Each manifest selects a source/font capture directory containing `plan.json`,
`provenance.json`, captured shaders and the worker report. The report binds the
actual plan and rendered frame hashes to the GPU backend. The examples use
fixed 60 fps clocks and history-independent samples; driver and encoder outputs
may differ between machines. Film exports check the decoded media clock.

Focused checks, under the same cap, are
`./bin/bl test test/bl/scene/hello_test.bl test/bl/scene/showcase_test.bl`,
`python3 test/scripts/scene_hello.py` and
`python3 test/scripts/scene_showcase.py`.
