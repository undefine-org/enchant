# From coverage to a visual language

The first pipeline demo was a functional test, not a satisfactory visual result.
The user explicitly asked to raise the visual standard and use Lisp abstractions
to express a coherent style. The new original study is `scene_demo/editorial.bl`.
It uses `scene.atelier` and `scene.material`, not a hand-authored SVG document.

## What the reference actually shows

The full 1080×1080 Kevin Ngo video was retrieved and sampled again. A close-up at
40 seconds shows cream paper, fine grain, pale blue grid lines, softly irregular
near-black outlines, simple offset shadows, a restrained red/green/blue/yellow
palette, and large handwritten captions. Other samples show hatching, halftones,
colour fields and deliberately simple diagrams. This is observed artwork. There
is still no original renderer source, so its implementation cannot be asserted.

The result is consistent with a 2D procedural compositor: structured shapes,
coverage masks, text glyphs, material fields, ordered alpha composition and a
frame clock. It does not require 3D light transport. It also does not tell us
whether the author evaluated custom pixels, used a graphics library, or combined
methods. The Bend authorship claim comes from the post, not a code audit.

## First principles and backend choice

A shape defines coverage at a sample. Its material defines colour and alpha.
Ordered layers combine with `C = alpha * foreground + (1-alpha) * background`
for straight-alpha foreground over an opaque background. Multiple spatial samples
estimate edge coverage; final reconstruction determines how fine detail survives.
Typography is glyph selection, shaping, placement and coverage, not a generic
"text" decoration. Those jobs need a policy at least as much as a graphics API.

SVG is a useful display-list interchange for this particular workload: curves,
glyphs, patterns, clips and affine transforms are its native vocabulary. It does
not choose the composition, the font, the stroke character or the texture scale.
The first attempt failed those design choices; that was not evidence of an SVG
quality ceiling. The retained editorial frame is an actual experiment in improving
them. A native Skia/Cairo or shader backend remains possible behind the same scene
values if measured rendering needs justify it. No superiority is assumed.

Relevant primary specifications:
- https://www.w3.org/TR/filter-effects-1/#feTurbulenceElement
- https://www.w3.org/TR/SVGFilter12/#feCompositeElement
- librsvg implementation: https://gnome.pages.gitlab.gnome.org/librsvg/coverage/rsvg/src/filters/turbulence.rs.html

## The Lisp vocabulary

Materials (`paper`, `halftone`, `hatch`, `grid`) are inspectable resource values.
`scene.atelier` composes them through `label`, `display`, `annotation`, `ink-line`,
`rough-box`, `cutout`, `arrow`, `reveal`, `drift` and `stagger`. These functions
return scene values and can be composed with ordinary map, for, functions and
higher-order helpers. Macros are not required to obtain this abstraction; introduce
syntax only when it improves authoring rather than hiding state or renderer work.

For example, a `cutout` expands to paper stock, a consistent ink edge, an offset
shadow and arbitrary content, under one transform and stable identity. A diagram
node combines a material, outline, glyph and caption. Animation changes a group's
transform or reveal parameter without changing the material seed or object IDs.
The renderer remains separate from this authored grammar.

The original study uses Instrument Serif (regular/italic), DM Sans, and Patrick
Hand, packaged with their SIL OFL licenses. Serif display type supplies a strong
editorial hierarchy; handwritten annotations explain the diagram; the small sans
labels supply a quiet technical register. The illustration uses overlapping
paper planes, graph lines, a halftone sun, hatching and seeded grain. It illustrates
BL scene composition, rather than copying the reference's game or proof claims.

## Sampling, texture and provenance

The canonical raster is evaluated at 2160 square then reconstructed to 1080 with
Lanczos. This preserves logical layout while improving small edge sampling.
Grain remains restrained and separate from the typography; it must not become a
blur layer across the entire output. The backend resolves each seeded paper
filter once into a transparent 512×512 texture tile, embeds the packed PNG in a
reusable SVG pattern, and uses the same material-local coordinates in every frame.
The texture tile is procedural backend output, not an AI-generated image or an
external paper photograph. Its cache key includes the resource parameters and
lowering version. Halftones, hatches, graph lines, type and geometry remain vectors.

BL owns authorship, evaluation, timing, IDs and orchestration. librsvg/Pango/Cairo
own glyph shaping and rasterization; the Python worker resolves immutable texture
resources and calls librsvg and FFmpeg. FFmpeg does reconstruction and encoding.
The high-quality video uses CRF 16 with browser-friendly yuv420p; the PNG is the
lossless master. Backend versions, sampling policy, source hashes, packaged font
hashes and seed are retained in the editorial export manifest.

The 512 tile policy is part of this backend's quality identity. It does not promise
pixel identity with uncached full-frame turbulence. The first direct and cached
frames were both visually inspected. Cached materials materially reduce repeated
filter work, without regenerating random texture as objects move.
