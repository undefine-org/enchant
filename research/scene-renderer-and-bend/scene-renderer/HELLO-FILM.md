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

## Completed export and checks

[Watch Hello, world.](evidence/hello-film/index.html), or open the
[MP4](evidence/hello-film/hello-world.mp4). The user review endpoint is
`http://100.124.205.18:4054/` while its intentional four-hour service is alive.

The final capture revision is
`78f8135e99273346c5595e8e1bdacd458fab324d9627bd38138ea16266d9cce7`,
source commit `2c4883f0`. The film contains exactly 3,600 frames, 1920×1080 at
60/1 fps, 60 seconds. Stereo AAC is 48 kHz / 60 seconds. The movie is 20,841,909
bytes. Capture took 69.098 seconds / 1.5 GiB peak; render/encode/probe took
120.988 seconds cgroup wall time / 1.6 GiB peak. Both used zero swap. These are
measurements of this one offline workload, not interactive-preview benchmarks.

Nine BL assertions, nine canonical text tests and nine worker admission tests
pass. A fresh native context sampled frames 1980, 0, 2520, 3420 in that order;
all matched their full-export PNGs byte-for-byte. At film seconds 30 and 33,
the project is at the same eight-second marker. The complete 1360×765 artwork
crop is byte-identical in those two native frames, including glyphs, attachments,
seed texture and shader highlights. The pointer/timeline are separate film UI.
This is a native-frame equality check, not a claim of equal compressed H.264 bytes.

Chromium played the entire 60 seconds with sound enabled and reported zero
dropped frames out of 3,600. Nine forward/backward seek requests, Nunito loading,
replay state and a 390-pixel layout passed. HTTP video byte ranges returned 206
with the expected 16 bytes. The owned browser/profile, encoders and native test
workers were stopped. The intentional review server is time-bounded.

AAC decode level checks measured mean -21.0 dBFS and peak -2.9 dBFS. The retained
movie, lossless samples, decoded contact, screenshot, source/font provenance,
render report, independent sample report and full compressed evaluated plan are
under `evidence/hello-film/`. The raw JSON plan is 231,476,147 bytes; its lossless
archive is 18,263,848 bytes. Source, movie and decompressed plan hashes were
verified. Full-size samples and the decoded contact were inspected; automated
playback does not establish a human full audiovisual review or professional mix.

Visual review corrected clipping around the extended title, scale/spacing in the
family, inherited tree density, degenerate connector stubs, the marker clock,
selected-text baseline scaling and the concept label's position. All components
remain keyed; actual geometry and material changes carry the story. The end
keeps the same title, shared coral stock, attached seed and chosen spectral finish.
