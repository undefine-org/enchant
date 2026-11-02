# Read-only evaluation of the same producers used for realization.
{ kind, requestJson, sdk ? null }:
let product = if kind == "release" then import ./portable-artifact.nix { inherit sdk; }
              else if kind == "application" then import ./application-artifact.nix { inherit sdk requestJson; }
              else import ./native-artifact.nix { inherit requestJson; };
in assert builtins.elem kind [ "application" "native" "release" ];
{ output = product.outPath; derivation = product.drvPath; }
