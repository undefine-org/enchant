# Two renderer tracks after the postcard

Approved direction, 2026-10-24. The user asked for the studio and the visual
language to develop as separate tracks, with visual capability leading and the
studio catching up. Both remain separate from the Bend/compiler programme.

## Shared foundations already implemented

BL components construct picture values. Pango measurement and Cairo outlines
share canonical glyph geometry. Layout preserves logical, ink, and conservative
effect bounds, semantic identities, and anchors. The selected-frame studio has
bounded physical work, stale-result suppression, and last-valid-frame retention.
Immutable scenes support arbitrary seeking. Packaged fonts, material values,
source/resource provenance, and canonical PNG/MP4 output already exist.

These are foundations rather than the final visual vocabulary. The postcard is
one composition, not the product's universal document schema. The implemented
surface is in `priv/lib/scene/README.md`; the broader research remains proposed.

## Track S: studio and workflow

1. Export exactly the current UI configuration through the canonical exporter.
   Capture a revision once; bound export work independently of preview admission;
   display progress/failure and retain a usable last frame.
2. Introduce a general BL composition entrypoint with declared parameters, after
   varied compositions establish a useful contract. JavaScript presents controls
   and transport; it does not duplicate scene authorship.
3. Implement coherent source refresh using existing executable/environment
   ownership. Close or explicitly qualify load-before-capture boundaries.
4. Extend inspection from font/color origins to dependencies, clipping, source
   locations, and revision differences. Keep selection stable across edits.
5. Distinguish uncached scrubbing, cached playback, and high-quality stills.
   Add project save/load without silently changing revision meaning.

Track S accepts independently testable workflow slices. It must not require every
new drawing capability to acquire editor controls before a film can use it.

## Track V: visual language and clip composition

1. Establish an inspectable temporal algebra: finite clips, sequence, parallel,
   delay, retime, cues, and half-open activity. Layout remains independent. Signals
   sample properties; clips schedule content; event queries do not perform effects.
2. Build the twelve-second illustrated transformation described below. Start with
   path drawing, geometric clipping, nested clocks, and camera framing; use actual
   stills and motion to decide whether the abstractions produce good work.
3. Extract reusable geometry operations: path length/sampling/trimming, controlled
   deformation, expressive strokes, and attached/routed connectors. Distinguish a
   conservative dash reveal from true measured path trimming.
4. Expand materials with explicit local/world/output coordinates, independent
   random channels, declared scale/strength units, and stable rest coordinates.
   Add alpha masks, isolated groups, and effects with capability/bounds contracts.
5. Expand typography: spans, baseline composition, line/word/glyph addressing,
   fixed-layout reveals, and more deliberate shaping controls. Broader scripts
   require actual specimens and glyph coverage, not a general support claim.
6. Add captured image assets with cropping/masking/color policy and reusable
   camera/viewports. Shared-element transitions preserve identity across shots;
   overlapping property animation needs a declared combination policy.

Do not implement this entire list before making another film. Each addition must
earn its place in an authored composition, with visible quality and documented
semantics. SVG/librsvg is the current backend; use demanding fixtures to establish
actual limitations before switching. No GPU/compiler work is a prerequisite.

## Next film: a seed of possibility

An original twelve-second square editorial motion study:

- Opening: a strong typographic plate introduces a small seed/idea.
- Diagram: drawn connections and annotations establish relationships.
- Detail: camera framing carries the same illustration into an enlarged view;
  branching stems and leaves appear through clipped, stable material layers.
- Closing: the frame settles into a composed botanical plate with a final line.

Acceptance includes arbitrary-time sampling, exact frame boundaries, coherent
fonts/materials, explicit clip clocks, and selected-frame/full-film agreement.
It also includes visual review at 1080px and watching motion: hierarchy, textures,
edges, continuity, pacing, and readable holds. A passing scheduler test cannot
establish aesthetic quality. Retain selected PNGs, a viewable film, provenance,
actual measurements, and clear limitations.

## Why these inspirations still matter

Pict supplies measurable composition; Typst semantic typography and appearance;
Motion Canvas property relationships; Houdini attributed procedural geometry and
material coordinates; Tidal/Strudel temporal phrases; OpenUSD instances and
traceable overrides; Salsa explicit recomputation dependencies; Vega queryable
visual documents. Detailed rationale and primary references remain in
[API-RESEARCH.md](API-RESEARCH.md) and [API-SOURCES.md](API-SOURCES.md).

Functions and data are the first extension mechanism. Small languages for plants,
annotations, printmaking, or diagrams can encode visual judgment above a common
scene model. Macros may improve notation or source provenance when a concrete
need appears; they are not required to make the first expressive components.
