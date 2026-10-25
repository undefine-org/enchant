# MAKE WORLDS — a material-led showcase

The user rejected the 48-second piece as slow and visually underpowered. This
brief supersedes its pacing and sparse diagram aesthetic. Make a complete,
original 30-second commercial, not a deck, tutorial, or catalogue of effects.
No claim of awards or parity with a production studio is implied by the target.

## Direction

One continuous sculptural ribbon changes its geometry, material and relationship
to typography. Begin inside the material, pull back hard, thread through a knot,
stretch into a wave, orbit a helix, and return to a signature loop. Alternate
large gestures with short readable moments. Camera motion and geometry overlap;
avoid repeatedly stopping at the ends of six-second eases. Make type part of
the composition, with graphic scale and deliberate occlusion. Black, ivory,
acid yellow, vermilion, and spectral metal replace the earlier botanical palette.

The material vocabulary is real evaluated shading: procedural brushed metal,
interference colour, woven microstructure, print grain and emissive edge accents.
Use native mesh rasterization with depth, lighting, an explicit post pass and
packed readback. This is an experimental backend, not compiler/GPU research.
BL owns the score, sampled camera/geometry/material controls, stable identities,
asset definition and build. GLSL owns the declared procedural surface equations
and pixel shading; EGL/GLES executes them. Record actual hardware and timings.

The film should run at 60 fps. An original deterministic synthesized soundtrack
can supply the editorial pulse: 128 BPM, 64 beats, exactly 30 seconds. No borrowed
recording. Audio needs its own bounded worker and explicit BL-authored event score.
Preview must play immediately and support seeking. Retain the movie, selected
lossless frames, evaluated plan, source/font hashes and actual checks.

## Evidence and limitations

Inspect full-size frames before committing to the full export. Test shader
compilation, invalid-plan admission, exact clocks and history-independent sample
rendering. Verify encoded video/audio duration, playback, seek and range delivery.
Stop owned EGL contexts, encoders and browser tests. Keep the intentional user
review server time-bounded. This does not deliver generic studio shader editing,
a general physically based renderer, arbitrary topology morphing, or hot reload.

Primary backend references:
- [Khronos EGL](https://www.khronos.org/egl): contexts, surfaces and ownership.
- [OpenGL ES registry](https://registry.khronos.org/OpenGL/index_es.php): GLES 3
  and GLSL ES specifications, framebuffer, texture, shader and pixel semantics.
- [Khronos framebuffer documentation](https://wikis.khronos.org/opengl/Framebuffer):
  explicit framebuffer readback and packed pixel transfer.

The first hardware probe created a surfaceless GLES 3.2 context and reported
Mesa Intel UHD Graphics 630 (CML GT2), Mesa 26.1.1. This is an observed local
backend capability, not a performance comparison with any other renderer.

## Implemented visual vocabulary

`scene.score` supplies finite numeric-vector tracks with time-aware cubic
Hermite tangents. Interior keys do not force the camera to stop. Camera matrices
are calculated in BL. Geometry weights are normalized; physical material channels
are bounded after score interpolation. The shader consumes those captured values
without reading a wall clock or replaying a simulation. Five persistent bands
share one continuously deforming loop/knot/wave/helix surface grammar. The private
GLSL vertex stage defines this actual parametric geometry; it is not BL-compiled
GPU code. UV materials follow the deformation. 320 deterministic orbital points
provide scale detail. Native depth and four-sample antialiasing preserve overlap.

The typography is shaped once with packaged Pango fonts and rasterized from the
same outlines, then warped on camera-facing quads. Giant words pass through the
composition behind the sculpture; the two small signature lines stay in front.
This layered occlusion is compositing, not 3D extruded text or physical shadows.
The final brand has a separate clear area. No chapter panels or fading objects.

The scene buffer is RGBA16F with depth24, resolved from 4x MSAA. The post pass
adds a tightly sampled glow and an ACES-like curve, then writes opaque RGBA8.
The material model uses analytic studio reflection cards, view-dependent colour,
UV-locked brushing/weave and edge accents. It is original stylized shading, not
a full microfacet/anisotropic BRDF, path tracing, or a universal material system.
No film grain/noise source is advanced through playback history.

The first visual iteration exposed mirrored/unreadable world-facing type and
a pastel foil palette. Camera-facing type and darker metal corrected those.
A wide sparse bloom kernel created ghost outlines; a tighter 32-tap disk and
lower fringe strength removed the obvious replicas in inspected frames.

Checks completed before full export: 12 BL assertions (including all 1,800 frame
controls), 9 Python admission tests, shader compilation and eleven full-size
selected frames on the Intel GPU. The canonical movie and playback verification
are recorded separately after export; a selected-frame review is not full motion
or audio quality assurance.

## Completed film and retained evidence

[Watch MAKE WORLDS](evidence/showcase/index.html), or use the
[MP4](evidence/showcase/showcase.mp4). The intentional Tailscale review endpoint
is `http://100.124.205.18:4052/` while its four-hour service is alive.

The canonical capture is revision
`4377809eda4be84cb53d2c29920a33e25560f000639967c4efdf0b4c76340135`,
source commit `44380e73`. The film is exactly 1,800 video frames at 60/1 fps,
1920×1080, 30 seconds. AAC stereo is 48 kHz / 30 seconds. Encoded size is
53,458,183 bytes. GPU/encoding/probe worker time was 80.232 seconds; cgroup wall
time 80.453 seconds, peak 860 MiB, zero swap. This is a measurement of this one
local workload, not an interactive frame-rate or comparative benchmark.

The original score has 64 beats at 128 BPM. BL authors kick, bass, hat, snare and
chord events; the packed Python worker synthesizes their waveforms, short stereo
reflections and soft limiting into 1,440,000 stereo sample frames. The AAC decode
measured mean -18.5 dBFS and peak -2.6 dBFS. Level/clock checks and browser audio
playback passed; no claim of a professional auditory mix review is made.

Chromium played the entire 30 seconds, with sound enabled, reporting 1 dropped
frame of 1,800 on this run. Forward/backward seeking through seven times, native
replay state and a 390-pixel mobile layout passed. Byte-range delivery returned
206 with the expected 16 bytes. The browser service/profile was stopped/removed.

A fresh native context sampled frames 1200, 0, 660, 120 in that order. Every PNG
matched the corresponding canonical full-film sample byte-for-byte. Full-size
frames, native and independently decoded contacts, and the browser screenshot
were inspected. This sampling plus automated playback does not substitute for a
human full audiovisual review or establish that every possible layout is good.

Retained artifacts include the movie, four lossless frames, poster, native and
decoded contact sheets, screenshot, full losslessly compressed evaluated plan,
source/font provenance, render report, independent seek report and checks. The
compressed plan hash and all source/movie hashes were verified. The raw plan's
absolute capture path in the manifest describes the original run; reproduce a
new capture with `showcase.sh`, not by assuming that temporary directory exists.
Shader source files live in the repository and are hashed by the report.

Open: generic shader/surface nodes and capability negotiation, public 3D bounds
and picking, richer temporal sampling, proper anisotropic BRDFs/shadows, glyph
mesh deformation, more varied surface grammars, professional sound design, and
studio adoption. These are not prerequisites silently claimed by this film.
