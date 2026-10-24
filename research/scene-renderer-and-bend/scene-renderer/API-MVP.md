# A1 living postcard studio

Status: proposed first authoring-API milestone, 2026-10-24. This is the recommended
next experiment for user review. The studio described here is not implemented by
writing this plan. The existing editorial frame, four-second film, and prototype
preview/export remain available as evidence and a visual reference.

## 1. The first result

Make a polished six-second living postcard from a title, a short sentence, and
three keyed concept cards. The cards have automatically wrapped text, shared
visual style, named anchors, simple connectors, and staggered entrances. One BL
component definition supplies all three cards. The same composition can be
sampled at any timestamp, inspected, restyled, and exported.

The author should edit content and timing rather than repair coordinates. The
preview should request the current frame without rasterizing an entire film.
The image should meet the newer editorial edition's visual standard, not retreat
to gray boxes because layout and timing are being generalized.

This proves a small, useful picture language. It does not implement every
inspiration from API-RESEARCH.md. A1 extends the existing R1/R2/R3/R4 work:

| Existing track | A1 contribution |
|---|---|
| R1 deterministic scene core | Measurable components, local IDs, structured transforms, a few layout/text operations |
| R2 live preview | Selected-frame requests, readable diagnostics, bounds/anchor inspection |
| R3 export | Reuse the captured revision and canonical renderer for the postcard film |
| R4 workflow evidence | Measure warm text/style/time edits and current-frame backlog behavior |

## 2. What the author can do

- Write one `concept-card` function with an options map.
- Supply three records with stable semantic IDs, captions, and body text.
- Arrange them with a small row/column/overlay vocabulary under explicit constraints.
- Connect named anchors without repeating coordinates in arrow geometry.
- Choose a style pack and locally override an accent or text role.
- Place entrances relative to a named explanation cue and adjust stagger spacing.
- Seek, step, play, and request a crisp still before exporting the whole film.
- Select an object and inspect its ID, three bounds, anchors, time, and a property
  source explanation.
- Make an invalid edit and keep the last valid preview while seeing the problem.

A property inspector is useful first. Dragging an object and writing source edits
back automatically can wait; that requires an explicit authoring/override model.

## 3. The deliberately small surface

These names are provisional proposals, not the current implemented modules:

| Area | A1 scope | Later |
|---|---|---|
| Content | Group, rect/circle, structured path/transform subset, semantic text | Arbitrary image/video assets, extensive path tools |
| Layout | Column, row, overlay, padding, alignment, width-constrained wrapping | Full constraints, advanced responsive layout, obstacle routing |
| Measurement | Logical/ink/effect bounds, baselines, center/east/west anchors | Rich arbitrary geometry queries |
| Style | One fully art-directed editorial pack plus a small blueprint variation | General selector cascades and style-pack ecosystem |
| Materials | Seeded paper, ink, hatch, halftone, grid; declared local coordinates | Shader graphs, animated fields, physically based materials |
| Time | Cue table, finite tween, delay/parallel/sequence/stagger, arbitrary seek | Audio, tempo maps, infinite patterns, stateful simulation |
| Inspection | ID lookup, bounds/anchor overlay, one property-source trace | Scene database, natural-language intent explanations |
| Runtime | Current-frame rendering, bounded latest-wins admission, last-valid revision | General fine-grained reactive engine and distributed rendering |
| Output | Canonical PNG/contact sheet, six-second silent MP4, manifest | Extra raster backends and print/PDF guarantees |

The blueprint variation should be small enough not to double the project: palette,
font-role/spacing decisions, grid/line treatment, and one intentional texture
change. Both versions must be visually reviewed. If only one reaches the quality
bar, keep the other explicitly experimental rather than claiming arbitrary styles.

## 4. Build order within A1

### A1.1 measurable card

Port one editorial card through an options-map component. Add canonical text
measurement and wrapping, logical/ink/effect bounds, and explicit overflow.
Preserve the existing packaged fonts and raster backend. Render a still with a
short and a long caption, with no manual repositioning between the two.

The critical technical spike is a trustworthy measurement interface consistent
with canonical shaping. If librsvg's internal shaping cannot expose the required
metrics, investigate a narrow Pango measurement worker or resolved glyph-run
boundary. Do not estimate text width from character count. Prove the boundary
on a few demanding specimens before extending the API.

