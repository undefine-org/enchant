# Proposed scene API contract

Status: design proposal, 2026-10-24. None of the new signatures below is a promise
that the corresponding module already exists. The current implementation uses
`scene.core`, `scene.material`, `scene.atelier`, and the editorial builder. The
purpose of this contract is to guide the next authoring milestone without freezing
the prototype's SVG-shaped interface.

## 1. Public boundaries

| Proposed surface | Responsibility | Excluded responsibility |
|---|---|---|
| `scene` | Composition root, explicit context, revision evaluation, scene identity | Starting a server during construction |
| `scene.picture` | Shapes, groups, structured paths/transforms, picture identity | Font fallback, file/network loading |
| `scene.layout` | Measurement, row/column/overlay/padding/alignment, anchors, attachments | General simulation or unrestricted constraint solving |
| `scene.text` | Structured text, typography roles, shaping/measurement requests, overflow policy | Unrecorded browser-only metrics |
| `scene.motion` | Signals, clips, cues, interpolation, sampleable timing composition | External side effects from seeking |
| `scene.material` | Material values, coordinate policy, declared randomness/resources | Silent backend-specific shader execution |
| `scene.style` and style packs | Explicit roles, defaults, scoped overrides, semantic components | Hidden mutation of unrelated scene state |
| `scene.inspect` | Lookup, evaluated values, bounds, dependency/source explanation | Modifying a captured revision in place |
| Preview/export shell | Admission, worker ownership, rendering requests, files, encoding | A second authoring model in JavaScript |

These are conceptual boundaries, not a demand to implement nine large modules
at once. Keep the first public surface small and add entrypoints when their
semantics and a concrete use are clear. Style-pack names should not determine the
underlying scene format. `art` in examples denotes the proposed editorial pack.

## 2. Authored values and evaluated values

There are two deliberately different representations:

1. **Authored content:** semantic components, layout requirements, style roles,
   material references, relationships, and time expressions. Constructed with BL
   functions; may be an arbitrary program evaluated within a captured environment.
2. **Evaluated scene:** resolved time, metrics, geometry, transforms, resource
   references, ordering, clipping, and diagnostics. Serializable and inspectable;
   no live closure or implicit mutable state is required to interpret it.

A backend consumes an evaluated scene, not arbitrary live BL functions. An
extension can expand to known authored content or implement a documented lowering
interface. Opaque code remains a conservative dependency boundary until its
semantics can be represented explicitly.

A conceptual evaluated object might be:

```clojure
;; Proposed schema fragment; coordinates and numbers are illustrative.
{:id [:postcard :scene-model :title]
 :kind :glyph-run
 :logical-bounds [0 0 364 52]
 :ink-bounds [1 -1 358 49]
 :effect-bounds [1 -1 358 49]
 :anchors {:baseline [0 39] :east [364 26]}
 :transform [1 0 0 1 208 388]
 :resources {:font "sha256:..." :glyph-run "sha256:..."}
 :provenance {:source {:path "postcard.bl" :line 18}
              :role :heading
              :font-rule [:style :editorial :type :heading]}}
```

This is an illustration of information to retain, not a finalized serialized
format. In particular, font metrics must come from the actual shaping engine;
no test should endorse these made-up metrics as a reference result.

## 3. Identity and composition

A component defines local semantic IDs. An instance establishes a namespace.
`[:postcard :card-a :title]` and `[:postcard :card-b :title]` name different titles,
even if both arise from the same function and contain equal text.

Use explicit instance keys for collections. Sibling order determines display or
layout ordering; it does not define semantic identity. Anonymous decorative
wrappers may be generated internally, but must not destabilize descendant semantic
IDs when a layout wrapper is inserted. An anonymous element that needs stable
selection, references, or procedural randomness must acquire an explicit key.

A content hash is a cache key, not an author-facing identity. Instance identity
can change while content remains shareable. Caption edits change content without
necessarily changing the selected authored object. Reparenting needs an explicit
policy; the first milestone need only preserve IDs across value edits and sibling
reordering inside one component hierarchy.

Duplicate semantic IDs and unresolved references are diagnostics. Do not append
unexplained random suffixes to make an invalid program appear valid. ID provenance
should identify the generating component and, where available, source form.

Composition rules should be predictable:

- `group` preserves explicit child order and a local coordinate system.
- `overlay` declares paint order separately from any alignment calculation.
- `row` and `column` measure children under declared constraints.
- `padding` changes logical size; a shadow changes effect bounds.
- A clip changes visible coverage; whether it changes the logical box must be
  explicit, rather than inferred from the raster crop.
- Style and motion wrappers preserve the semantic identity of their contents.

Structural comparison is meaningful for normalized evaluated values. Float
rounding, font versions, and backend rasterization still require a pinned context
for exact pixel comparisons.

## 4. Measurement and layout

Logical units are scene units, independent of raster scale. The first studio uses
an explicit logical viewport, such as 1080×1080. A 540-pixel preview samples that
same layout. It must not accidentally create different line breaks.

