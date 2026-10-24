# Scene renderer session handoff

You are the new Codex session for the Beam Lisp scene renderer and live preview.
Work only in `/home/othman/code/undefine/beam-lisp--scene-renderer` on branch
`feat/scene-renderer-preview`. The base research commit is `a1da65fc`.

## User intent

The user explicitly separated two projects: (1) a useful scene renderer and its
preview loop; (2) outperforming Bend in compute, proofs, and agent workflows.
This session owns the first project. The second remains independent research;
do not make renderer delivery depend on general native lowering, GPU support,
or a new proof system.

Read root AGENTS.md and any applicable narrower instructions first, then:

- research/scene-renderer-and-bend/README.md
- research/scene-renderer-and-bend/scene-renderer/VIDEO.md
- research/scene-renderer-and-bend/scene-renderer/DESIGN.md
- research/scene-renderer-and-bend/SOURCES.md
- research/scene-renderer-and-bend/WORKTREE.md

## Implementation direction when the user continues

Proceed with R0: audit existing BL graphics, JS, browser/desktop integration and
scenario.film. Choose one practical graphics backend and produce a reproducible,
inspectable BL-authored frame with text, shapes, transforms, and clipping.
Keep authoring, scene construction, revision management, and orchestration in BL.
Reuse graphics mechanisms rather than rewriting the runtime to get the first
frame. Document the actual backend contribution honestly.

Then implement the deterministic scene core, a short multi-scene animation,
live seek/step/play preview, coherent revision refresh, and offline export, in
that order. Use the detailed milestones and acceptance conditions in DESIGN.md.
Select routine implementation choices autonomously and make tangible progress.

Scene evaluation must be deterministic for revision, timestamp, assets and seed.
Use stable object identities and explicit display ordering. Keep previews and
exports tied to coherent revisions; old render results must not overwrite newer
requests. Use bounded queues and packed pixel buffers. Preserve the last valid
preview after an invalid edit. Keep text/font policy and colour/alpha semantics
explicit. Do not silently omit unsupported objects.

No source for the original Bend renderer was located. The video was inspected
through sampled frames; the proposed architecture is an inference, not a source
audit or a verified performance comparison. Create original demonstration art.

## Repository and resource boundaries

The source execution-protocol worktree has unrelated uncommitted runtime/AOT
work. It was intentionally not copied into this branch. Do not modify, commit,
reset, or import those changes implicitly. Check this worktree's status before
editing and preserve any changes made here by the user.

Use ./bin/bl from this checkout. Inspect scripts/bl-mem before starting BEAM
processes, reuse a warm VM where possible, run focused tests, and cap heavy runs
as root AGENTS.md requires. Stop all preview servers, VMs, workers, and encoders
you launch for checks. Do not assume a timeout physically cancels native work.

Keep verification proportional and meaningful: time boundaries, deterministic
seeking, stale-result suppression, revision isolation, export frame count,
visual correctness, and cleanup. Preserve evidence of actual results and label
proposals or limitations. Do not claim performance superiority without a matched
measurement. Do not spawn sub-agents unless the user explicitly requests them.

## Initial session bootstrap

For the initial bootstrap turn, read the instructions and research, confirm the
working directory and branch, and summarize the first concrete implementation
step. Do not begin implementation or launch services yet: the user is moving
into this fresh session to continue the work. End ready for their next message.

## Implementation continuation

The user superseded the initial bootstrap pause and authorized autonomous renderer
implementation. See `PROGRESS.md`, `examples/scene-renderer/README.md` and the
retained `evidence/` for the implemented R0–R3 vertical slice and initial R4 checks.
Do not repeat the bootstrap pause. The next useful work is on-demand preview and
stronger snapshot/publisher identity, with the remaining limitations in PROGRESS.md.

The user subsequently rejected the visual quality of the first demo. The newer
art-directed entrypoint is `examples/scene-renderer/editorial.bl`, using
`scene.atelier`, `scene.material` and packaged fonts. Read `ART-DIRECTION.md`.
Do not present the earlier plain demo as the current visual target. The user
explicitly wants expressive Lisp abstractions and visual excellence, not merely
pipeline acceptance. Keep using actual rendered visual checks.

## API research and proposed first authoring milestone

The user requested a durable written record of every API inspiration, sources,
code examples, semantics, and a first milestone to review and play with. Read
`README.md`, `API-RESEARCH.md`, `API-CONTRACT.md`, `API-EXAMPLES.bl.md`,
`API-SOURCES.md`, and `API-MVP.md`. They preserve the conversational proposals and
expand their rationale, risks, boundaries, and acceptance conditions. A1 is the
proposed living postcard studio: measurable components, wrapped semantic text,
stable keyed cards/anchors, cue-relative motion, selected-frame preview, and a
small inspector. The user wants to refine the plan through playful experiments.
These documents do not implement A1 or turn the illustrative syntax into a
working public API. Preserve the distinction between existing prototype behavior
and proposed design. The renderer remains separate from Bend/compiler research.

## Autonomous A1 implementation

The user agreed to the plan and explicitly authorized autonomous work and commits
as implementation proceeds. The measurable text/layout slice and selected-frame
studio now exist; read the latest PROGRESS.md and `priv/lib/scene/README.md` before
assuming an API is only proposed or fully delivered. Existing code uses canonical
Pango shaping plus Cairo vector outlines, and a BL-owned task coordinates the
studio. Source hot replacement and full source-form explanations remain open.
Keep making concrete, visually checked progress and commit completed slices.

## Two-track continuation

The user approved separating studio workflow from visual/clip-language development.
Read TRACKS.md. Visual capabilities should progress through standalone authored
films, then the studio adopts their inputs/inspection. The next approved study is
a twelve-second illustrated transformation with clip clocks, path drawing,
geometric reveals, camera movement, and procedural botanical composition. Continue
autonomously and commit completed slices; do not spawn sub-agents.