### A1.2 composition and identity

Generate the three cards from records, give instances stable keys, and arrange
them under a declared logical viewport. Resolve simple connectors from anchors
once nodes are placed. Insert a card and reorder existing cards; the old semantic
IDs and their seeded material choices must survive.

### A1.3 motion and selected-frame preview

Add a cue table and finite sampled motion. The entrance is presentation motion
over reserved layout boxes. Request one timestamp on edit or scrub; do not block
the preview on full-film export. Reuse static fonts/materials and use coarse safe
invalidation before inventing a general reactive runtime.

The preview shell retains bounded admission and coherent publication. Keep one
active rendering operation and one latest pending request initially. Changed
code must be captured coherently; a short source hash alone is not a complete
executable-capture design. Use existing BL ownership mechanisms and review the
load-before-capture and concurrent-publisher gaps called out in PROGRESS.md.

### A1.4 inspection and play session

Add selection by stable ID, bounds/anchor overlays, and a small property-source
trace. Put caption, theme, seed, and cue edits through real preview refreshes.
Record where authoring feels repetitive, where a property is surprising, and
which operations are still too slow. This feedback should revise the plan.

### A1.5 export and evidence

Export six seconds at 24/1 fps: exactly 144 frames, logical/raster output 1080
square for the quality edition. Use the same captured scene meaning as preview.
Verify frame count/duration and selected canonical frames, inspect the stills
at useful scale, and inspect motion samples. Retain a concise manifest and
measurements. Stop every owned worker/compiler scope afterward.

These are implementation slices, not five independent product milestones.
Keep a viewable composition available as each slice lands.

## 5. Acceptance and review gates

| Gate | Concrete evidence |
|---|---|
| Content adapts | Short/long captions wrap; card height and connected anchors update without hand-edited coordinates; overflow has an explicit diagnostic |
| Composition is reusable | The same function generates all cards from data; insertion/reorder preserves existing semantic IDs and material variation |
| Style is coherent | Editorial output meets the retained keyframe's type/material/edge standard; blueprint variation uses the same semantic content and is separately visually reviewed |
| Time is sampleable | Evaluate timestamps in shuffled order and compare normalized scenes; zero-duration/boundary behavior is tested |
| Preview is selective | One requested frame can be produced without rendering all 144; rapid scrubbing coalesces; old results cannot replace the newest requested state |
| Edits are coherent | Invalid edits preserve the old valid frame and show diagnostics; accepted edits publish one revision; concurrent publication cannot mix revisions |
| Inspector is useful | Select a title, see bounds/baseline/anchors, and explain its resolved font or color with the originating role/rule |
| Export is coherent | ffprobe reports 144 frames and six seconds; keyframe PNGs match the same canonical sampling path; source changes during export cannot alter the admitted revision |
| Ownership is closed | Closing during work drains owned server, compiler scopes, raster workers, and encoders; unrelated services remain untouched |

Correctness alone is insufficient. Review actual typography, whitespace, card
hierarchy, edge quality, grain scale, clipping, and motion pacing. A contact sheet
cannot establish all of these. The user should be able to reject an aesthetically
weak result even if the structural checks pass.

## 6. Responsiveness targets

These are proposed product targets to measure and refine, not current results:

- Show the last valid frame immediately while an edit is being evaluated.
- Target warm edit-to-current-frame p50 at or below one second and p95 at or below
  two seconds for the 540px preview on the named development host.
- Use the unchanged 1080-square logical layout at every preview raster scale.
- Admit only the latest pending scrub request; expose the selected quality and
  pending state rather than showing an apparently final stale frame.
- A high-quality still or full export may take longer and must not block controls.

Measure first preview, text edit, accent edit, cue edit, arbitrary seek, and full
export separately. Record sample count, distribution, backend, font/assets,
quality, hardware, resource peaks, and whether caches were warm. Current editorial
full-film evidence is roughly four minutes for four seconds of 2× offline work;
that is not an interactive-preview result. Measure on-demand work before choosing
a new backend or claiming the cache solves latency.

If targets are missed, preserve the measurements, identify the stage, and propose
a scope/implementation adjustment for review. Do not silently change logical
layout, remove texture, or relabel an offline operation as interactive to pass.

## 7. How to have fun with it

### Session one: a postcard about anything