Proposed constructor convention: a component's explicit `:width` includes its
padding and border, so the content box is derived by subtraction. Overflow policy
handles content that cannot fit; it must not silently create negative dimensions.
This convention is provisional until tested by the first postcard examples.

Measurement returns logical, ink, and effect bounds; baseline information; and
named anchors. Distinguish layout placement from visual transforms. A post-layout
entrance should ordinarily leave its reserved logical box unchanged. Effects may
have conservative bounds; the inspector should say when a bound is approximate.

The initial layout vocabulary is row, column, overlay, padding, align, and attach.
A connector resolves endpoints after the relevant nodes are placed. Connectors
ordinarily do not feed their ink extent back into the parent layout that positioned
those nodes. This phase separation prevents common accidental cycles.

Attachments that genuinely depend on each other must form an acyclic graph or
produce a cycle diagnostic. Specify shrink/grow rules and overflow explicitly.
Do not invent a result from an unsatisfied global system of constraints.

## 5. Text and style

Text inputs include content/spans, role or explicit typography, font identity,
script/language/direction where supported, wrapping width, line height, alignment,
features, and overflow behavior. `block` and `paragraph` need documented meanings;
wrapping and whitespace policy must not depend on the backend's guesses.

For A1, admit the packaged Latin font set, explicit paragraphs, line breaks,
wrapping, baseline alignment, and missing-glyph/overflow diagnostics. Future
script coverage must be tested with an appropriate shaping implementation. Do
not generalize from a Latin specimen to an international-text claim.

Proposed precedence is defaults → style pack → lexical role overrides → local
properties. Record the winning source and enough overwritten candidates to
explain a surprising property. Avoid ambient mutable global themes; the selected
style belongs to evaluation context or authored content and revision identity.

Theme variants may change typography and therefore geometry. Consistent style
switching does not mean every theme has identical bounds. It means dependent
layout and anchors recompute coherently, without coordinate repair by the author.

Text measurement and text rendering share a canonical shaping policy. Prefer
resolved glyph runs and metrics at the backend boundary where feasible. If the
chosen library shapes text internally, establish a matching measurement interface
and verified policy before promising cross-backend equivalence.

## 6. Geometry, transforms, and materials

The public path model should use structured commands; SVG path strings can remain
an explicit backend escape hatch with limited guarantees. The portable transform
model should use ordered operations or matrices with a specified multiplication
convention. Example syntax is in API-EXAMPLES.bl.md.

For the initial convention, coordinates increase rightward and downward, local
origin is top-left, angles are explicit degrees through a named angle constructor
or documented field, and the operation list applies in its listed order. Define
the exact matrix mapping in implementation tests: translate-then-rotate must not
become ambiguous because different graphics APIs serialize transforms differently.

Materials declare their coordinate space and parameter units. Start with local
paper, halftone, hatch, and grid. A material identifier refers to a value; it is
not an arbitrary URL. Validate resource references and reject unsupported kinds.

Derive procedural variation from explicit seed, authored/instance identity,
material identity, and a named channel. Frozen grain has no time dependency.
An explicitly animated material may include time and must document continuity.
Cache keys include the material algorithm/lowering version and quality policy.
The current 512px cached tile is one backend implementation, not the definition
of paper for all future backends.

Scene colors should be tagged values rather than untyped strings at the portable
boundary. The first backend can admit sRGB colors and its declared SVG compositing
policy. A request for linear-light composition must be checked as a separate
capability; do not claim it merely because input colors were sRGB. Track alpha
convention explicitly at every packed-buffer boundary. Color interpolation is a
separate declared operation, not an accidental map over encoded channel bytes.

## 7. Time and motion

Export frame `k` at fps `n/d` samples time `k*d/n`. Scene and clip activity uses
half-open intervals `[start,end)`. The last export frame is derived from the
specified frame range; it is not an extra sample at duration. No implicit replay
is required to evaluate a requested frame.

A signal can be sampled at a time. A clip has content, duration, a local clock,
and entry/exit policy. A cue resolves a named landmark within a clip/film. An event
is an annotation queried over an interval, not permission to perform an external
side effect while evaluating a picture.

A tween's default proposed behavior is hold-start before the interval and
hold-end afterward; clipping/visibility can instead be controlled by a clip.
Zero duration is a step at the specified instant. Clamp, repeat, extrapolation,
and spring settling need separate policies. For A1, use explicit finite tweens,
sequence, parallel, delay, and stagger; defer simulation and infinite repetition.

A new motion expression should normally affect presentation transform/opacity
rather than logical layout. A paragraph can reveal a pre-shaped run without
reflow. If logical geometry really changes, declare per-sample layout and track
its dependencies. Property dependency cycles are diagnostics.

Time expressions should have an inspectable representation. Ordinary BL functions
can compute them or construct entire scenes. For opaque functions, capture the
executable environment through existing BL mechanisms and invalidate conservatively.
Do not derive semantic identity from printed functions or retain live mutable
closures in an exported evaluated scene.

