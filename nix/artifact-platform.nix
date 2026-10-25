# A small immutable provider platform, independent of the compiler/SDK payload.
{ pkgs, commandExecutor ? import ./command-executor.nix { inherit pkgs; } }:
pkgs.runCommand "beam-lisp-artifact-platform" {} ''
  mkdir -p "$out/nix" "$out/bin"
  ln -s ${commandExecutor}/bin/bl-command-executor "$out/bin/bl-command-executor"
  cp ${commandExecutor}/executor.json "$out/executor.json"
  cp ${./native-artifact.nix} "$out/nix/native-artifact.nix"
  cp ${./native-source.nix} "$out/nix/native-source.nix"
  cp ${./bounded-build.nix} "$out/nix/bounded-build.nix"
  cp ${../flake.lock} "$out/flake.lock"
''
