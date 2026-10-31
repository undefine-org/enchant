# Realize and retain in one Nix operation; no unrooted evaluation result crosses
# a client-process boundary before the durable requester root is installed.
{ source, crate, version ? 1, member ? ".", package ? null }:
let
  lock = builtins.fromJSON (builtins.readFile ../flake.lock);
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
  snapshot = import ./native-source.nix { inherit source crate version member package; };
in pkgs.runCommand (if version == 1 then "${crate}-retained-source" else "native-workspace-retained-source") {} ''
  mkdir -p "$out"
  cp -a ${snapshot}/. "$out/"
''
