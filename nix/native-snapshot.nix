# Realize and retain in one Nix operation; no unrooted evaluation result crosses
# a client-process boundary before the durable requester root is installed.
{ source, crate }:
let
  lock = builtins.fromJSON (builtins.readFile ../flake.lock);
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
  snapshot = import ./native-source.nix { inherit source crate; };
in pkgs.runCommand "${crate}-retained-source" {} ''
  mkdir -p "$out"
  cp -a ${snapshot}/. "$out/"
''
