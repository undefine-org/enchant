{ root }:
let
  lock = builtins.fromJSON (builtins.readFile ../../flake.lock);
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
  native = import ../../nix/native-products.nix { inherit pkgs root; };
in builtins.mapAttrs (_: product: product.drvPath) native.products
