# A small immutable provider platform, independent of the compiler/SDK payload.
{ pkgs, commandExecutor ? import ./command-executor.nix { inherit pkgs; } }:
pkgs.runCommand "beam-lisp-artifact-platform" {} ''
  mkdir -p "$out/nix" "$out/bin"
  ln -s ${commandExecutor}/bin/bl-command-executor "$out/bin/bl-command-executor"
  ln -s ${pkgs.python3}/bin/python3 "$out/bin/python3"
  cp ${commandExecutor}/executor.json "$out/executor.json"
  cp ${./native-artifact.nix} "$out/nix/native-artifact.nix"
  cp ${./native-source.nix} "$out/nix/native-source.nix"
  cp ${./bounded-build.nix} "$out/nix/bounded-build.nix"
  cp ${./application-artifact.nix} "$out/nix/application-artifact.nix"
  cp ${./application-worker.bl} "$out/nix/application-worker.bl"
  cp ${./application-inventory.py} "$out/nix/application-inventory.py"
  cp ${./project-source.nix} "$out/nix/project-source.nix"
  cp ${./project-snapshot.nix} "$out/nix/project-snapshot.nix"
  cp ${./native-bundle.nix} "$out/nix/native-bundle.nix"
  cp ${../flake.lock} "$out/flake.lock"
''
