# ORA Ventures intro film — research

Sources: the ORA Ventures website mockup (`ORA Ventures Website.html`, "Mockup v2 ·
English · October 2026"), read in full and screenshotted section by section in
headless Chromium on 2026-10-25. The scene-studio work in
`research/scene-renderer-and-bend/scene-renderer/` (MAKE WORLDS, Hello world).

## What ORA Ventures says about itself

| Site section | Claim | What the film must make visible |
|---|---|---|
| Hero | "We build your AI infrastructure." Advisory · Engineering · Products. Casablanca; projects in French and English. | A builder of foundations, not a chatbot vendor. Rooted in Casablanca. |
| The company of tomorrow | Teams already use AI, each person with their own tools, instructions and habits. Gains are real but individual, uneven, hard to govern. Next step is organisational: AI managed like finance or IT. | Many private, unsynchronised AI uses → one governed shared layer. |
| Four transitions | Personal assistants → shared company layer. Knowledge in chats → one governed source. Quality depends on user → company standards. Data leaving unnoticed → data kept where you decide. | Four before/after states, each needs its own visual signal. |
| Two ways to use AI | "The difference is in the foundations." Efficiency gauges: fragmented ≈ 0 %, sometimes negative; shared > 100 %. Gauge colours: red < 0, amber < 50 %, grey < 100 %, green above. | Efficiency as rising light levels using the site's own colour code. The values are illustrative on the site, so the film must not show numbers. |
| Five ways we work | Assess → Train → Connect → Build → Host & operate. | Out of scope for a 45 s intro. Belongs on the page. |
| Five layers | Teams / Assistants and agents / **Playbooks and optimisers** (highlighted) / Connected tools / Data foundation. "The company layer in the middle carries your know-how." | The physical metaphor: a stack with a privileged, glowing middle block. |
| Built to be trusted | Data stays yours · every answer has a source · people keep the decision · no lock-in. | Physical rules: threads that return, threads to sources, a hand on the output. |
| Products | Knowledger (law firms, shared memory), Blueprint (manufacturing, production plan), Backdesk (hospitality, guest service and staff). | Three building silhouettes on the same foundation. |
| Funding | EBRD-referenced consultant. | Not in the film (a claim, not a visual). |

The site already reserves two animation slots:

- **"The common block"**: efficiency gauges, about 60 s, looping, silent. The 'Two ways' placeholder shows five assistants on each side. On the fragmented side each is unlinked. On the shared side all five link to "Playbooks + optimisers".
- **"Layers assembling"**: about 15 s. "The five layers drop into place from the bottom up. Coral lines then run from the playbooks layer to each team."

The intro film can **feed both slots** as cut-downs of the same evaluated scenes.
That is a concrete production argument for building it on the scene studio.

## Brand system (measured from the page CSS)

| Token | Light page | Hero / dark |
|---|---|---|
| navy | `#1B2D4F` | hero background `#121C30` |
| cream | — | `#FBEACE` (hero ink) |
| coral | `#D9533F` | `#F07A66` |
| good / warn / bad | `#2E8B57` / `#C4862A` / `#EE6A5E` | `#4CBF7E` / `#E0A54A` / `#EE6A5E` |
| line | `#DEDBD2` | `#263044` |

The site uses three typefaces: Schibsted Grotesk for display, Source Serif 4 for body text and IBM Plex Mono for labels. A 48 px square grid sits behind the hero. Coral is the only saturated accent and marks the company layer. **Storyboard boards substitute DM Sans** because the site fonts are not yet packaged in this repo. The film lockup must use Schibsted Grotesk; package it with its OFL licence before production, as was done for Nunito.

## What the studio can carry today

Tested in this folder's proof (see `proof/README.md`):

- BL authors every per-frame value: camera, box transforms, materials, glow, floor shock, motes and sound events. Each is a pure function of time. The seek-history assertion passed.
- A native EGL/GLES worker (Intel UHD 630, Mesa 26.1.1) draws 4× MSAA RGBA16F scenes with depth, procedural engraved materials, additive motes, bloom and an ACES-like tone curve.
- 15 s of 1080p60 plus original AAC stereo render and encode in about 46 s at an 879 MiB peak.

From MAKE WORLDS and Hello world: shaped type (Pango, rasterised once), warped type layers, deforming parametric surfaces, measured text layout, and Cairo vector display lists composited under GPU materials.

Not yet available, and needed by the full film:

- Instanced architecture (a tower of rooms).
- Simple figures.
- Thread/curve primitives that stay attached in 3D.
- Per-instance clocks for many orbs.
- A wordmark built from Schibsted Grotesk outlines in 3D.
- The top-down camera handoff to a flat grid.

None needs a new renderer architecture. All of it is authored geometry plus shader work on the proof's path.

## Visual principles derived from the brief

1. **State is colour + rhythm, never text.** Out of sync and multicoloured means fragmented. One pulse, cream and coral, means shared. Teach the code in one shot, then rely on it.
2. **The website is the set.** The film opens on the site's own grid and ends on it, so it hands straight off to the page.
3. **Coral means the company layer.** On the site it only marks the playbooks layer and the CTA. In the film coral is reserved for the common block and what flows from it.
4. **Gauge colours are levels, not decoration.** Red, amber, grey and green appear only as light-column heights inside rooms.
5. **Continuous camera, physical cause.** Every beat has a visible cause: a landing, a pulse, a thread. No fades between unrelated renders.
6. **One line of copy:** "ORA Ventures". Everything else is shown.
