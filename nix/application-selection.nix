# One read-only evaluation selects an existing source snapshot and application.
# These are hints until the caller retains the actual outputs. Missing or
# collected source snapshots use the ordinary atomic realization path.
{ source, rootsJson, excludedJson ? "[]", sdk, requestJson }:
let
  snapshot = import ./project-snapshot.nix { inherit source rootsJson excludedJson; };
  snapshotPath = builtins.unsafeDiscardStringContext snapshot.outPath;
  request = (builtins.fromJSON requestJson) // { source = snapshotPath; };
  realized = builtins.pathExists snapshotPath;
  product = if realized && !(request.force or false)
    then import ./application-artifact.nix { inherit sdk; requestJson = builtins.toJSON request; }
    else null;
in {
  source = snapshotPath;
  output = if product == null then null else product.outPath;
  derivation = if product == null then null else product.drvPath;
}
