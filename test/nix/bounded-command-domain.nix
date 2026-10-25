# Reuse the actual command-domain controls inside the production worker shape.
let
  lock = builtins.fromJSON (builtins.readFile ../../flake.lock);
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
  executor = import ../../nix/command-executor.nix { inherit pkgs; };
  bounded = import ../../nix/bounded-build.nix {
    inherit pkgs;
    memoryMiB = 512;
    diskMiB = 1024;
    commandManager = true;
  };
in bounded (pkgs.runCommand "beam-lisp-bounded-command-domain-control" {
  nativeBuildInputs = [ pkgs.python3 ];
} ''
  export BL_CUSTODY_EXECUTOR=${executor}/bin/bl-command-executor
  mkdir -p "$out"
  python3 ${../scripts/test_command_domain.py} > "$out/controls.log" 2>&1 || {
    cat "$out/controls.log"
    exit 1
  }
  cat "$out/controls.log"
'')
