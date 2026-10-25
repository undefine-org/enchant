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
