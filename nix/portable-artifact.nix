# A finite operation: package the selected SDK's exact native image.
{ sdk }:
let
  lock = builtins.fromJSON (builtins.readFile ../flake.lock);
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
  selected = builtins.fromJSON (builtins.unsafeDiscardStringContext
    (builtins.readFile (builtins.storePath sdk + "/artifact.json")));
  image = builtins.storePath selected.image;
  tools = builtins.storePath (builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile ../portable-tools.json))).tools;
in
assert builtins.match "/nix/store/[0-9a-z]{32}-[^/]+" sdk != null;
assert selected.version == 1 && selected.kind == "sdk";
import ./portable-product.nix { inherit pkgs image tools; }
