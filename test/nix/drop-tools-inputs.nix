{ root }:
let
  lock = builtins.fromJSON (builtins.readFile ../../flake.lock);
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath {
    system = "x86_64-linux";
  };
  tools = import ../../nix/drop-tools.nix { inherit pkgs; root = /. + root; };
in { source = toString tools.src; derivation = tools.drvPath; }
