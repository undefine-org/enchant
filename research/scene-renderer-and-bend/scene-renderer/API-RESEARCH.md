# API research for composable pictures and motion

Research and proposal date: 2026-10-24. Build a small compositional language for
pictures, layout, materials, and time, backed by a precise evaluated scene. Lisp
should make it easy to invent visual languages; the underlying representation
should make those languages reliable to render, inspect, revise, and export.

This records and expands the preceding API discussion, including its less obvious
inspirations. [API-SOURCES.md](API-SOURCES.md) separates reference facts from our
proposed adaptations. [API-CONTRACT.md](API-CONTRACT.md) defines the intended
semantics. [API-EXAMPLES.bl.md](API-EXAMPLES.bl.md) preserves the code examples.
[API-MVP.md](API-MVP.md) proposes the first practical milestone.

## 1. The goal and the starting point

The long-term unit of authorship is an ordinary BL program that constructs visual
content and describes its behavior over time. One scene definition should support
a frame, a film, an inspectable preview, and eventually other faithful outputs.
The first language should serve typography, diagrams, procedural illustration,
and data-driven visual explanation. Broader uses are reasons to preserve clean
boundaries, not reasons to implement every feature at once.

The current core, materials, atelier, PNG preview, and export are useful working
experiments. The editorial study demonstrates a higher visual standard with
packaged type, paper grain, ink outlines, hatching, halftones, layered cards, and
staggered motion. It does not yet provide the API proposed here. Raw SVG strings,
long positional arguments, manual text coordinates, global palette constants,
and eager full-film generation should not become permanent public contracts.

A successful API must improve both the image and the work of making it. Useful
abstraction removes repeated design decisions while leaving the decisions that
matter visible: composition, hierarchy, rhythm, emphasis, and material character.
An elegant function name is not evidence of good typography or an effective scene.

## 2. Direct inspiration from Racket Pict

### The source mechanism

