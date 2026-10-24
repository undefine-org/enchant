# Proposed authoring and inspection examples

For current executable signatures see `priv/lib/scene/README.md`. The finite
temporal subset now implemented as `scene.clip` is illustrated below; the earlier
`motion/clip` sketches remain proposed syntax rather than compatible aliases.

```clojure
;; Implemented API: data content, independent of picture layout.
(ns clip-example (:require [scene.clip :as clip]))
(def timing
  (clip/schedule
    (clip/sequence {:id "story"}
      [(clip/clip {:id "opening" :duration 2} :opening)
       (clip/retime {:id "slow-detail" :duration 4}
         (clip/clip {:id "detail" :duration 2 :cues {"bloom" 1}} :detail))])))
(clip/sample timing 4) ;; detail is active at local time 1
(get (:cues timing) "story/slow-detail/detail/bloom") ;; 4 seconds
```

The author maps sampled content/local times to pictures. Sampling does not invoke
functions, mutate a drawing, or choose arrangement. A hold is an authored interval
of stable content; a gap is empty. The botanical study is an executable example.

These are design examples, not runnable library examples. Namespaces, signatures,
cue handling, structured transforms, measurement, inspector, and studio commands
below are proposed unless specifically identified as existing. They preserve the
conversation's code and make the intended API concrete enough to review. No BEAM
was started to validate these speculative forms.

See [the contract](API-CONTRACT.md) for semantics and [A1](API-MVP.md) for the
subset to implement first. Code currently generating the editorial film lives at
[scene_demo/editorial.bl](../../../examples/scene-renderer/scene_demo/editorial.bl).

## 1. Original semantic text examples

```clojure
(text/block {:role :heading} "From a thought")
(text/paragraph {:role :explanation}
  "A small language for things that move.")
```

The selected style resolves the roles. Paragraph shaping/measurement supplies
layout metrics under a width constraint. Unsupported fonts or glyphs produce
diagnostics rather than silently selecting an unrecorded substitute.

## 2. Original conversational component and entrance

This preserves the exact illustrative component shape from the discussion:

```clojure
(defn concept-card [{:keys [id title body]}]
  (art/cutout {:id id
               :width 420
               :padding 28
               :paper :warm}
    (layout/column {:gap 12}
      [(text/block {:id :title :role :heading} title)
       (text/paragraph {:id :body :role :body} body)])))

(motion/enter {:cue :explanation
               :duration 0.6
               :effect :rise}
  (concept-card {:id :scene-model
                 :title "A scene is a function"
                 :body "Choose a time. Evaluate the world."}))
```

The containing clip supplies the `:explanation` cue. The column receives available
content width from the cutout after padding. Its child IDs are local to the card
instance. `enter` preserves those identities and applies presentation motion to
the already measured picture. It does not make each child reserve a new logical
box every frame. The exact options syntax remains open to review.

## 3. A self-contained proposed studio composition

```clojure
(ns postcard
  (:require [scene :as scene]
            [scene.layout :as layout]
            [scene.text :as text]
            [scene.motion :as motion]
            [scene.styles.editorial :as art]))

(def cards
  [{:id :compose :title "Compose"
    :body "Small values become a visual language."}
   {:id :evaluate :title "Evaluate"
    :body "Pick a time. Resolve the scene."}
   {:id :see :title "Make visible"
    :body "The same idea becomes a frame."}])

(defn postcard [items]
  (scene/composition
    {:id :postcard
     :viewport [1080 1080]
     :seed 41
     :style :editorial/warm
     :duration 6
     :cues {:explanation 0.8}}
    (layout/column {:padding 56 :gap 32}
      [(text/block {:id :heading :role :display}
         "A little world of your own.")
       (layout/column {:id :cards :gap 20}
         (mapv
           (fn [item]
             (concept-card item))
           items))])))
```

This version deliberately omits choreography from the data-generation loop.
Adding stagger should be an independent composition step, without rewriting the
card function or inventing a second data source. Portrait cards can later become
a row or another layout when their constraints fit the chosen viewport.

## 4. Layout and an attached connector

```clojure
(scene/group {:id :diagram}
  [(layout/row {:id :nodes :gap 72 :align :center}
     [(concept-card {:id :input :title "Input" :body "A structured idea."})
      (concept-card {:id :output :title "Output" :body "A visible result."})])
   (scene/connector
     {:id :flow
      :from (scene/anchor [:nodes :input] :east)
      :to (scene/anchor [:nodes :output] :west)
      :routing :curve
      :role :relationship})])
```

IDs here are resolved relative to the current component scope. The top-level
example would need a viewport wide enough for the cards or smaller card widths.
That constraint is intentional: a good API reports the fit problem instead of
quietly overlapping them. Connectors resolve after node layout and do not feed
their ink bounds back into the row by default. A1 only needs direct or simple
curved attachment, not a general obstacle-avoiding router.

## 5. Structured transforms and paths

```clojure
(scene/transform
  {:id :tilted-card
   :ops [[:translate [190 458]]
         [:rotate {:degrees -5 :about [0 0]}]]}
  (concept-card {:id :card :title "A value" :body "Still inspectable."}))

(scene/path
  {:id :underline
   :commands [[:move [0 0]]
              [:quadratic [80 12] [160 0]]]
   :stroke {:role :ink :width 2 :cap :round}
   :fill :none})
```

