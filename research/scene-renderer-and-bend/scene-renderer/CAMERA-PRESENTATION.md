# The program is the sketchbook

The user requested extending the visual study into a longer presentation about
the medium, with natural pans and zooms and no entrance or exit animations.
The implementation is `examples/scene-renderer/scene_demo/atlas.bl`; the build
entrypoint is `examples/scene-renderer/atlas.bl`. The research audit was committed
first as `eac8718f`; the camera/atlas implementation is `7fb3d243`.

## Editorial structure

The presentation is 56 seconds, 1344 frames at 24/1 fps, 1920×1080, initially
silent. It follows a serpentine route through six plates in one persistent world.

| Start | Reading interval | Plate | Content and inspiration |
|---|---|---|---|
| 0 | 6s | A language for little worlds | Lisp functions construct meaningful pictures; Pict |
| 8.8 | 7s | Meaning before coordinates | Real text metrics, layout, anchors; Pict and Typst |
| 18.6 | 7s | One idea, a family of forms | Components, keyed instances, material character; Houdini and OpenUSD |
| 28.4 | 7s | Time is a place you can visit | Independent sampling and nested clocks; Motion Canvas and Tidal/Strudel |
| 38.2 | 7s | Ask the picture how it works | Bounds, anchors, font/color origins, last-valid preview; Vega and Salsa |
| 48 | 8s | A living medium, an open horizon | BL authorship, graphics libraries, shared preview/export meaning, next capabilities |

The five 2.8-second travel intervals are part of the story. The camera widens to
show spatial context, follows an explicit curved path, then settles into the next
reading interval. It does not cut between unrelated slides. Every plate and its
content exist before the first sample. There are no fades, object arrivals,
scale-from-zero effects, drawn-path reveals, animated masks, or departures.
Earlier historical films keep their existing animation direction.

The six code/derivation captions are editorial illustrations. Names such as
`picture`, `ideas`, and `film` denote example bindings; they are not additional
public library functions. The inspect plate uses actual Pango logical/ink extents
for its glyph example. Its purple padding illustrates conservative effect extent;
it does not demonstrate a new general effect engine. The graph is explanatory
artwork, not a measured performance chart.

## Implemented camera API

```clojure
(ns camera-example (:require [scene.camera :as camera]))
(def a {:center [900 600] :zoom 1.02 :roll -0.18})
(def b {:center [928 585] :zoom 1.08 :roll 0.12})
(def c {:center [2750 600] :zoom 1.02 :roll -0.18})
(def journey
  (camera/track
    [{:id "read" :duration 6 :from a :to b}
     {:id "travel" :duration 2.8 :from b :to c :pullback 0.23
      :controls [[1500 650] [2200 540]]}]))
(camera/sample journey 7)
(camera/matrix (camera/sample journey 7) [1920 1080])
```

These are actual signatures. `track` derives segment starts and duration, checks
unique IDs, finite parameters, positive durations/zoom, and matching endpoint
poses. `sample` is pure and holds endpoints outside the track. The presentation's
own `frame-plan` admits only its half-open film interval. `matrix` puts the camera
center at the viewport center and applies the inverse camera roll.

The interpolation policy is explicit:

- Timing uses `10p³ − 15p⁴ + 6p⁵`, giving zero velocity and acceleration at endpoints.
- Position uses a cubic Bézier path evaluated at that eased progress.
- Zoom interpolates logarithms, with a symmetric temporary logarithmic pullback.
- Roll interpolates explicit degrees without angle-wrap guessing.
- Reading shots use a small push and drift. Travel has a wider field and greater
  speed. No spring simulation or history-dependent physics is hidden in sampling.

For this track, sampled zoom ranges approximately 0.8336–1.08. The restrained
camera roll ranges from -0.18° to 0.12°. The world is 5600×2400 logical units,
rasterized at two pixels per world unit. This gives a declared finite sampling
budget rather than an unbounded vector-zoom promise.

## Graphics boundary and reproducibility

BL owns the world, canonical shaping requests, camera track, every sampled matrix,
rational frame clock, source/resource capture, and final publication. The world
uses packaged fonts, procedural geometry, stable paper grain, hatching, halftones,
and explicit typography. Pango/Cairo supply measured outlines; librsvg rasterizes
the captured vector world once. `camera_worker.py` uses native Cairo to resample
that static atlas and streams opaque packed BGRA to one FFmpeg encoder.

Python does not interpolate the camera, construct scene objects, or loop over
individual pixels. The native packed buffer is copied as a block. Review PNGs and
film input use the same sampler. Color/alpha, atlas density, filter, native library
identity, encode arguments, media checks, and hashes are retained. This backend
does not promise equality with rerasterizing SVG at arbitrary zoom. The existing
startup executable-capture qualification remains; a source-change guard is not
proof of complete executable freezing.

Reproduction commands, environment, and resource caps are in the example README.
Use one publisher per output directory. The worker validates its plan and pixel
budget before large allocations/encoding, owns one encoder, and drains it on
failure. Run under the repository cgroup limits and inspect `scripts/bl-mem` first.

## Verification and review

The new focused checks cover camera boundary poses, logarithmic zoom, viewport
centering, endpoint continuity, arbitrary seeking, invalid tracks, persistent
world geometry, all 1344 finite orientation-preserving matrices, and text fit.
Native checks use a real tiny colored atlas to verify density, translation, opaque
BGRA channels, repeated-seek pixels, selected PNG equality, and a decoded MP4.
Validation checks reject malformed matrices, clocks, dimensions, and frame ranges.

Full-resolution reading frames must be visually reviewed, then the actual encoded
media must pass count/rate/duration and browser playback/seek checks. Numerical
smoothness is useful evidence, not a substitute for the user's judgment of rhythm.
Actual final measurements and retained artifacts belong in PROGRESS.md and
`evidence/atlas/`; this design record does not fabricate those results in advance.