Pict represents pictures as composable values. Its datatype preserves dimensions,
text baselines, and relationships to embedded subpictures; finders locate those
subpictures inside a composition. Constructors and combiners provide the concrete
functional-picture precedent. [Sources P1–P4](API-SOURCES.md#pict).

### The adaptation for BL

A picture should participate in composition through a small, explicit measurement
interface. Nesting must preserve enough structure to measure a component, address
its anchors, and locate its children after transforms. This is more valuable than
adding one helper for every possible diagram shape.

Distinguish three boxes:

- **Logical bounds:** the box used by the layout algorithm.
- **Ink bounds:** the extent of drawn shapes and glyphs.
- **Effect bounds:** conservative coverage including shadows, blur, and other
  overflow needed for cropping, damage tracking, and raster resource allocation.

A label can have an overhanging italic glyph without changing every neighboring
column. A shadow can extend beyond the card without increasing the paragraph's
line spacing. Padding changes the logical box deliberately. Rotation must produce
usable transformed bounds, even when they are conservative rather than tight.

Named anchors such as `:center`, `:east`, `:baseline`, `:input`, and `:output`
should be returned by layout. Connectors refer to these anchors rather than
copying coordinates. Moving a card or changing its caption then updates the
connector through the dependency model.

Start with row, column, overlay, padding, alignment, and attachment. These compose
into most initial scenes. Use a bounded layout algorithm with explicit width and
height constraints before attempting an unrestricted global constraint solver.
Unsatisfied constraints and cycles need diagnostics with the relevant objects.

### The restraint

Do not copy Pict's entire representation or assume its drawing-context behavior
is the right backend boundary. Our scene values must support revision capture,
material resources, animation sampling, and backend capability checking. Borrow
the picture algebra and measurable composition, then specify our own contracts.

## 3. Direct inspiration from Typst

### The source mechanism

Typst content values contain structured elements and fields. Scoped set rules
supply appearance defaults, while show rules can replace presentation. Its layout
reference supplies a useful separation between content and arrangement.
[Sources T1–T2](API-SOURCES.md#typst).

### The adaptation for BL

A heading should remain a heading until style resolution. A paragraph should
remain structured content until shaping and line breaking. Avoid reducing either
to pre-positioned glyphs too early in the authoring layer.

The text API needs blocks, spans, paragraphs, explicit fonts, language/direction,
features, line height, alignment, wrapping constraints, and overflow behavior.
A small first implementation can admit only a declared subset while reporting
unsupported requests. A font-size property alone is not a typography system.

Measure text with the shaping policy used by canonical rendering. Do not measure
with a browser fallback font and export through another engine. Capture font
bytes and shaping-relevant settings in revision/resource identity. Missing glyphs,
missing fonts, and overflow should be inspectable outcomes. The first studio can
support its packaged Latin font set without pretending to support every script.

Semantic roles allow a style pack to supply hierarchy:

```clojure
;; Proposed API, not the current scene.atelier functions.
(text/block {:role :heading} "From a thought")
(text/paragraph {:role :explanation}
  "A small language for things that move.")
```

Resolve appearance in an explicit order: library defaults, selected style pack,
lexically scoped role overrides, then local properties. This is a proposed BL
rule, not a claim about Typst's exact cascade. Attach provenance to the winning
values. Broad selector systems and arbitrary show-rule rewriting can wait until
simple scoped roles have proved insufficient.

Typography affects geometry. A font change can invalidate line breaking, component
size, and connectors. A color change usually should not. Keeping those dependencies
separate benefits correctness, refresh speed, and explanations.

### The restraint

Do not bring an entire publishing engine into the renderer to get a paragraph.
The lesson is structured content and scoped appearance. Choose a real shaping
and measurement boundary and make its admitted capabilities explicit.

## 4. Direct inspiration from Motion Canvas

### The source mechanism

Motion Canvas signals express values that change over time and dependencies
between them. Its animation-flow API uses generators and composition helpers.
[Sources M1–M2](API-SOURCES.md#motion-canvas).

### The adaptation for BL

Authors should be able to express relationships: the arrow follows the card, the
caption fades after the heading arrives, and a node's emphasis follows a cue.
They should not have to repeat numerical updates in a loop.

Keep the meaning independently sampleable. A signal is a value at a time; a clip
has a duration and local clock. Sequence, parallel composition, delay, overlap,
and stagger construct explicit timing structures. A playback clock chooses a
time to request. It does not define the scene's meaning.

Define behavior before and after each animation interval, including zero-duration
changes. For a scalar tween, specify interpolation and easing; for a color,
specify the interpolation space; for transforms, distinguish semantic parameter
interpolation from matrix interpolation. Missing interpolation rules should fail
rather than guess for arbitrary maps.

Layout animation needs a policy. Prefer transform/opacity animation over fixed
logical boxes for the first studio. A typewriter reveal can shape and lay out
its complete text once, then change visibility. Reflowing on every new character
is a different, explicitly requested effect. Later admit per-sample layout when
the intended animation changes logical geometry.

### The restraint

Do not make coroutine replay the only way to seek. Imperative-looking sugar could
compile to the timing model later. Arbitrary stateful simulations need an explicit
checkpoint model, not hidden mutation inside ordinary scene functions.

## 5. Direct inspiration from Houdini

### The source mechanism

Houdini represents geometry with named attributes at several granularities and
provides tools to inspect them. Its documented `id` is distinct from element
number, and rest coordinates can keep procedural textures attached to geometry.
[Source H1](API-SOURCES.md#houdini).

### The adaptation for BL

Procedural graphics should be ordinary transformations of attributed values:
map over records to make cards, derive emphasis from a value, attach a material,
then compose the result. Preserve meaningful attributes rather than baking them
into anonymous drawing commands immediately.

Object identity must survive insertion and reordering. Use a domain key, such as
`:parser`, rather than the third item's position. Derive any procedural variation
from revision seed, stable object identity, material/effect identity, and a named
random channel. Adding one unrelated object should not reseed the whole picture.
Expose random channels so changing a paper's flecks need not alter its edge shape.

Coordinate space is part of a material's meaning. Grain might stick to a sheet,
a light field might occupy world coordinates, and a film overlay might be locked
to the output. Define material-local, scene/world, and raster spaces explicitly.
Texture strength and spatial frequency must be specified in a declared unit;
preview resolution should not silently change the visual material.

Inspection should expose the intermediate geometry and material decisions, not
just a final image. The author should be able to see object IDs, bounds, anchor
locations, evaluated properties, and the stage that produced them.

### The restraint

Borrow procedural attributes and inspection without building a node editor or
importing Houdini's full geometry hierarchy. Node-like dependencies can arise
from ordinary BL functions and a small recorded evaluation model.

## 6. A visual style should be a reusable design system

This is our design synthesis, informed by the earlier art-direction experiment.
A style pack should define type and spacing scales, palette roles, stroke
character, corners, texture scales and strengths, shadow rules, and a related
motion vocabulary. Keep these dimensions separately adjustable.

For example, the warm-paper style can favor broad margins, quiet technical labels,
a single strong display face, occasional handwritten notes, and a restrained
accent. A blueprint style can use different paper, line hierarchy, and type
roles while preserving the same semantic diagram. These are authored choices;
a renderer cannot guarantee beauty merely by supplying a preset.

Semantic components can encode useful visual judgment: a callout may choose a
readable caption width; a diagram node may expose ports with a minimum gap; a
chart may reserve labels before allocating the plotting area. Their decisions
must be visible and overridable. Avoid a global magic-style function that edits
every property without a documented precedence rule.

High-level composition should preserve contrast hierarchy, whitespace, optical
alignment, legibility, and deliberate restraint. Keep a small collection of
visually reviewed fixtures at actual display size and in motion. Tiny contact
sheets are useful for pacing; they cannot validate fine texture or type edges.

## 7. Less obvious inspiration from music and live coding

### The source mechanism

The Strudel/Tidal pattern model queries a span of time to obtain events, with
fractional times and compositional transformations of the query/results. This is
a useful musical precedent for temporal structure. [Source U1](API-SOURCES.md#musical-patterns).

### The adaptation for BL

Separate four concepts:

| Concept | Meaning | Example |
|---|---|---|
| Signal | A value sampled at time `t` | Position, opacity, a counter |
| Clip | A composition over a bounded local interval | A card entrance lasting 0.6 seconds |
| Cue | A named editorial landmark | `:explanation` begins at 1.2 seconds |
| Event | An annotation over a point or interval | A subtitle segment or a sound marker |

Sequence adds durations. Parallel composition takes a declared enclosing duration,
usually the maximum. Delay shifts local time. Stagger schedules related entrances
with a declared spacing. Hold supplies an interval of stable meaning. Retime maps
parent time into child time. Repeat needs finite/infinite duration policy and a
boundary rule; the first milestone can defer it.

Use exact/rational frame indices at the export boundary. Keep time units separate
from frames, beats, and normalized progress. A musical tempo map could later map
beats to seconds without changing the scene's property evaluators. Cues permit
retiming a story without searching through dozens of hard-coded timestamps.

An event query should have explicit interval inclusion rules and stable event
identity. Seeking must not accidentally trigger external side effects. Preview
sound playback and export mixing are shell responsibilities over a captured event
track, not arbitrary actions executed by `scene(t)`.

This approach could support rhythmically repeated diagrams, recursive reveal
patterns, synchronized captions, or future audio-reactive work. It does not require
audio in the first useful release. Preserve the temporal algebra now and add sound
when a real project needs it.

## 8. Less obvious inspiration from OpenUSD

### The source mechanism

OpenUSD composes reusable scene descriptions through references, layers, variants,
and overrides with specified strength ordering. It also supports scenegraph
instancing. [Sources D1–D2](API-SOURCES.md#openusd).

### The adaptation for BL

A reusable component should support local variation without copied implementations.
One use can change a caption or accent while another keeps the default. The
resolved scene should show where an override came from.

Begin with component parameters, instances, semantic style roles, and explicit
local overrides. A simple precedence rule and a diagnostic for unknown override
paths are enough to start. More general layered authoring is a later extension
when actual films require it. Preserve provenance so future layers can be added
without flattening every artistic decision prematurely.

Identity has three separate jobs:

- **Authored identity:** the semantic object that should stay selected across edits.
- **Content identity:** the evaluated content/resources safe to compare or cache.
- **Instance identity:** the occurrence of a reusable definition in this composition.

Two cards with identical contents can share a texture or glyph run while retaining
different selection paths and animation. A content hash must not become the user
selection ID: changing a caption would then destroy the object's identity.

Child names live within component instances. A `:title` in one card does not
collide with a `:title` in another. Reorder instances by changing a vector while
keeping their explicit keys. Reparenting is a distinct operation; specify whether
it preserves an authored key rather than assuming tree paths solve every case.

### The restraint

Adopt a small, predictable subset. Do not copy USD's full composition machinery,
file formats, or 3D schema. This is a lesson about modular artistic decisions.

## 9. Less obvious inspiration from incremental query systems

### The source mechanism

Salsa caches deterministic derived queries and tracks dependencies across input
revisions. Its documentation makes the deterministic-input boundary explicit.
[Sources Q1–Q3](API-SOURCES.md#incremental-queries).

### The adaptation for BL

Model expensive work as explicit computations with declared inputs:

```text
shape-text(font, content, typography)
layout(component, constraints, sampled-properties)
resolve-material(material, coordinate-policy, quality)
evaluate-scene(revision, time)
render-frame(evaluated-scene, backend, quality)
```

A caption edit invalidates shaping, affected layout, connectors, and rendering.
A grain-strength edit should ordinarily leave glyph shaping intact. A time change
that affects only a group transform should not require rebuilding font resources.
Do not include the whole revision hash in every leaf resource key if unchanged
font and material bytes can be reused safely across revisions.

Start with explicit dependency keys and coarse conservative invalidation. Build
fine-grained tracking only where measurements show value. Ordinary user functions
must remain possible. If an opaque function's dependencies are unknown, capture
its execution environment and invalidate conservatively. Hashing a printed closure
or trusting a function name is not a sound executable identity policy.

Separate a latest-wins request coordinator from pure scene evaluation. Bound
admission, coalesce pending work, reject stale publication, and drain workers on
shutdown. A cancelled wait is not evidence of physically cancelled native work.
These obligations apply even if the cache makes most requests fast.

### The restraint

Borrow the query model without making a new compiler programme a renderer
prerequisite. Use existing BL environment/executable ownership mechanisms when
capturing a revision. The first useful optimization is selected-frame preview,
not a wholesale incremental-computation framework.

## 10. Less obvious inspiration from queryable visual documents

### The source mechanism

Vega separates declarative visualization specification from runtime dataflow;
its view API exposes scenegraph and signal interfaces. The Reactive Vega paper
connects data, scene construction, and interactions in one dependency architecture.
[Sources V1–V4](API-SOURCES.md#vega).

### The adaptation for BL

Keep the evaluated scene available as a structured query target. An inspector or
agent should be able to ask:

- Why is this label at this position?
- Which rule supplied its color and font?
- What clipped this object?
- Which objects overlap this caption?
- Which dependencies changed between revisions?
- Which backend fallback, if any, was selected?

An explanation needs evaluated values, dependency links, and source provenance.
A useful initial answer is a small derivation chain, such as `title font → text
metrics → column width → card size → east anchor → connector endpoint`. It does
not need to interpret the author's intent or generate a natural-language story.

Use stable object selection through layout wrappers and style expansion. Preserve
semantic relationships, such as a connector's source and destination, alongside
the eventual path geometry. Those relationships support editing and debugging.
A later graphical editor can emit the same scene values and parameter overrides.
It should not require a separate JavaScript scene language.

Start with lookup by ID, bounds/anchors overlays, and a property-source explanation.
Spatial queries, scene diffs, and agent-assisted corrections can follow. A scene
need not live in a database engine to have a queryable model.

## 11. Public API practices to stabilize

1. Prefer options maps for extensible constructors. Reserve positional arguments
   for short, unambiguous mathematical operations.
2. Represent paths, transforms, colors, and references as structured values.
   SVG serialization belongs to a backend; do not expose its strings as the only
   portable public interface.
3. Define time, units, coordinate spaces, alpha, interpolation, and ordering before
   promising interchangeable backends.
4. Capture deterministic revision inputs, assets, executable dependencies, seed,
   and quality. Preserve a coherent last-valid preview on failed edits.
5. Make evaluated scenes versioned and inspectable, with useful diagnostics and
   source locations where available.
6. Check backend capabilities explicitly. Unsupported features produce a failure
   or an author-selected, reported fallback. Never quietly omit an object.
7. Share scene meaning between preview and export. Declare quality differences;
   pin a canonical path when exact agreement matters.
8. Keep functions and data primary. Add macros when they improve authoring or
   capture provenance, while expanding to the same inspectable representation.
9. Distinguish supported extension expansion from opaque backend callbacks.
   Unknown bounds, hidden dependencies, or nondeterminism must not be concealed.
10. Version the semantic boundary, not just a bag of helper names. Use explicit
    normalization and migration when the representation changes.

## 12. What should guide implementation next

Stabilize measurement, identity, time, and inspection. Keep style libraries easy
to extend and renderers replaceable behind that meaning. Build the API through
real, visually reviewed compositions: typography, connected diagrams, data-driven
charts, and procedural illustration. A shared API should support them without
requiring all four in the first milestone.

The recommended first exercise is the living postcard in [API-MVP.md](API-MVP.md):
a polished, editable composition that proves automatic text/layout, named anchors,
independent motion sampling, and selected-frame preview together. Its purpose is
to expose useful API friction while producing something enjoyable to make.
