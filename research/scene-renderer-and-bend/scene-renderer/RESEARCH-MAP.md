# Inspirations, API decisions, and what makes this medium distinctive

Recorded 2026-10-24 after the two-track films. The full prior conversation's
substantive inspiration notes, primary sources, API semantics, and code examples
were already committed in API-RESEARCH.md, API-SOURCES.md, API-CONTRACT.md, and
API-EXAMPLES.bl.md. This index connects those documents to today's implementation
and records the newer camera-led presentation direction. It does not replace the
longer research or relabel proposed interfaces as implemented ones.

## Inspiration-to-decision crosswalk

| Inspiration | Decision to preserve | Working subset | Still open |
|---|---|---|---|
| Racket Pict | Pictures compose through dimensions, baselines, structure, and findable subpictures | Logical/ink/effect bounds, anchors, row/column/overlay/padding, transformed indexing | Rich finders, attachment graphs and routing |
| Typst | Keep semantic content and scoped appearance until resolution | Text roles, explicit style values, canonical paragraph measurement/outlines | Rich spans, lexical role overrides, deeper provenance, broader script specimens |
| Motion Canvas | Express relationships between animated properties | Cue-relative finite tweens and immutable arbitrary-time sampling | General signals, competing-property policies, richer choreography |
| Houdini | Treat procedural geometry as attributed data; identity is not element number | Keyed instances, procedural leaves/petals, stable material tiles | Random channels, rest/world/output coordinates, deformation/path tools |
| Tidal/Strudel | Compose temporal phrases; query intervals independently of playback | Finite clip/sequence/parallel/delay/retime/cues | Event queries, repeat policy, beat maps, audio integration |
| OpenUSD | Separate authored, content, and instance identity; make variation traceable | Scoped semantic IDs, component parameters, explicit local styles | Layered overrides, general variants, reparenting policy |
| Salsa | Separate deterministic queries and their input dependencies | Shaping reuse, material reuse, selected-frame caches | Fine-grained dependency tracking, coherent executable hot replacement |
| Vega | Keep the visual document queryable | Object lookup, bounds/anchor overlays, font/color origins | Spatial queries, revision diffs, source dependency explanations |

Primary references and evidence boundaries are in [API-SOURCES.md](API-SOURCES.md).
These systems supply ideas; we do not claim to reproduce their full semantics.

## API record and implementation map

- [API-RESEARCH.md](API-RESEARCH.md): detailed rationale, examples, tradeoffs, and
  deliberate restraints for every inspiration above.
- [API-CONTRACT.md](API-CONTRACT.md): authored/evaluated boundaries, identity,
  measurement, typography, materials, clocks, revisions, backend and extension laws.
- [API-EXAMPLES.bl.md](API-EXAMPLES.bl.md): preserved proposed examples plus the
  actual finite `scene.clip` interface. Proposal code is explicitly labeled.
- [API-MVP.md](API-MVP.md): the original postcard acceptance programme and play
  sessions. Later progress does not silently close all those acceptance gates.
- [Library README](../../../priv/lib/scene/README.md): actual callable surface.
- [TRACKS.md](TRACKS.md): independent studio and visual-language delivery tracks.
- [PROGRESS.md](PROGRESS.md): actual tests, films, measurements, and limitations.

Public constructors favor options maps. Geometry/transform/time semantics belong
to the scene model; serialization belongs to the backend. Content hashes are not
selection IDs. Fonts and shaping options participate in revision meaning. A shadow
changes effect bounds, not paragraph spacing. Sampling time does not execute
external actions. Unsupported requests must produce diagnostics. New extensions
need bounds, dependency/resource identities, inspection, and capability handling.
Functions and data come first; macros should earn their place through better
notation or provenance rather than hide execution.

## What makes this approach distinctive

The combination matters more than claiming that any individual feature is unique:

1. **A picture can be a program and still be a document.** Ordinary Lisp functions
   build meaningful, measurable objects that remain inspectable after evaluation.
