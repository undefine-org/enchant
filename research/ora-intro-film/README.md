# ORA Ventures — intro film

A visually led company intro for ORA Ventures (AI infrastructure for established
businesses, Casablanca), built on the Beam Lisp scene studio. The narrative is
carried by picture and sound. The only copy is the closing "ORA Ventures".

| Read | What it is |
|---|---|
| [RESEARCH.md](RESEARCH.md) | What the ORA site says, its brand system, what the studio can carry, visual principles |
| [BRIEF.md](BRIEF.md) | **The Common Block**: 45 s, 8-shot brief with action, camera, meaning, sound, transitions, gates, deliverables |
| [storyboard/index.html](storyboard/index.html) | Timed visual storyboard (serve the folder over HTTP; `?contact=1` for a contact sheet) |
| [proof/](proof/README.md) | **Rendered** shot 03 / website "Layers assembling" loop: 15 s 1080p60 with sound |
| [DIRECTIONS.md](DIRECTIONS.md) | Two alternative directions, **Zellige** and **Crease**, compared with a recommendation |

The source was the ORA Ventures website mockup v2 (October 2026),
`ORA Ventures Website.html` at the repository root. It is not copied here.

Rebuild the boards with `python3 research/ora-intro-film/storyboard/build.py`.
Rebuild the proof with `proof/render.sh` (see its README).
