# From plates to one transforming organism

The user rejected the slide structure of the 56-second atlas, while approving
its visual quality and asking that it remain committed. It is already preserved
by 785bf079. The new direction explicitly supersedes the camera-only atlas brief:
no more plates, repeated heading/body templates, or camera travel between slides.
Preserve the earlier no-entrance/exit preference, while allowing genuine geometry
and relationship transformations in a single continuous composition.

The new film follows one keyed system across scales: a seed, a radial organism,
a branching system, a time ribbon, a magnified inspectable component, and an
orbital constellation. The same nodes/edges persist. Shape, position, orientation,
scale, and attachment geometry change; opacity is not an arrival/departure tool.
Camera focus follows semantic objects during deep pullbacks and dives, rather
than visiting independent content panels. Short inscriptions belong to the
structures and their scale, rather than six replacements for slide titles.

`scene.choreo` introduces keyed formation correspondence, logarithmic scale
interpolation, shortest-angle turns, continuous attachment endpoints, and focus
blending over named objects. It is a finite sampleable transformation vocabulary,
not arbitrary topology inference or simulation. Missing correspondence and
unresolved attachments must fail. Stable IDs and ordering survive reordering of
the target formation.

The graphics route expands from one static atlas to cached native vector paths
and per-frame BL-authored transforms/curves. This keeps deep zooms crisp and makes
the geometry itself transform. Python/Cairo executes captured drawing values;
it does not invent formations or camera choreography. Reuse packed surfaces and
one encoder, declare texture policy, validate plans, cap resources, and retain
actual visual/motion evidence. The studio remains an independent track.

## Actual first vocabulary

```clojure
(ns transformation-example (:require [scene.choreo :as choreo]))
(def seed
  (choreo/formation [{:id "a" :at [0 0] :angle 0 :scale 1}
                     {:id "b" :at [80 0] :angle 20 :scale 1 :parent "a"}]))
(def branch
  (choreo/formation [{:id "b" :at [160 -100] :angle -30 :scale 0.7 :parent "a"}
                     {:id "a" :at [0 100] :angle 0 :scale 1}]))
(choreo/morph seed branch (choreo/progress 2 0 4))
(choreo/path-morph [["M" 0 0] ["C" 10 0 20 20 30 20]]
                  [["M" 0 0] ["C" 5 20 25 0 30 20]] 0.5)
```

The 48-second piece uses large camera scale changes (0.48–4.5), actual object
following, curved attachment reconfiguration, corresponding contour morphs,
logarithmic scale, and shortest-angle turns. Its point/parent correspondence is
authored rather than inferred. The special seed remains the same object as it
changes between circle, leaf, and lens contours. Text is part of the diagram at
different scales, not repeated heading/body panels.

Full-size review exposed dense crossing connections and colliding annotations.
Radial formations now attach along their branches, and the two magnified instances
are deliberately separated in the formations. Cartographic label halos preserve
legibility over connections without introducing text panels. These are concrete
art-direction decisions, not proof that arbitrary generated layouts will be good.
