# Checkout entry for staging its immutable recipes and stock command executor.
let
  lock = builtins.fromJSON (builtins.readFile ../flake.lock);
  source = builtins.fetchTree lock.nodes.nixpkgs.locked;
  pkgs = import source.outPath { system = "x86_64-linux"; };
in import ./artifact-platform.nix { inherit pkgs; }