Choose three nouns: `idea → experiment → discovery`, `seed → forest → weather`,
or `coffee → code → tiny universe`. Write a title and one sentence per card.
Keep the content personal. Render a still, then watch the cards introduce
one another. This exercises composition without needing a full explainer script.

Change a caption from three words to twenty. The visual should adapt or explain
why it cannot fit. This is a playful stress test of typography and layout, not
an invitation to shrink every font until the picture technically fits.

### Session two: art director mode

Switch warm paper to blueprint. Adjust the accent, grain strength, and shadow
depth individually. Ask whether the same idea now has a different voice while
remaining readable. Change the seed: only the declared procedural details should
change, not the content or scene structure.

Keep before/after frames. Record the two or three controls that made the biggest
visual difference. These are candidates for the public style surface; controls
that need constant coordinated repair may belong behind a higher-level choice.

### Session three: choreography mode

Move the explanation cue, change stagger spacing, and change a rise to a fade.
Seek backward to the middle of an entrance. Repeatedly switch between distant
frames. The image at a fixed time should remain the same regardless of how you
got there. Listen to the visual rhythm even though the film is initially silent.

A later playful extension could map a beat pattern to entrances, but the first
session needs only a cue and finite clips.

### Session four: a little visual debugging game

Select a label and ask where its font came from. Turn on anchors and stretch a
caption. Watch the connector follow. Deliberately use a missing anchor or font
and read the diagnostic. Fix it and confirm the old selected object still exists.

If the inspector requires reverse-engineering pixels, or a simple error erases the
scene, the model has not yet delivered the promised inspectability.

### Session five: procedural remix

Insert a fourth keyed card, reorder the originals, and switch the layout from a
column to a row under a suitable viewport. A width diagnostic is a useful result
if the chosen cards cannot fit; silent overlap is not. Keep the old card IDs and
their seeded appearance. This is the smallest test of the Houdini-inspired
procedural direction and the USD-inspired identity distinctions.

## 8. Questions that should improve the plan

After a short play session, answer these from actual use:

1. Did you enjoy arranging a picture, shaping text, choosing a material, or timing
   an entrance most? The next example should emphasize that activity.
2. Which change forced you to touch code that felt unrelated?
3. Were constraints and measurements understandable, or did layout feel magical?
4. Was it easy to tell a style default from a local override?
5. Did you want absolute placement, anchors, or row/column layout at each point?
6. Was waiting for a preview the main problem, or was deciding what to change?
7. Did any abstraction save lines while hiding an important visual decision?
8. Would you rather make a chart, a branching diagram, a kinetic poem, or a
   procedural illustration next?

The answers can change names, options, defaults, and the next milestone. The
contract's determinism, resource ownership, and coherent revision requirements
should not depend on a particular aesthetic preference.

## 9. What can be tried today

The new A1 authoring surface is not implemented yet. The retained editorial
[MP4](evidence/editorial/field-notes.mp4) and
[lossless frame](evidence/editorial/frame-060.png) can be viewed now. Existing
prototype source can already be edited through
[the editorial entrypoint](../../../examples/scene-renderer/editorial.bl) and
[its documented commands](../../../examples/scene-renderer/README.md#art-directed-edition).
That path still uses manual layout and offline rasterization; do not mistake it
for the proposed studio.

No services need to be launched to review this research or its retained artifacts.
For implementation checks, inspect `scripts/bl-mem`, use checkout `./bin/bl`, run
focused checks serially under a cgroup cap, use private runtime ownership for test
services, and stop them explicitly. The separately scoped compiler cleanup lesson
from PROGRESS.md remains relevant.

## 10. After A1

A2 should be chosen from actual friction, likely one of:

- A data-driven chart with labels and changing values, to test data/layout/query
  boundaries.
- A richer connected diagram, to test anchors, attachments, component reuse, and
  controlled overrides.
- A kinetic poem, to test shaping, spans, line-breaking policy, and temporal rhythm.
- A procedural illustration, to test attributed geometry, material coordinates,
  stable variation, and richer effects.

Do not freeze a major API before several of these demanding compositions share
it comfortably. Defer general USD-style layers, a full incremental framework,
stateful simulation, audio tooling, extra backends, GPU kernels, and unrelated
Bend/compiler work until a measured project need justifies them.
