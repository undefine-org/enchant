# Renderer worktree handoff

The documentation commit on `feat/enforced-execution-protocol` is the base for a
new branch `feat/scene-renderer-preview` and sibling worktree
`/home/othman/code/undefine/beam-lisp--scene-renderer`.

Create the worktree from the committed research revision. Existing uncommitted
runtime-image/AOT changes in the source worktree remain there; they are not
silently copied or included in the research commit. The renderer branch therefore
inherits the committed execution-protocol code and these research documents,
not unrelated working-directory edits. Reconcile any future dependency explicitly.

The immediate implementation task is R0 from [the design](scene-renderer/DESIGN.md):
audit existing graphics integration, select one practical backend, and produce
a BL-authored inspectable frame. Then progress through deterministic scenes,
preview, and export. Keep the Bend/compiler programme in its own track.

This handoff creates the workspace and records the authorized direction. It does
not claim the renderer has been implemented. This turn's deliverable is committed
research and the separate worktree, ready for that implementation.

Follow root AGENTS.md, inspect any narrower instructions, use checkout ./bin/bl,
inspect memory before launching VMs, and clean up all owned preview/runtime
processes. Documentation-only validation does not require starting a BEAM VM.
