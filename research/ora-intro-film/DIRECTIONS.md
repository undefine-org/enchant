# Two other directions

Both directions carry the same story as *The Common Block*. The story comes from the site:

1. Today everyone uses AI separately.
2. ORA puts a shared, governed layer underneath.
3. Output becomes consistent, improvements spread to everyone, data stays home.
4. There are products for specific sectors.
5. ORA Ventures.

What changes is the visual world, and with it who the film speaks to first.

## B — "Zellige"

> Superseded by the full film in [zellige/](zellige/BRIEF.md), rebuilt from scratch with a short spoken-free script.

**Idea:** Moroccan geometric tilework as the metaphor for a shared method. One
compass-and-straightedge construction (the playbook) generates a pattern that
every tile obeys. It is Casablanca-rooted without being a postcard. The point
is geometry and craft, not souvenir motifs.

**Look:**
- Macro ceramic: wet glaze, crazing, the slight wobble of hand-cut edges.
- The site palette, glazed: navy, cream and coral glazes on raw terracotta.
- Low raking light. Shallow depth of field faked with layered planes.

| # | Time | Picture | Meaning |
|---|---|---|---|
| 1 | 0–6 s | Extreme macro on a single coral glaze, pulling back. It's one loose tile on a workbench among dozens. Each tile is glazed differently, cut at a different angle, some chipped. | Everyone has their own AI, each one different. |
| 2 | 6–13 s | Hands (silhouettes) try to lay tiles side by side. Edges don't meet and gaps open. One tile cracks. Tiles slide off the table into the dark. | Uneven quality, lost knowledge, data leaving. |
| 3 | 13–20 s | Black. A compass point touches cream plaster. One circle, then a second, then the construction lines of an 8-pointed star, drawn in coral light at a confident beat-locked pace. | The playbook: one method, drawn once. |
| 4 | 20–27 s | The construction drops onto the scattered tiles. Each tile re-cuts and re-glazes to fit and clicks into the tessellation. Gaps close in a wave from the centre outwards. A glaze sheen sweeps across the finished panel. | Shared standards: consistent output, everyone fits. |
| 5 | 27–31 s | One tile at the edge gets a finer cut. The construction lines flash and every matching tile across the panel takes the refinement at once. | Optimisers share an improvement everywhere. |
| 6 | 31–37 s | Cross-section through the panel: strata of clay, slip, glaze, pattern and light. These are the five layers. A grout line glows coral back to the centre star. | Five layers; data held in the structure. |
| 7 | 37–42 s | The pattern grows beyond the panel across courtyard walls, floors and fountains. Three rooms in different patterns share the same central star: an archive, a workshop, a riad. | Products for sectors, one method underneath. |
| 8 | 42–45 s | Pull up top-down. The central star resolves into a coral ring: the O. "RA Ventures". | ORA is the method underneath. |

- **Strengths:** the most sensory and memorable of the three, and unmistakably local. It shows craft and rigour together. It uses the studio's strongest asset, procedural materials, and BL is well suited to geometric construction.
- **Risks:** cultural cliché if art-directed loosely, so it needs a real zellige reference pass (geometry and glaze, not tourism). Less literal about "AI": the first 6 s could be read as a ceramics brand until shot 3.
- **Production gates:**
  - Exact star construction as BL geometry.
  - Tessellation with stable tile identity.
  - Glaze, crazing and terracotta shaders.
  - A cross-section render.
  - About 2,000 tile instances.
- **Effort:** the highest of the three on materials, the lowest on architecture.

## C — "Crease"

**Idea:** company knowledge as a single sheet of paper whose fold pattern is the
playbook. A daylight, editorial counterpoint to the navy night of The Common Block.
It speaks to the professional-services audience (Knowledger) first.

**Look:**
- Warm off-white paper (the site's light page `#FAFAF7`) under soft window light.
- Crease lines in navy ink. Coral only for the master crease pattern.
- The studio's editorial paper and ink lineage, scaled up.

| # | Time | Picture | Meaning |
|---|---|---|---|
| 1 | 0–6 s | Top-down on a desk. Dozens of copies of the same printed procedure, each folded differently by a different hand: airplanes, crumpled balls, careful but wrong boxes. | Everyone has their own AI, their own instructions. |
| 2 | 6–12 s | The copies drift. Two collide and tear. One slides off the desk edge and out of frame. Their folded shapes can't stack. | Duplicated knowledge, uneven quality, data leaving. |
| 3 | 12–19 s | A fresh sheet lands flat. Coral crease lines draw themselves across it on the beat: a precise crease pattern. Embossed lines of text appear in its margins. | The playbook, written once. |
| 4 | 19–25 s | Every copy on the desk unfolds itself flat, picks up the coral crease pattern, then refolds in perfect unison into the same structure: a five-tier architectural fold. | Shared method: identical, reliable output. |
| 5 | 25–30 s | One fold gets a refinement. The change ripples through every structure on the desk at once. | Optimisers share improvement everywhere. |
| 6 | 30–36 s | Close up: each fold carries a fine thread back to the paragraph it came from. A fingertip touches a fold before it lifts away. The desk edge is now a raised lip, and nothing slides off any more. | Sources cited · people decide · data stays put. |
| 7 | 36–41 s | Pull back. The folded structures grow into three paper architectures: a stack of bound folios, a sawtooth factory roof, a courtyard of balconies. | Knowledger, Blueprint, Backdesk. |
| 8 | 41–45 s | Everything unfolds flat at once. The overlapping crease patterns align into the site's square grid. The central fold collapses into a coral ring: the O. "RA Ventures". | ORA is the pattern underneath. |

- **Strengths:**
  - Calm, intelligent and very legible. Easy to understand muted.
  - Closest to the site's light sections (Services, Infrastructure, Products), so it doubles as page illustrations.
  - The cheapest to produce well: mostly flat geometry with folding transforms, paper shading and soft shadows.
- **Risks:**
  - Less "flabbergasting" spectacle per second than A or B.
  - Origami can feel twee if the folds are cute rather than architectural.
  - Folding needs real geometric correctness: rigid-panel folding on a defined crease graph, with no paper stretch.
- **Production gates:**
  - A rigid-fold solver for one crease pattern, which BL can author as an explicit, time-sampled fold-angle score.
  - Paper fibre and ink shading.
  - Contact shadows.
  - Thread primitives.
- **Effort:** the lowest overall. Its single technical risk is the folding.

## Comparison

| | A — The Common Block | B — Zellige | C — Crease |
|---|---|---|---|
| Mood | Night, architectural, cinematic | Sensory, crafted, warm | Daylight, editorial, precise |
| Speaks first to | Executives buying infrastructure | Brand and Moroccan market | Professional services |
| Most spectacular moment | Core slam + shockwave (rendered) | Tessellation snapping into place | Synchronised refold |
| Fit to the site's animation slots | Direct: both slots | Indirect | Partial: light sections |
| Literalness of "AI infrastructure" | High | Low | Medium |
| Main production risk | Architecture instancing, city shot | Cultural art direction, materials | Fold geometry |
| Already proven in the studio | Layers shot fully rendered | Materials (MAKE WORLDS) | Paper/ink (editorial study) |

**Recommendation:** lead with **A**. It maps one-to-one onto the site's story and
both of its animation slots, and its riskiest shot is already rendered. Borrow
from **B** for shot 07 (a zellige-patterned courtyard as the Backdesk building)
to root the city in Casablanca. Keep **C** as the style for still illustrations
in the light sections of the site.
