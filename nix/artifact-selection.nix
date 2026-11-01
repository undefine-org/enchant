# Read-only evaluation of the same producers used for realization.
{ kind, requestJson, sdk ? null }:
let product = if kind == "application" then import ./application-artifact.nix { inherit sdk requestJson; }
              else import ./native-artifact.nix { inherit requestJson; };
in assert builtins.elem kind [ "application" "native" ];
{ output = product.outPath; derivation = product.drvPath; }
