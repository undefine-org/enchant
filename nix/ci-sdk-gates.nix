# Check the SDK's already-produced portable bytes; never select another SDK.
{ sdk }:
let
  lock = builtins.fromJSON (builtins.readFile ../flake.lock);
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
  selection = builtins.storePath sdk;
  metadata = builtins.fromJSON (builtins.readFile (selection + "/artifact.json"));
  release = builtins.storePath metadata.release;
  portable = builtins.fromJSON (builtins.readFile (release + "/artifact.json"));
  platform = builtins.fromJSON (builtins.readFile (builtins.storePath metadata.platform + "/platform.json"));
  executor = builtins.storePath platform.executor;
  runs = import ./drop-runs.nix { inherit pkgs; drop = release; };
  floor = pkgs.runCommand "bl-selected-sdk-glibc-floor" {
    nativeBuildInputs = [ pkgs.binutils pkgs.findutils ];
  } ''
    export DROP_BIN=${executor}/bin/drop
    got=$(sh ${../tooling/drop/glibc-floor.sh} ${release}/bl.drop)
    echo "$got"
    v=$(echo "$got" | cut -d' ' -f1)
    [ "$(printf '%s\n2.44\n' "$v" | sort -V | tail -1)" = 2.44 ] \
      || { echo "glibc floor $v exceeds the declared 2.44 host requirement" >&2; exit 1; }
    printf '%s\n' "$got" > "$out"
  '';
in
assert metadata.version == 1 && metadata.kind == "sdk" && metadata.target == "x86_64-linux";
assert portable.version == 1 && portable.kind == "release" && portable.target == metadata.target;
assert portable.compiler == metadata.compiler && portable.file == "bl.drop";
pkgs.linkFarm "beam-lisp-selected-sdk-gates" [
  { name = "drop-runs"; path = runs; }
  { name = "glibc-floor"; path = floor; }
]
