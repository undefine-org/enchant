# Beam Lisp scene renderer research

Build an expressive, inspectable language for authored visual scenes and motion.
The visual standard is the newer editorial study, not the initial plumbing demo.
The renderer remains independent of the Bend comparison and compiler programme.

## Start here

| Read | Purpose |
|---|---|
| [Inspiration and API map](RESEARCH-MAP.md) | Complete research navigation, implemented/proposed crosswalk, and camera-led presentation brief |
| [Camera-led presentation](CAMERA-PRESENTATION.md) | Script, actual camera API, motion policy, graphics boundary, and verification |
| [Two implementation tracks](TRACKS.md) | Approved split: studio workflow and the advancing visual/clip language |
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

## A1 implementation continuation

The user approved the plan and authorized autonomous work and commits. The first
measurable-card and selected-frame studio slices are now implemented. See
[the actual library surface](../../../priv/lib/scene/README.md),
[studio commands](../../../examples/scene-renderer/README.md#living-postcard-studio),
[A1 evidence](evidence/a1/checks.json), and [PROGRESS.md](PROGRESS.md). The design
examples still describe a broader API; they are not all available signatures.

## Current implementation and retained artifacts

The current showcase is [MAKE WORLDS](evidence/showcase/index.html): a
[30-second 1080p/60 commercial study](evidence/showcase/showcase.mp4) with
continuous surface transformations, GPU materials, kinetic typography and an
original stereo score. [SHOWCASE.md](SHOWCASE.md) records actual mechanisms,
measurements and limits; [checks](evidence/showcase/checks.json) retain the evidence.

The earlier direction is [A living picture](evidence/metamorphosis/index.html):
a [48-second continuous transformation](evidence/metamorphosis/experience.mp4)
of one keyed system, with contour/formation/relationship morphs and deep camera
following. [TRANSFORMATION-EXPERIENCE.md](TRANSFORMATION-EXPERIENCE.md) records the
user's correction away from slides and the actual new API. [Evidence](evidence/metamorphosis/checks.json)
includes the full compressed evaluated plan, media, and deterministic sample checks.

The earlier camera-only presentation is [The program is the sketchbook](evidence/atlas/index.html):
a [56-second 1080p film](evidence/atlas/presentation.mp4) through six connected
ideas, with camera-only motion and persistent content. Its [checks](evidence/atlas/checks.json)
and [camera/script documentation](CAMERA-PRESENTATION.md) distinguish demonstrated
behavior from the open research programme. The full inspiration/API record is
indexed in [RESEARCH-MAP.md](RESEARCH-MAP.md).

The next visual-language study is the [twelve-second botanical film](evidence/growth/a-seed-of-possibility.mp4),
with a [review page](evidence/growth/index.html), [lossless master](evidence/growth/master-264.png),
and [checks](evidence/growth/checks.json). The studio now exports its accepted
edited postcard revision; [export evidence](evidence/studio-export/checks.json)
and [browser screenshot](evidence/studio-export/studio.png) record the first slice.
See TRACKS.md for what remains independently open in both tracks.

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
