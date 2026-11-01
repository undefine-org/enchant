# Reuse a qualified SDK selection

`nix/retained-sdk.nix` consumes a real qualified selection independently of a
public Source pin. It never demands `packages.sdk` or runs a producer. Supply:

- `sdk`: the declared flake input for the selection (used to observe its pinned
  artifact descriptor and launcher).
- `sdkReference`: the original qualified `/nix/store/…-beam-lisp-sdk-selection`.
- `sdkSource`: a separate declared input for `artifact.json`'s exact `source`.
- `source`: the public Source input used by native recipes.
- `descriptorSha256`: the qualified SHA256 of `artifact.json`.

The helper checks the descriptor, launcher reference, exact SDK Source binding,
complete Rust native Source inventory and hashes, and host NIF API Source. It
returns the real selection with its Nix package dependency context. The runtime
and Android staging still verify the genuine SDK/image/native contracts;
these passive consumer checks grant no SDK or execution authority.

Nix path inputs become `*-source` aliases. Their copied absolute links are not
pure permissions to read another store root, and the aliases have no retained
product references. Reading the declared SDK Source avoids traversing image
links; returning the explicit real selection retains the complete SDK closure.
`builtins.storePath` would make this consumer impure. Returning only the alias
would lose the real product dependency. Both mistakes have actual mutation
controls in `test/scripts/retained_sdk_pin.py`.

Use an exact published Source commit and the already qualified SDK reference
as separate pins. A later tag at the same commit can keep the same locked
revision and SDK selection. A missing retained closure fails rather than
silently producing a different SDK. Restore it from an authorized configured
store, or explicitly run the canonical producer once and review/update the
selection, descriptor and SDK Source pins together. No public binary cache is
implied by this interface.

Finite no-build proof using an existing genuine SDK:

```sh
python3 -B test/scripts/retained_sdk_pin.py --sdk /nix/store/QUALIFIED-beam-lisp-sdk-selection
```

It executes real pure/impure Nix evaluations, genuine product observation and
private native Source mutations. It never edits the SDK, fabricates metadata,
starts BEAM, compiles a native product or produces an SDK.
