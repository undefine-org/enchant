# Realization keeps the complete source closure rooted through the transition
# from evaluation to a durable requester root. Do not return an unrooted path
# to a separate client process and hope GC does not run between the two.
{ source, rootsJson, excludedJson ? "[]", packages ? null }:
let
  lock = builtins.fromJSON (builtins.readFile ../flake.lock);
  pkgs = if packages != null then packages else
    import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
  snapshot = import ./project-source.nix { inherit source rootsJson excludedJson; };
in pkgs.runCommand "beam-lisp-project-snapshot" {} ''
  mkdir -p "$out"
  cp -a ${snapshot}/. "$out/"
''