2. **One definition can produce a family.** Components and transformations express
   botanical illustrations, diagrams, annotations, and typography as small visual
   languages rather than copied drawing commands.
3. **Content and geometry can stay connected.** Actual text metrics affect card
   size; anchors affect connectors; identities preserve selection through reorder.
4. **Time is addressable.** A requested moment has meaning independently of the
   path the playback cursor took to reach it. Nested clips have their own clocks.
5. **The authoring language also owns the workflow.** BL constructs scenes and
   coordinates revisions, preview, and export. JavaScript transports controls and
   frames. Pango/Cairo/librsvg/FFmpeg supply named graphics/media mechanisms.
6. **Art direction is reusable knowledge.** Type hierarchy, spacing, ink character,
   material scale, and rhythm can be expressed as explicit components and values.

These are working directions with evidence, not superiority claims. Stronger
source/executable capture, generic studio inputs, general effects, and broader
typography still require implementation. The renderer remains independent of
the Bend/compiler programme.

## New presentation brief: a continuous atlas

The user explicitly requested a longer, more complete presentation with natural,
dynamic, thoughtful pans and zooms, and **no entrance or exit animations**.
All content will therefore exist in a persistent illustrated world from the
first frame. No title fades, card arrivals, scale-from-zero, stroke reveals,
animated masks, cut transitions, or object disappearance. A moving viewport
provides editorial emphasis and continuity. Geometric frame cropping is camera
framing, not an animated reveal mask.

The proposed approximately one-minute presentation visits six connected plates:

1. A language for little worlds: the program as sketchbook.
2. Meaning before coordinates: text metrics, layout, and anchors.
3. One idea, a family of forms: functions, instances, and material character.
4. Time as a place to visit: sampleable clocks and retiming.
5. Ask the picture how it works: bounds, anchors, and property origins.
6. A living medium: shared scene meaning across preview/export and the open horizon.

Motion has a reading rhythm: a quiet push into each plate; an eased, spatially
motivated move to the next; scale breathing that gives context during travel;
and a deliberate final hold. Position follows explicit curved paths. Zoom is
interpolated in logarithmic scale. Quintic timing has zero endpoint velocity and
acceleration, avoiding abrupt starts or stops; this is a deterministic camera
model rather than a stateful physics simulation. Camera roll remains restrained
so body text stays readable. Shot durations are editorial choices, not a speed
benchmark. The film is initially silent; its written content must stand alone.

## Static-atlas backend experiment

A camera-only film permits a useful graphics optimization: BL authors one vector
world and all camera matrices, shapes text once, and samples the camera at exact
frame times. The graphics worker rasterizes a captured world at a declared density
then applies those BL matrices in Cairo to packed surfaces. FFmpeg encodes packed
BGRA frames. No scene authorship or camera planning moves into Python/JavaScript.

This route has a finite texture-resolution ceiling, unlike rerasterizing vectors
at arbitrary zoom. Declare atlas density, maximum zoom, filtering, alpha/color
policy, and output resolution; retain lossless selected frames and compare them
through the same camera sampler. Do not call raster-atlas output pixel-identical
to arbitrary vector rerasterization. Cache identity includes the atlas policy.
Cap the entire process tree and validate frame plans before allocating large
surfaces or launching an encoder.

Primary graphics references inspected for this experiment:

- [Cairo source surfaces](https://cairographics.org/manual/cairo-cairo-t.html#cairo-set-source-surface):
  source binding uses the active coordinate system; apply the camera before binding.
- [Cairo pattern filtering and matrices](https://cairographics.org/manual/cairo-cairo-pattern-t.html):
  filtering is explicit; pattern matrices map user coordinates into source space.
- [Cairo surface ownership and pixel access](https://www.cairographics.org/manual/cairo-cairo-surface-t.html):
  flush before reading native data; retain and destroy owned surfaces correctly.

The camera-only constraint is this film's artistic direction, not removal of
entrance/exit operations from the general library or earlier historical films.
