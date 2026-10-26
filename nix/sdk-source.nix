# Capture the complete declared engine producer tree, including recipes and
# pinned coordinator sources. Generated state never becomes a producer input.
{ source }:
let
  lock = builtins.fromJSON (builtins.readFile ../flake.lock);
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
  root = /. + source;
  text = toString root;
  prefix = parent: child: parent == child || pkgs.lib.hasPrefix (parent + "/") child;
  roots = [ "bin" "nix" "priv" "native" "tooling/drop" "vendor/foundry-ledger"
    "env.bl" "bl.lock" "flake.nix" "flake.lock"
    "scripts/prepare-checkout-platform" "scripts/prepare-checkout-sdk"
    "scripts/prepare-release.bl" "scripts/produce-sdk.bl"
    "scripts/qualify-artifact-generation" "scripts/demo-artifact-production"
    "scripts/check-source-floor" "scripts/check-execution-history"
    "test/scripts/artifact-generation.bl" ];
  excluded = [ "priv/native" "priv/z3" "priv/codegen.sources" "priv/precompiled.term" "priv/sdk-code.term" ];
  captured = builtins.path {
    name = "beam-lisp-engine-source";
    path = root;
    filter = path: type:
      let
        full = toString path;
        relative = if full == text then "." else builtins.substring (builtins.stringLength text + 1) (builtins.stringLength full) full;
        reserved = builtins.elem (baseNameOf path) [ ".git" ".bl" ]
          || (baseNameOf path == "target" && (prefix "native" relative || prefix "tooling/drop" relative))
          || builtins.any (entry: prefix entry relative) excluded;
        selected = builtins.any (entry: prefix entry relative || prefix relative entry) roots;
      in if relative == "." then true
         else if reserved || !selected then false
         else if type == "symlink" then throw "Engine production requires a self-contained source tree"
         else type == "directory" || type == "regular";
  };
in
assert builtins.isString source && pkgs.lib.hasPrefix "/" source && text != "/";
assert builtins.all (entry: builtins.pathExists (root + "/${entry}")) roots;
pkgs.runCommand "beam-lisp-engine-snapshot" {} ''
  mkdir -p "$out"
  cp -a ${captured}/. "$out/"
''
