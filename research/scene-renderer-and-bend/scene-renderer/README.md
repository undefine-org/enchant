# Beam Lisp scene renderer research

Build an expressive, inspectable language for authored visual scenes and motion.
The visual standard is the newer editorial study, not the initial plumbing demo.
The renderer remains independent of the Bend comparison and compiler programme.

## Start here

| Read | Purpose |
|---|---|
| [API research](API-RESEARCH.md) | Detailed inspirations, design practices, bolder connections, and decisions to preserve |
| [Proposed API contract](API-CONTRACT.md) | Value model, module boundaries, identity, layout, time, rendering, and extension rules |
| [API examples](API-EXAMPLES.bl.md) | Original conversational example plus proposed authoring, inspection, and experiment code |
| [First API milestone](API-MVP.md) | A small living-postcard studio, acceptance conditions, play sessions, and feedback questions |
| [API sources](API-SOURCES.md) | Primary references, what each establishes, what we borrow, and evidence boundaries |
| [Art direction](ART-DIRECTION.md) | Actual reference observations, the visual grammar, material caching, fonts, and sampling |
| [Implementation progress](PROGRESS.md) | Implemented behavior, checks, measurements, and outstanding limitations |
| [Original delivery design](DESIGN.md) | R0–R4 renderer milestones and preview/export requirements |
| [Video reconstruction](VIDEO.md) | What was observed in the inspiration video and what remains unknown |
| [Session handoff](SESSION.md) | Worktree boundaries, authorization, resource ownership, and continuation instructions |

The API research and examples are proposals dated 2026-10-24. They are not a
claim that the illustrative functions, inspector, or new studio already run.
Existing code is explicitly identified below and in the contract. The first API
milestone is A1, extending the existing R-series delivery rather than restarting it.

## Current implementation and retained artifacts

- [Authored editorial scene](../../../examples/scene-renderer/scene_demo/editorial.bl).
- [Editorial build entrypoint](../../../examples/scene-renderer/editorial.bl).
- [Atelier helpers](../../../priv/lib/scene/atelier.bl),
  [material values](../../../priv/lib/scene/material.bl), and
  [scene core](../../../priv/lib/scene/core.bl).
- [Commands and dependencies](../../../examples/scene-renderer/README.md).
- [Lossless editorial keyframe](evidence/editorial/frame-060.png).
- [Four-second editorial MP4](evidence/editorial/field-notes.mp4).
- [Export provenance](evidence/editorial/export-manifest.json) and
  [check results](evidence/editorial/checks.json).

The complete generated revision was written to `/tmp/bl-field-notes/`; it is
scratch output and can disappear. The source, fonts, research, and selected
artifacts above live in this worktree. Their presence does not imply they have
been committed. The original source video is referenced, not redistributed.
