# Scene rendering and a measurable comparison with Bend

Research date: 2026-10-24. Status: research and implementation handoff, not a
claim that the proposed compiler or renderer already exists.

The starting point is Kevin Ngo's [Bend explainer video](https://x.com/kevin_t_ngo/status/2113663060888203642).
The user wants two independent projects: a BL scene renderer with a live preview
loop, and an evidence-based effort to outperform Bend across its claimed strengths.
This folder preserves the reasoning and separates their delivery criteria.

## Read in this order

1. [Evidence and source register](SOURCES.md): what was actually inspected,
   reproducible source identities, and what remains unknown.
2. [Video reconstruction](scene-renderer/VIDEO.md): observed visuals, likely
   construction, and the limits of the evidence.
3. [Renderer design and delivery](scene-renderer/DESIGN.md): a concrete authoring
   model, preview architecture, implementation sequence, and acceptance criteria.
4. [Comparison](bend-comparison/ASSESSMENT.md): advantages, gaps, and explanations.
5. [Compiler and proof programme](bend-comparison/ROADMAP.md): what must change
   to make stronger claims true.
6. [Evaluation protocol](bend-comparison/EVALUATION.md): how to determine wins,
   losses, unsupported cases, and regressions without moving the goalposts.
7. [Worktree handoff](WORKTREE.md): where implementation proceeds and what that
   branch inherits.

## The split is a dependency decision

| | Scene renderer and preview | Outperforming Bend |
|---|---|---|
| User outcome | Author, inspect, revise, and export a procedural film | Demonstrably stronger capabilities on declared workloads |
| Primary unit | Scene, timestamp, frame, revision, export | Contract, kernel, backend, benchmark, evidence |
| First deliverable | A deterministic short animation and working scrubber | A pinned comparison corpus and honest baseline |
| Can use existing graphics libraries? | Yes; identify their contribution | Yes, but classify library and language comparisons separately |
| Requires general native lowering? | No | Yes for a broad native-compute claim |
| Requires GPU support? | No for the first useful renderer | Yes to compete on GPU-language execution |
| Requires a new proof system? | No | Required contracts and broader proof coverage need dedicated work |
| Success | A useful creative tool with dependable output | Reproducible wins within explicit scope |

The renderer is a potential consumer of future compiler improvements. It must
not become hostage to them. Conversely, a pleasant animation editor does not
establish superiority in GPU throughput or mathematical proof checking.

## Working conclusions

BL has a compelling architecture for a living application that agents can
inspect and modify. Bend presents serious challenges in efficient numerical
execution and explicitly checked recursive proofs. These advantages concern
different tasks; neither language wins every axis by definition.

The strategy is to keep application state, authority, orchestration, and
inspection in BL, while compiling admitted numerical regions when profitable.
For correctness, distinguish optional analysis from required invariants: an
unknown result may decline an optimization, but must not satisfy a required law.

All APIs and milestones in the design documents are proposals unless explicitly
identified as present in source. No BL runtime, benchmark, or proof check was run
for this documentation task. Existing retained results are historical evidence.

## Independent follow-up research tracks

- [Logic: proof expressiveness, trust, and required-law enforcement](bend-comparison/logic/RESEARCH.md).
- [Compute: Mojo/MAX feasibility, ABI, lifecycle, licensing, and experiments](bend-comparison/compute/MOJO-MAX.md).

These are independent investigations. The logic follow-up corrects the initial
comparison: BL already supports inductive transition-system safety arguments.
The gap is broader structural proofs and uniform checked-law enforcement, not
the absence of induction altogether.
