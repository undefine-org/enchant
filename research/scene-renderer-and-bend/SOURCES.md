# Evidence and sources

## Evidence discipline

Four categories are used throughout this folder:

- **Observed:** visible in downloaded video frames or directly inspected source.
- **Reported:** an author's assertion or retained measurement, not independently
  reproduced during this investigation.
- **Inferred:** an explanation consistent with observations, with alternatives.
- **Proposed:** a design or acceptance target for future implementation.

The original investigation sampled video frames across the full duration. It
did not transcribe or independently verify the soundtrack. No source for this
particular custom renderer was located. The architecture in VIDEO.md is a
reconstruction, not a source audit. The earlier conversational wording that the
video was “watched” should be read with this more precise qualification.

## External primary sources

### E1: Kevin Ngo's post and attached video

- [Original post](https://x.com/kevin_t_ngo/status/2113663060888203642).
- Published 2026-10-23 according to the retrieval response.
- X returned 403 to the browsing tool. A public FxTwitter response supplied the
  post text and attached media URLs; it is a retrieval intermediary, not an
  independent corroboration of the author's claims.
- [Retrieval endpoint](https://api.fxtwitter.com/status/2113663060888203642).
- [Inspected 540-pixel video](https://video.twimg.com/amplify_video/2113656958318460929/vid/avc1/540x540/SGVwv5bBm3QvsX9h.mp4?tag=29).
- Metadata identifies a 120-second square video and a 1080-pixel source variant.
- Author reports a Claude-built Bend renderer. Visible frames identify Bend
  2.0.38. No rendering hardware, throughput, or renderer repository was obtained.

### E2: Current Bend README

- [README at the inspected revision](https://github.com/bendlang/bend/blob/295e996574573e3a88827b1cf7045b437333c8f0/README.md).
- [Limitations](https://github.com/bendlang/bend/blob/295e996574573e3a88827b1cf7045b437333c8f0/README.md#limitations).
- Useful for advertised goals and explicitly acknowledged boundaries. Marketing
  language is not a measurement. The source revision is newer than the release
  identified in the video; do not attribute every current feature to 2.0.38.

### E3: Current Bend guide

- [Guide at the inspected revision](https://github.com/bendlang/bend/blob/295e996574573e3a88827b1cf7045b437333c8f0/guide/GUIDE.md).
- Primary reference for language semantics and documented workflows.
- Executable behaviour was not independently checked here. Future comparisons
  must pin and run an actual release or build, including its checker options.

Only short summaries of external material are retained here; follow the primary
sources for their full claims. No downloaded third-party code or video is vendored.
The [manifest](evidence/source-manifest.json) records source hashes and identities.

## Repository evidence

Paths below are relative to this folder. Their presence establishes code or
recorded experiments, not universal compiler coverage or current test success.

| ID | Source | What it supports |
|---|---|---|
| L1 | [Repository README](../../README.md) | BL's intended application and live-development model |
| L2 | [Evidence publication](../../priv/lib/system/evidence.bl) | Generation-aware analysis publication; candidate classifications |
| L3 | [Native eligibility](../../priv/lib/native/eligible.bl) | Purity, termination, and result-sort candidate gate; remaining obligations |
| L4 | [SMT translator](../../priv/lib/system/smt.bl) | Supported translation mechanisms and explicit unknown/untranslatable cases |
| L5 | [Proofs as compiler output](../../docs/from-source-to-silicon/06-proofs-as-compiler-output.bl.org) | Optional analysis model and compiler annotations |
| L6 | [Native-region execution](../../docs/native-regions/01-meaning-and-execution.typ) | Semantics, representation, and execution boundaries |
| L7 | [Native-region checking](../../docs/native-regions/06-building-and-checking.typ) | Exact prototype admission and independent-oracle requirements |
| L8 | [Fusion results](../rt-selfhost/fusion/RESULTS.md) | Retained whole-call and kernel measurements for one byte pipeline |
| L9 | [Older offload wiring](../native-offload/README.md) | Earlier standalone-probe experiment; a different baseline |
| L10 | [Native region plan](../../!tasks/plans/PLAN-140-make-pure-data-regions-a-bl-compiler-exe.org) | Proposed generalization, explicitly not shipped functionality |
| L11 | [Film module](../../priv/lib/scenario/film.bl) | Existing scene/media export orchestration |
| L12 | [Film worker](../../priv/lib/scenario/film/render.py) | Python/FFmpeg implementation boundary and measured-media handling |
| L13 | [Task module](../../priv/std/proc/task.bl) | Captured environment and executable lifetime; cancellation qualifications |
| L14 | [Native host](../../priv/std/vm/native.bl) | Existing native declaration/build/lifetime integration points |

Historical documentation can overstate what a differential test establishes.
Agreement on fixtures is evidence about those fixtures; it is not a universal
proof of compilation correctness. A native eligibility candidate is also not
permission to execute arbitrary machine code. Current source qualifications take
precedence over an older broad headline.

## Reproducing the visual inspection

Download the public MP4 into a temporary directory, then use FFmpeg to sample:

```sh
ffmpeg -v error -i video.mp4 \
  -vf 'fps=1/8,scale=360:360,tile=5x3' -frames:v 1 contact.jpg
```

This yields 15 samples over two minutes. Inspect additional frames around any
transition under discussion. Sampling cannot establish motion smoothness, audio
content, or the performance of the generating program. Keep attribution to the
original post and do not use the resulting contact sheet as a renderer benchmark.
