# Scene authoring library

The first A1 authoring slice adds real measurable text and composable layout.
The original `scene.core`, `scene.material`, and `scene.atelier` APIs remain usable.
The broader proposed API is documented under
`research/scene-renderer-and-bend/scene-renderer/`; only the behavior below is
implemented by these modules.

## Canonical text

`scene.text/block` and `scene.text/paragraph` take an options map and a string.
Text needs a local `:id`; a `:role` resolves defaults from the explicitly selected
style. `paragraph` wraps to its propagated content width. `block` is unwrapped
and reports width overflow. The initial type overrides are `:family`, `:size`,
`:line-height`, `:weight`, and `:italic`.

`text/measure!` batches shaping requests through `text_worker.py`. Pango produces
logical/ink extents and baselines; Cairo extracts vector outlines from that very
same shaped layout. These outlines are rendered as paths, so preview/export
cannot silently reshape the measured paragraph through a different text engine.
No Python packages or system font fallback are required. The four packaged font
files and shared Pango/Cairo libraries are required. The worker uses the selected
`rsvg-convert` dependency closure where available; `SCENE_*_LIBRARY` can override
library discovery. Backend paths/versions and font hashes accompany the result.

The initial examples use the packaged Latin type set. Missing glyphs, unknown
font families, invalid paragraph dimensions, and unsupported content produce
diagnostics. This is not a comprehensive multilingual typography guarantee.
Text is shaped with raster-independent hint metrics and absolute logical sizes.

## Components and layout

`scene.styles.editorial/cutout` is an options-map card constructor. It accepts
content, width, padding, optional maximum height, structured transform operations,
and an optional grain resource name. It expands to paper, ink edges, a shadow,
and its measured content. The grain resource must be defined by the containing
scene. `warm` and `blueprint` are explicit style values, not mutable global state.

`scene.layout` supplies `column`, `row`, `overlay`, and `padding`. Row cells share
the available width unless a child explicitly declares its width. Oversized rows
and exceeded `:max-height` constraints are diagnosed. Explicit width includes
padding. `requests` propagates width constraints and collects text for one shaping
batch; `evaluate` turns authored nodes plus shaped runs into an evaluated tree.

`scene.picture` supplies group, rect, circle, and structured-path nodes. Paths
require explicit conservative bounds in this first slice. `scene.geometry`
defines structured path validation, affine matrices, bounds, and operation order:
listed transform operations apply in listed order. Source shapes currently admit
finite geometry and basic fill/stroke; a general effects API remains future work.

Each evaluated node carries logical, ink, and conservative effect bounds, anchors,
local transform, and semantic identity. Card shadows extend effect bounds without
changing logical layout height. Anonymous layout wrappers preserve descendant
semantic IDs. `layout/index` resolves world coordinates for addressable objects.
Explicit local child IDs are scoped by component instances, not collection order.

## Inspection and motion

`scene.inspect/object`, `bounds`, and `explain` work over the index. The first
explanation records the source of a font or color: an explicit local setting or
a style/role. It does not yet provide arbitrary source-form dependency traces.
`overlay` draws logical/ink/effect bounds and anchors for one selected object.

`scene.motion/enter` attaches finite cue-relative rise/fade parameters to an
authored node. `sample` applies them to an evaluated tree at any time; it never
mutates the base tree or replays previous frames. `tween` has finite validation,
clamped endpoints, and explicit zero-duration behavior.

`scene.clip` adds temporal composition independently of layout. `clip` takes
`{:id "local-name" :duration seconds :cues {"name" seconds}}` and data content.
`sequence` derives duration by summing children; `parallel` takes the maximum
unless an explicit longer duration reserves a trailing gap. `delay` adds `:by`
seconds; `retime` gives a positive-duration child a new positive `:duration`.
All combinators take options first and an ordered child vector (or one child).
Sibling IDs are unique local string names without slashes. `schedule` returns
serializable leaf intervals, scoped cues, and local-clock rates; `sample` returns
active leaves with local time. Activity is half-open, zero-duration leaves are
inactive, and outside the schedule sampling returns no active content. Sampling
does not invoke content functions or perform side effects. Empty tail intervals
do not implicitly hold a picture: author an explicit content clip for a hold.
Property blending, generalized signals, repeat, event tracks, and simulation
remain open. The growth study demonstrates scheduling and retiming.

## Camera-led composition

`scene.camera/track` takes a nonempty ordered vector of segments with unique
`:id`, positive `:duration`, and matching `:from`/`:to` poses. A pose declares
`:center [x y]`, positive `:zoom` (up to 64), and optional `:roll` in degrees.
Optional `:controls [point point]` defines a cubic spatial path. `:pullback`
(0–1) gives a temporary logarithmic widening during travel. Segment starts and
total duration are derived; discontinuous endpoint poses are rejected.

`sample` is an arbitrary-time pure query, holding endpoint poses outside the
track. Timing is quintic with zero endpoint velocity/acceleration; zoom is
logarithmic. `matrix` maps world coordinates into a declared positive viewport,
placing the sampled center at its midpoint. No objects are hidden, introduced,
or removed by a camera track. This is a deterministic editorial path, not a
stateful physical-camera simulator. Roll is explicit, without angle-wrap guessing.

The atlas presentation is a camera-only example. Its graphics worker captures a
static world at two pixels per world unit and resamples through the BL matrices
with Cairo BEST filtering. The finite raster density is a declared quality limit;
this route does not promise arbitrary-zoom vector equivalence. Selected lossless
frames and streamed video use the same packed-surface sampler. Python does not
plan the camera or author the world.

## Persistent transformations

`scene.choreo/formation` validates an ordered vector of keyed nodes with `:id`,
`:at [x y]`, `:angle` degrees, positive `:scale`, and optional `:parent` identity.
`morph` takes source/target formations and progress in [0,1]. Correspondence follows
IDs rather than collection indices; paint order follows the source. Position is
linear, scale logarithmic, and angle follows the shortest turn (a 180° tie takes
the negative direction). Attachment endpoints travel between the source and target
parent positions; this is an explicit relationship morph, not a constraint solver.
No opacity/visibility channel is supplied. Unresolved parents and missing keyed
correspondence fail. `progress` supplies finite quintic timing, and `follow`
blends a camera's focus between points resolved from named objects.

`path-morph` interpolates structured commands with matching operators/arity. The
author supplies contour correspondence. It does not infer arbitrary shape topology,
repair self-intersections, or promise tight bounds. Ordinary component functions
can combine these operators with the existing geometry, timing, and camera values.

The metamorphosis film uses 48 persistent nodes: radial, branching, ribbon, and
orbital formations, with a changing seed contour and camera focus on actual
instances. Its graphics worker caches native vector paths instead of flattening
the complete world to a raster atlas, preserving deep-zoom edge quality. Paper is
a cached, world-local repeating raster material. Hatching and label halos are
explicit backend styles. PNG/video share the same packed native sampler.

## Verification and resource ownership

Focused BL tests are in `test/bl/scene/layout_test.bl`. Real shaping tests are in
`test/scripts/scene_text.py`. Use checkout `./bin/bl`, inspect `scripts/bl-mem`,
and cap the test process tree as root AGENTS.md requires. Run checks serially.
Shaping is a bounded synchronous batch process, not a persistent test service.
The postcard example is a selected-frame build; full-film export is independent.