## 8. Evaluation, revisions, and caching

A conceptual request is:

```clojure
;; Proposed API.
(scene/evaluate captured-revision
  {:time [5 2]
   :viewport [1080 1080]
   :assets asset-set
   :seed 41
   :quality :preview})
```

The captured revision includes executable dependencies and resource identities,
not only source filenames. A readable source hash and a source-change guard are
useful evidence but do not close every load-before-capture race. Reuse existing
BL environment ownership/capture mechanisms; do not invent a second lease system.
A first implementation must state any remaining boundary honestly.

A practical evaluation flow is: expand authored components within the captured
context; resolve style and sample relevant time expressions; measure/lay out;
resolve acyclic relationships and anchors; normalize an evaluated scene; validate
backend capabilities; then rasterize. The implementation can interleave/cache
these computations as long as observable semantics are preserved.

Keep revision identity on requests/results while allowing safely unchanged leaf
resources to be reused across revisions. Font bytes and shaping options can key
a glyph-run cache without including every unrelated scene source file. Unknown
function dependencies trigger conservative invalidation. Cache misses and cache
failures must not silently change the image.

The preview coordinator has one active render and a bounded latest pending
request initially. Every result has a revision and request sequence. Old work may
finish and enter a cache, but cannot replace a newer requested frame. Invalid edits
retain the last valid scene and display the new diagnostic. Concurrent publishers
need exclusion or generation guards before this is a reliable multi-writer tool.

## 9. Backends and output

SVG/librsvg remains the canonical initial graphics route. BL owns content,
layout/time semantics, scene/revision construction, and orchestration. The graphics
library owns raster coverage and its admitted shaping/effect work. Packed pixels
stay at that boundary; avoid per-pixel BL values or messages.

Capability reports distinguish exact support, explicitly selected approximation,
and unsupported features. The result must report selected fallbacks and their
quality implications. A future native backend consumes the same evaluated
meaning; it may need different lowering and may not support every effect.

A preview quality can reduce raster scale or material sampling, but must preserve
logical layout and declared time. The quality description belongs in artifact
identity. Canonical PNG references use the pinned backend, font set, quality,
color policy, and environment. MP4 is a separate lossy deliverable.

Exports capture a revision once. Record frame range, rational rate, dimensions,
source/executable/resource identities, backend versions, sampling and color/alpha
policy, seed, encode arguments, output hashes, and selected frame hashes. Editing
source or publishing a new preview must not change an admitted export midway.

## 10. Inspection, errors, and extension

An initial inspector needs ID lookup, bounds/anchor overlays, and a property-source
explanation. Preserve a minimal dependency trace rather than promising a complete
interpretation of arbitrary user code. Later add spatial queries and revision diffs.

A diagnostic should contain a stable kind, object/resource path, source location
when available, related dependencies, and an actionable message. Examples include
unknown material, duplicate ID, missing anchor, layout cycle, missing glyph,
overflow, unsupported effect, stale revision, and backend failure. The image should
not silently drop the corresponding object.

A component extension first expands to existing content. A new primitive/effect
must also supply validation, bounds/measurement behavior, resource dependencies,
inspection metadata, and backend lowering or a capability error. Quality and
revision identity must include extension versions. Avoid requiring a new native
compiler or proof system merely to add a useful component.

## 11. Laws and regression fixtures

Meaningful tests should cover these properties, not mirror constructor maps:

- Arbitrary seek order produces equivalent evaluated scenes at fixed inputs.
- Changing output resolution does not change text wrapping or logical anchors.
- Inserting an unrelated sibling preserves semantic IDs and seeded appearance.
- Repeated instances remain separately selectable without unnecessary resource
  duplication.
- Padding changes layout; shadow extent alone does not change paragraph spacing.
- A caption/font edit recomputes affected measurements and connector endpoints.
- Reusing a valid cached resource preserves pixels under the pinned context.
- Failed edits retain the previous valid frame; stale work cannot publish over new.
- Export uses one captured revision and produces the exact requested frame range.
- Closing while work is outstanding drains owned services and compiler scopes.

Use visually reviewed fixtures for typography, clipping, alpha, transformed ink,
material scale, and staged motion. The current editorial keyframe is a starting
quality reference, not proof that every future style or backend is correct.

## 12. Compatibility and adoption

Keep the original demo and editorial helpers working while adding the new surface
through adapters. Port the living postcard first. Extract common operations only
when their measurement/time/identity rules are clear. Do not rename every helper
or rewrite the runtime before a new public example can be reviewed.

Publish the authored/evaluated schema version and supported capabilities. Keep
normalization/migration functions explicit. Unknown fields should be rejected or
preserved through a documented extension namespace, never silently interpreted.
A frozen major API comes after several demanding compositions, not after the first
pleasant function names. The next acceptance gate is [A1](API-MVP.md).
