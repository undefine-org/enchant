# Reconstructing the video

## What is visible

The inspected samples show a designed 2D explainer: coloured paper-like panels,
hand-drawn-looking outlines, text, diagrams, a grid-based game, terminal panels,
bar charts, and a small branching computation tree. Subtitles run underneath.
The narrative moves from rules in AGENTS.md to enforceable laws, a wrapping-board
change that violates a rule, a corrected board, and then types and computation.
These are observations from frames, not a complete transcript.

The game-board example communicates a temporal property: after any sequence of
allowed moves, the winning state remains unreachable. A single frame of a wall
is not evidence for that property. A scene illustrates the argument; the actual
program and its checked proof would supply evidence for it.

One visible chart labels Game of Life with 6.8 seconds for C and 7.8 seconds for
Bend on an Apple M4 Max. That is a figure depicted by the video, not a benchmark
we ran. It should not be reused as a measured result without locating its source,
versions, exact workload, and measurement procedure.

## Likely construction

A useful reconstruction separates five jobs:

1. An editorial script chooses scenes, text, colours, and explanatory pacing.
2. A timeline maps a timestamp to active scenes and transition parameters.
3. Scene functions produce positioned drawing objects.
4. A graphics backend rasterizes those objects into pixels.
5. An export stage combines frames and audio into the deliverable video.

Examples of inexpensive, expressive building blocks are rectangles, circles,
lines, polygonal arrows, glyph runs, clipping, alpha compositing, transforms,
and smooth interpolation. A seeded perturbation of paths can create sketchy
outlines. A seeded texture field can create paper or print grain. Neither effect
requires generative imagery or a path tracer.

This explains how an agent could create the observed style with ordinary code.
It does not establish the original implementation. Alternative mechanisms
include precomputed vector paths, embedded bitmaps, or generated font outlines.
The presence of text does not tell us how glyphs were rasterized.

Bend's documented image model offers one possible route, but there is no basis
to assert that this renderer used it. Likewise, pixel independence makes some
stages parallelizable; it does not establish that the author used a GPU.

## Why the result is reproducible in BL

The scene model mostly manipulates structured values and time. BL can express
that authoring layer directly. A graphics backend can execute drawing commands
without making a BEAM term for every pixel. The authoring language and pixel
execution backend should therefore be assessed separately.

There are at least three legitimate implementations:

- BL authors scenes and emits SVG for an existing rasterizer.
- BL authors scenes and emits a display list consumed by a Canvas/native backend.
- BL authors scenes and compiles its own rasterization regions into native code.

The first two are useful delivery strategies. The third is a language/compiler
research project. Record exactly which parts BL executes rather than conflating
all three under the phrase “rendered in BL.”

## Open questions about the original

We do not know the renderer source, font assets, encoding tool, frame rate,
render time, number of iterations, CPU/GPU use, audio production, or whether
scene functions were pure. We also do not know whether illustrative code on
screen was compiled and checked. Those uncertainties do not prevent building
our own renderer, but they prevent a direct performance comparison today.

The useful target is an independently authored explainer of comparable visual
complexity, accompanied by an inspectable pipeline and timing evidence. Copying
the original artwork or soundtrack is unnecessary.
