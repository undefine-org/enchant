# A small immutable provider platform, independent of the compiler/SDK payload.
{ pkgs, commandExecutor ? import ./command-executor.nix { inherit pkgs; }, includeRecipes ? true }:
pkgs.runCommand "beam-lisp-artifact-platform" {} ''
  mkdir -p "$out/nix" "$out/bin"
  ln -s ${commandExecutor}/bin/bl-command-executor "$out/bin/bl-command-executor"
  ln -s ${pkgs.python3}/bin/python3 "$out/bin/python3"
  for executable in ${pkgs.nix}/bin/*; do
    ln -s "$executable" "$out/bin/$(basename "$executable")"
  done
  ln -s ${pkgs.systemd}/bin/systemd-run "$out/bin/systemd-run"
  ln -s ${pkgs.systemd}/bin/systemctl "$out/bin/systemctl"
  ln -s ${pkgs.util-linux}/bin/setsid "$out/bin/setsid"
  ln -s ${pkgs.procps}/bin/kill "$out/bin/kill"
  cp ${commandExecutor}/executor.json "$out/executor.json"
  ${pkgs.lib.optionalString includeRecipes ''
  cp ${./native-compile.nix} "$out/nix/native-compile.nix"
  cp ${./native-artifact.nix} "$out/nix/native-artifact.nix"
  cp ${./native-snapshot.nix} "$out/nix/native-snapshot.nix"
  cp ${./native-workspace.nix} "$out/nix/native-workspace.nix"
  cp ${./sdk-source.nix} "$out/nix/sdk-source.nix"
  cp ${./engine-inputs.json} "$out/nix/engine-inputs.json"
  cp ${./sdk-artifact.nix} "$out/nix/sdk-artifact.nix"
  cp ${./native-source.nix} "$out/nix/native-source.nix"
  cp ${./bounded-build.nix} "$out/nix/bounded-build.nix"
  cp ${./application-artifact.nix} "$out/nix/application-artifact.nix"
  cp ${./artifact-selection.nix} "$out/nix/artifact-selection.nix"
  cp ${./application-selection.nix} "$out/nix/application-selection.nix"
  cp ${./sdk-worker-filesystem.nix} "$out/nix/sdk-worker-filesystem.nix"
  cp ${./application-worker.bl} "$out/nix/application-worker.bl"
  cp ${./application-inventory.py} "$out/nix/application-inventory.py"
  cp ${./project-source.nix} "$out/nix/project-source.nix"
  cp ${./project-snapshot.nix} "$out/nix/project-snapshot.nix"
  cp ${./native-bundle.nix} "$out/nix/native-bundle.nix"
  cp ${../flake.lock} "$out/flake.lock"
  ''}
''
