# Hello world product narrative film

The user approved production of the 60-second storyboard and requested a
friendlier font. Nunito replaces the high-contrast display serif in this film.
The packaged variable font and license are captured with the project. Its
[Google Fonts metadata](https://github.com/google/fonts/blob/main/ofl/nunito/METADATA.pb)
and local `Nunito-source.json` identify the upstream source and retrieved bytes.
The artwork and interface use canonical Pango measurement and Cairo outlines;
preview/export do not substitute browser text metrics.

## What the film actually executes

BL authors and samples one scene with a measured title, its cutout frame,
attached seed and two satellites, 24 keyed component instances, their grid/tree/
helix relationships, a world camera and a cinematic camera, actual text bounds,
and a finite project clock. The longer title changes the measured frame width.
One material setting changes the shared component stock. Native shader materials
remain tied to seed-local coordinates across camera travel and instance changes.
Two timeline returns sample exactly the same project state. End copy is the
approved brand, category and first-scene invitation. No voiceover is required.

`scene_demo/hello.bl` is the authored film. `hello.bl` captures all explicit
source leaves, fonts, shaped assets, sampled display lists and sound events.
`hello_worker.py` executes cached native Cairo paths and procedural GLES seed
materials, then streams packed RGBA to one owned FFmpeg encoder. The fragment
material uses analytic sphere normals, studio-style highlights, UV-locked grain/
weave, spectral color and antialiased orbital marks. It is stylized shading, not
physical path tracing, a general 3D renderer, or a new BL GPU compiler.

The soundtrack is original deterministic stereo synthesis: a warm musical bed,
reduced activity during inspection/scrubbing, action ticks, restrained travel
accents and a gentle final tail. BL authors event times and parameters. The
worker owns packed audio synthesis and encoding. It does not play a borrowed
recording or execute actions when seeking the scene.

## Interface and release boundary

The cinematic studio shell is a reconstruction and is labeled **Interface
concept** in the product shots. Its source pane, pointer, control interactions
and job panel are film graphics. This film does not claim to capture a shipped
generic source editor, spatial picking, unified material controls, instant
preview or general-project export. “A little later” marks an editorial time cut
in the conceptual export beat. Existing postcard studio and its real accepted
export remain separately implemented. The new film artwork is actually rendered;
the reconstructed interface is not evidence that its workflow is implemented.

The film therefore completes the requested narrative video while preserving the
storyboard's explicit release gates. A public release as a live product demo
would require replacing those interface shots with real captures after the
listed studio work. Until then, publish it as an authored product concept film.

## Reproducible build

Use the toolchain PATH and SCENE_RSVG / SCENE_EGL / SCENE_GLES / EGL vendor
configuration documented for MAKE WORLDS in the example README. Then:

```sh
examples/scene-renderer/hello.sh /tmp/bl-hello-film review
examples/scene-renderer/hello.sh /tmp/bl-hello-film film
```

The wrapper checks `scripts/bl-mem`, captures through one 4 GiB / 512 MiB swap
capped cold checkout VM, then runs the captured worker/shaders in a separate
4 GiB / 512 MiB / 20-minute cgroup. The manifest identifies a captured plan;
`report.json` identifies completed review/export. The movie is published only
after FFmpeg completes; frame count/rate, dimensions and audio/video duration
are independently checked with ffprobe. Driver/library identities remain native
backend dependencies. Explicit source capture retains the earlier qualified
load-before-capture boundary.

The complete evaluated plan can be large because it retains every item/matrix
for all 3,600 frames. The current private executor admits at most 256 MiB of JSON,
400 items/frame, 80 glyph assets, bounded native paths and 512 sound events.
Numbers, transforms, clips, paints, shader weights, IDs and rational frame clocks
are checked before graphics allocation. No per-pixel BEAM values are constructed.
