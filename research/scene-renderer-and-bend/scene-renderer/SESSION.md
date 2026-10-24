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
