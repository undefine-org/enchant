# Experimental scene authoring

The `scene.*` API is experimental. Scene data formats, layout and rendering
behavior may change between releases. The library uses ordinary BL values and
explicit time samples; shaping and graphics run only when requested.

| Namespace | Purpose |
| --- | --- |
| `scene.core` | Validate scene values, rational frame times and escaped SVG output |
| `scene.material`, `scene.atelier` | Seeded paper, ink and editorial components |
| `scene.geometry`, `scene.picture` | Structured paths, affine transforms and bounds |
| `scene.text`, `scene.layout` | Canonical text outlines and measured composition |
| `scene.inspect` | Semantic object lookup, bounds and property explanations |
| `scene.motion`, `scene.clip` | Cue-relative entrances and sampleable clip schedules |
| `scene.camera` | Continuous camera paths with explicit zoom and roll |
| `scene.choreo` | Keyed formation and compatible structured-path interpolation |
| `scene.score` | Continuous, finite vector-valued Hermite tracks |

```clojure
(ns example.picture (:require [scene.core :as scene]))
(scene/svg {:width 240 :height 120 :time 0
            :objects [{:id "card" :kind :rect
                       :attrs {:x 20 :y 20 :width 200 :height 80
                               :fill "#f3ead7"}}]})
```

Geometry is finite and explicit. Listed transforms apply in listed order.
Components scope local semantic IDs; insertion and reordering preserve named
objects. Layout records logical, ink and conservative effect bounds. Shadows
extend effect bounds while retaining logical layout size. Inspectors report
explicit settings and style roles.

`scene.text/measure!` accepts requests plus options containing `:font-dir`.
Pango supplies metrics and Cairo extracts outlines from the same shaped layout.
Rendering uses those outlines. The packaged example fonts are DM Sans,
Instrument Serif and Patrick Hand, with their OFL licenses. Unknown families,
missing glyphs and invalid dimensions refuse. Linux shared Pango/Cairo libraries
and Python 3 are required; `nix/scene-tools.nix` supplies the pinned tools.
`:worker`, `:python` and `:rsvg` select explicit worker/tool paths. The default
worker comes from the selected SDK. Results include font hashes and backend
versions. General multilingual typography remains outside this preview's scope.

Clip combinators take options first, then data content or an ordered child
vector. `schedule` derives scoped intervals and cues; `sample` queries local
time without invoking content functions. Intervals are half-open. Explicit
content represents a hold. Zero-duration leaves are inactive.

Camera tracks require positive durations and matching endpoint poses. Sampling
holds the endpoint outside the track. Zoom is logarithmic; roll is explicit.
Formation morphs match node IDs, interpolate scale logarithmically and follow
the shortest angle. Path morphs require matching operators and contour order.
Authors supply topology and conservative path bounds. Hermite score channels
may overshoot; authors choose bounds for physical controls.

The generic examples are in `examples/scene-renderer`. The SVG/librsvg route
and packed Cairo workers are optional display backends. PNGs and encoded video
have different quality properties; retained backend/font identities describe a
render. Full-film export and interactive studio checks are separate from the
finite language tests. See the example README for commands and resource limits.
