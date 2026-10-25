# A small immutable provider platform, independent of the compiler/SDK payload.
{ pkgs }:
pkgs.runCommand "beam-lisp-artifact-platform" {} ''
  mkdir -p "$out/nix"
  cp ${./native-artifact.nix} "$out/nix/native-artifact.nix"
  cp ${./native-source.nix} "$out/nix/native-source.nix"
  cp ${../flake.lock} "$out/flake.lock"
''
