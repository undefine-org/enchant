# Import a Source-owned backend through its checked bootstrap projection.
{ description }:
{ lib, ... }:
let
  path = toString description;
  compiled = import (/. + (lib.removeSuffix ".bl" path + ".nix"));
  backend = compiled.description;
in
assert lib.hasSuffix ".bl" path;
assert compiled.sourceSha256 == builtins.hashFile "sha256" description;
assert backend.version == 1;
assert builtins.elem backend.kind [ "local" "configured" "ssh" "nixbuild" ];
{
  nix = backend.nix;
  environment.etc = lib.optionalAttrs (backend ? evaluation) {
    "beam-lisp/build-station.json".text = builtins.toJSON ({ version = 1; } // backend.evaluation);
  };
}