The operation order must have exact tested semantics. Do not infer it from the
SVG string that happens to be emitted. SVG/backend strings may remain an explicit
escape hatch, with declared portability and measurement limitations.

## 6. Materials and style remain separate values

```clojure
(def warm-paper
  (material/paper
    {:id :warm-paper
     :seed 41
     :space :local
     :grain {:strength 0.04 :scale 0.8}
     :tone [:srgb 0.945 0.922 0.851]}))

(def warm-style
  (style/derive :editorial/base
    {:materials {:warm warm-paper}
     :palette {:ink [:srgb 0.14 0.15 0.23]
               :accent [:srgb 0.78 0.30 0.22]}
     :type {:heading {:font :instrument-serif :size 44}
            :body {:font :dm-sans :size 20 :line-height 1.4}}
     :motion {:entrance {:duration 0.6 :ease :smooth}}}))
```

The numerical grain fields illustrate a desired semantic interface; their units
must be settled before implementation. An existing backend's 512px tile is an
implementation detail unless explicitly requested as a quality policy. The
selected style is captured in the scene context, not stored in a mutable global.

## 7. Time composition and cue-relative motion

```clojure
(motion/clip
  {:id :story :duration 6 :cues {:explanation 0.8}}
  (motion/stagger
    {:id :entrances :at :explanation :step 0.18}
    (mapv
      (fn [item]
        (motion/enter {:duration 0.6 :effect :rise}
          (concept-card item)))
      cards)))

(motion/sequence
  [(motion/hold {:duration 0.5} opening)
   (motion/parallel [heading-reveal diagram-reveal])
   (motion/hold {:duration 1.0} completed-picture)])
```

Clip content versus track layout must be specified so an author can choose whether
items share one space or participate in a row/column. These sketches show temporal
composition; the first implementation may use separate layout and animation tracks
to avoid making `stagger` secretly choose geometry. Seeking samples these values;
it does not execute a series of drawing mutations from the beginning.

Conceptual query boundaries from the conversation:

```text
shape-text(font, content, typography)
layout(component, constraints, time)
resolve-material(material, quality)
evaluate-scene(revision, time)
render-frame(evaluated-scene, backend, quality)
```

The refined contract adds sampled properties, material-coordinate policy, resource
identity, and captured executable context to those keys where needed. Unknown
user-function dependencies lead to conservative invalidation, not guessed caching.

## 8. Inspection and a visual explanation

```clojure
(def evaluated
  (scene/evaluate revision
    {:time [5 2] :viewport [1080 1080] :quality :preview :seed 41}))

(inspect/object evaluated [:postcard :cards :evaluate :title])
(inspect/bounds evaluated [:postcard :cards :evaluate])
(inspect/explain evaluated
  [:postcard :cards :evaluate :title] :font)
```

A proposed explanation response:

```clojure
{:object [:postcard :cards :evaluate :title]
 :property :font
 :value {:asset "sha256:..." :family "Instrument Serif"}
 :because [{:kind :role :value :heading}
           {:kind :style-rule :path [:editorial :type :heading]}
           {:kind :font-resource :asset "sha256:..."}]
 :source {:path "postcard.bl" :line 12}}
```

A1 can display this as an inspector panel and a bounds/anchor overlay. Later queries
can report overlaps, clipped coverage, and scene differences. They must distinguish
logical-box overlap from actual painted-pixel intersection and mark approximation.

## 9. Non-destructive variation and stable instances

```clojure
(def base-card
  (concept-card {:id :definition :title "A reusable idea" :body "One source."}))

(scene/instances
  [{:id :first :definition base-card}
   {:id :second :definition base-card
    :overrides {[:title :text] "A local variation"}}])
```

This sketches the later OpenUSD-inspired direction, not required A1 syntax.
Initially, ordinary function parameters achieve most of the benefit. If override
paths are added, unknown paths should be errors and their precedence/provenance
must be explicit. Resource sharing must not merge the two authored identities.

## 10. Four experiments for finding API weaknesses

1. Replace a two-word heading with a sentence. Ask whether wrapping, card height,
   connectors, and animation still make sense without manual coordinate edits.
2. Insert a card in the middle of a keyed collection. The old cards should keep
   their identities and seeded material appearance.
3. Switch from warm paper to a blueprint style. Typography/layout may recompute,
   while the content and semantic relationships remain the same.
4. Move the explanation cue by one second. The related motion moves together,
   without changing component functions or replay-dependent state.

Keep the source before/after each experiment and selected-frame evidence. The
friction log is a design input: repeated verbose code, surprising precedence,
missing measurements, slow edits, and awkward naming should alter the plan.

## 11. Existing prototype syntax for comparison

This form uses the current `scene.atelier` API and shows what we intend to improve:

```clojure
(a/cutout "card"
  "translate(190 458) rotate(-5)"
  0 0 640 286 a/cream
  [(a/annotation "caption" 30 60 32
     "A world, made of values" {})])
```

It already composes paper, edge passes, a shadow, and contents. Its long positional
geometry, global palette value, coordinate-based text, and SVG transform string
are prototype conveniences. The proposed options maps, semantic text, measurement,
and structured transforms preserve the visual idea while making it reusable.
