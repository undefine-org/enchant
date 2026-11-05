# One read-only evaluation selects an existing source snapshot and application.
# These are hints until the caller retains the actual outputs. Missing or
# collected source snapshots use the ordinary atomic realization path.
{ source, rootsJson, excludedJson ? "[]", sdk, requestJson }:
let
  # Share only within this evaluation. Every request still captures its source
  # and reconstructs the fixed application recipe, including an unchanged base.
  lock = builtins.fromJSON (builtins.readFile ../flake.lock);
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
  snapshot = import ./project-snapshot.nix {
    inherit source rootsJson excludedJson;
    packages = pkgs;
  };
  snapshotPath = builtins.unsafeDiscardStringContext snapshot.outPath;
  request = (builtins.fromJSON requestJson) // { source = snapshotPath; };
  realized = builtins.pathExists snapshotPath;
  product = if realized && !(request.force or false)
    then import ./application-artifact.nix {
      inherit sdk;
      packages = pkgs;
      requestJson = builtins.toJSON request;
    }
    else null;
in {
  source = snapshotPath;
  output = if product == null then null else product.outPath;
  derivation = if product == null then null else product.drvPath;
}
