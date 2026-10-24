# Sources for the scene authoring API

Research date: 2026-10-24. This register covers the substantive inspirations and
references used in the API discussion and the expanded research package. Primary
documentation was inspected through the browsing tool; font asset/license bytes
were inspected in the worktree. Some repository pages were unavailable through
the browser; a separate
[retrieval manifest](evidence/api-source-manifest.json) records direct-fetch
hashes/status where available. Dynamic documentation can change after this date.
A hash identifies the fetched bytes, not a pinned upstream software release.

Our proposed API is an original synthesis. A source establishes its own mechanism;
it does not establish that BL already implements our adaptation, or that copying
that mechanism will guarantee visual quality or performance. Source descriptions
below are short paraphrases, not copied documentation. No benchmark claim is
borrowed from the references.

## Pict

| ID | Primary source | Reference fact and proposed use |
|---|---|---|
| P1 | [Pict overview](https://docs.racket-lang.org/pict/) | A functional picture library and a direct Lisp precedent for compositional authorship |
| P2 | [Pict datatype](https://docs.racket-lang.org/pict/Pict_Datatype.html) | Picture dimensions, baseline-related metrics, and embedded subpicture structure; informs measurable composition |
| P3 | [Basic constructors](https://docs.racket-lang.org/pict/Basic_Pict_Constructors.html) | Constructors include explicit dimensions and text/drawing concerns; informs primitive contracts |
| P4 | [Pict combiners](https://docs.racket-lang.org/pict/Pict_Combiners.html) and [finders](https://docs.racket-lang.org/pict/Pict_Finders.html) | Composition and subpicture location; informs alignment, anchors, and preserving useful structure |

The BL adaptation is in API-RESEARCH §2 and API-CONTRACT §§3–4. It does not adopt
Pict's drawing-context implementation or claim to reproduce its API.

## Typst

| ID | Primary source | Reference fact and proposed use |
|---|---|---|
| T1 | [Content](https://www.typst.app/docs/reference/foundations/content/) | Structured content elements/fields and scoped appearance mechanisms; informs semantic text and style roles |
| T2 | [Layout reference](https://typst.app/docs/reference/layout/) | Layout has its own vocabulary; informs separating author content from arrangement |

The proposed BL precedence order, overflow policy, measurement phases, and admitted
font/script subset are our decisions. No Typst runtime is required by this plan.

## Motion Canvas

| ID | Primary source | Reference fact and proposed use |
|---|---|---|
| M1 | [Signals](https://motioncanvas.io/docs/signals/) | Values can vary over time with dependent values updating; informs property relationships |
| M2 | [Animation flow](https://motioncanvas.io/docs/flow/) | Generator-based animation and composition helpers; informs ergonomic temporal composition |

Independent random-access evaluation is our required BL contract. The plan does
not claim Motion Canvas has exactly the same revision or sampling semantics.

## Houdini

| ID | Primary source | Reference fact and proposed use |
|---|---|---|
| H1 | [Geometry attributes](https://www.sidefx.com/docs/houdini/model/attributes.html) | Attributed geometry and inspection; stable `id` differs from element number, and rest coordinates can anchor procedural texture |

The BL plan borrows attributed procedural values, stable keys, coordinate-aware
materials, and inspection. It does not require Houdini or a node-graph editor.

## Musical patterns

| ID | Primary source | Reference fact and proposed use |
|---|---|---|
| U1 | [Strudel/Tidal pattern model](https://bournemouth.tidalcycles.org/technical-manual/patterns/) | A time-span query returns structured events with fractional time; informs a sampleable temporal algebra |

This is a project-authored technical-manual page on the Tidal domain, rather than
a claim that the exact page is the latest stable Strudel manual. Cues, clips,
scene events, and the proposed BL APIs are adaptations, not imported notation.

## OpenUSD

| ID | Primary source | Reference fact and proposed use |
|---|---|---|
| D1 | [Introduction to USD](https://openusd.org/dev/intro.html) | Scene composition through reusable descriptions, references, variants, layers, and overrides; informs modular artistic decisions |
| D2 | [Scenegraph instancing](https://openusd.org/dev/api/_usd__page__scenegraph_instancing.html) | Repeated scene content can share prototypes; informs distinguishing instance identity from shareable content |
| D3 | [AOUSD core specification overview](https://aousd.org/usd-core-specification/) | A formal data/composition boundary is useful context for long-term interchange and compatibility |

The first milestone deliberately uses a much smaller subset. No USD file format,
full composition precedence scheme, or 3D pipeline is proposed as an A1 dependency.

## Incremental queries

| ID | Primary source | Reference fact and proposed use |
|---|---|---|
| Q1 | [Salsa overview](https://salsa-rs.github.io/salsa/overview.html) | Deterministic derived work can be reused after input changes; informs dependency-aware resource/evaluation caching |
| Q2 | [Salsa algorithm](https://github.com/salsa-rs/salsa/blob/master/book/src/reference/algorithm.md) | Dependency/revision checks govern reuse; useful context for conservative invalidation |
| Q3 | [Salsa project](https://github.com/salsa-rs/salsa) | Project overview and scope of the query abstraction |

We are not proposing a Rust dependency or a compiler rewrite. BL's existing
execution/environment ownership must be reused where applicable. Resource cache
keys and a bounded preview coordinator can deliver value before general tracking.

## Vega

| ID | Primary source | Reference fact and proposed use |
|---|---|---|
| V1 | [Parser API](https://vega.github.io/vega/docs/api/parser/) | A declarative specification is translated into a runtime dataflow description; informs separating authoring from evaluation |
| V2 | [View API](https://vega.github.io/vega/docs/api/view/) | Runtime scenegraph/signals and output lifecycle are exposed; informs a queryable evaluated model |
| V3 | [Data model](https://vega.github.io/vega/docs/data/) | Structured records and transforms; supplementary context for data-driven authoring |
| V4 | [Reactive Vega paper](https://vis.mit.edu/pubs/reactive-vega.pdf) | Primary architecture paper by Satyanarayan, Russell, Hoffswell, and Heer; connects dataflow, visual construction, and interactions |

No performance result from the paper is adopted as a BL result. The proposed
property-source explanation, source provenance, and scene queries are our design.

## Graphics and art direction sources

These references were used in the earlier visual work and remain relevant to the
backend/material discussion. They are recorded here so the research is navigable
without reconstructing the conversation.

| ID | Source | Scope |
|---|---|---|
| G1 | [SVG filter turbulence](https://www.w3.org/TR/filter-effects-1/#feTurbulenceElement) | Procedural-noise primitive specification |
| G2 | [SVG filter composition](https://www.w3.org/TR/SVGFilter12/#feCompositeElement) | Pixel composition operations; an older specification, not a claim of current backend conformance |
| G3 | [librsvg turbulence implementation](https://gnome.pages.gitlab.gnome.org/librsvg/coverage/rsvg/src/filters/turbulence.rs.html) | Actual backend implementation evidence for the admitted primitive |
| F1 | [Instrument Serif](https://github.com/google/fonts/tree/main/ofl/instrumentserif) | Packaged font source and OFL license |
| F2 | [DM Sans](https://github.com/google/fonts/tree/main/ofl/dmsans) | Packaged font source and OFL license |
| F3 | [Patrick Hand](https://github.com/google/fonts/tree/main/ofl/patrickhand) | Packaged font source and OFL license |

Actual font bytes and licenses are in
[assets/fonts](../../../examples/scene-renderer/assets/fonts/). Export manifests
record the font hashes. [ART-DIRECTION.md](ART-DIRECTION.md) explains the shader,
texture-cache, supersampling, alpha, and typography choices actually exercised.

## Original video and the separate research programme

The original [Kevin Ngo post](https://x.com/kevin_t_ngo/status/2113663060888203642)
and [1080-square video](https://video.twimg.com/amplify_video/2113656958318460929/vid/avc1/1080x1080/GGVE8J5Mvf1E8noN.mp4?tag=29)
are the visual reference. X access failed in the browser; the
[FxTwitter endpoint](https://api.fxtwitter.com/status/2113663060888203642) supplied
post/media metadata. Full-resolution frames were inspected during implementation.
The original renderer source was not located. Its architecture is inferred from
visible artwork, not audited, and its reported Bend authorship is attributed to
the post.

[The parent source register](../SOURCES.md) and
[original source manifest](../evidence/source-manifest.json) retain the earlier
video/Bend/documentation references. Those sources and the comparison/compiler
programme are separate from the API milestone. Renderer delivery does not depend
on outperforming Bend, adding GPU compilation, or building a new proof system.

## Repository references and implementation status

| Evidence | Location | Meaning |
|---|---|---|
| Current low-level core | [scene/core.bl](../../../priv/lib/scene/core.bl) | Validation, time helpers, SVG serialization |
| Current materials | [scene/material.bl](../../../priv/lib/scene/material.bl) | Material values and SVG resource definitions |
| Current visual helpers | [scene/atelier.bl](../../../priv/lib/scene/atelier.bl) | Existing editorial composition helpers, not the full proposed API |
| Editorial scene | [editorial.bl](../../../examples/scene-renderer/scene_demo/editorial.bl) | BL-authored composition and sampled motion |
| Editorial builder | [build entrypoint](../../../examples/scene-renderer/editorial.bl) | Captured source/assets, frame generation, publication, export orchestration |
| Graphics boundary | [raster.py](../../../examples/scene-renderer/raster.py) | Material tile resolution, librsvg, reconstruction, FFmpeg, media checks |
| Revision/runtime constraints | [SESSION.md](SESSION.md), [PROGRESS.md](PROGRESS.md), and [root AGENTS.md](../../../AGENTS.md) | Existing limitations, authorization, resource caps, and cleanup lessons |
| Retained visual output | [editorial evidence](evidence/editorial/) | Actual frame, film, provenance, and check results |

Sources were inspected as design references. Other products were not installed,
benchmarked, or claimed to have APIs identical to the sketches here. Search-only
mirrors and third-party explanations were not used to establish technical claims.
The substantive sources from the conversation are covered above; incidental
search-result suggestions are not endorsements or implementation dependencies.

## Canonical text implementation references

The A1 measurement spike inspected these primary references on 2026-10-24:

- [Pango logical and ink extents](https://docs.gtk.org/Pango/method.Layout.get_extents.html):
  separate layout/ink rectangles in Pango units, with a layout-relative origin.
- [Pango wrapping width](https://docs.gtk.org/Pango/method.Layout.set_width.html):
  explicit line-wrapping width rather than character-count estimates.
- [PangoCairo layout outlines](https://docs.gtk.org/PangoCairo/func.layout_path.html):
  outline geometry can come from the same shaped layout used for measurement.
- [Cairo path ownership and iteration](https://www.cairographics.org/manual/cairo-Paths.html#cairo-copy-path):
  copy/inspect the vector path and release the owned native resource.

The worker records the installed library versions (Pango 1.57.1 and Cairo 1.18.4
in the retained run), rather than assuming the documentation site's newer version
is installed. Real outline/metrics tests and the admitted font set are described
in `priv/lib/scene/README.md`. These additions are implementation references after
the original 30-entry API inspiration retrieval manifest; that earlier manifest
remains a historical record rather than being silently relabeled as current.
