# OxiZ worker prototype

Owner: this Codex session, one writer on `prototype/oxiz-worker`.
Requested worktree: `/home/othman/code/undefine/enchant--oxiz-prototype`.
Base: `8e41ee0f6efef47ad8ccacd99296ac3ddb8d736f` (Enchant `main`).
Retirement: after review, merge or archive this branch, retain its evidence,
then remove the worktree. It stays available for the requested prototype review.

This project reuses the exact qualified SDK in `sdk-pin.json`; it changes no
runtime inputs and produces no SDK. The ignored `.bl/sdks`, `.bl/platforms`, and
`priv/z3` links reuse the integration checkout's retained artifacts.

This directory is a standalone project. Its runner verifies and invokes the
qualified SDK's exact launcher, never the installed drop on PATH. The current
checkout engine has a different input fingerprint from that retained SDK;
running the checkout compiler wrapper would produce an unrelated SDK. Runtime
source is unchanged, and project checks deliberately stay on the recorded pin.

Experimental only. Z3 remains the authority. OxiZ 0.3.4 has documented open
soundness and model bugs. Comparison must bypass the shared oracle memo.

The implementation and measured results are recorded below when qualified.
