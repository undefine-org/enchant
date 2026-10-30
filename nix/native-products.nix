# Server runtime products share the public single-crate manifest contract.
# Each crate has its own derivation: editing one never recompiles its siblings.
{ pkgs, root ? ../., target ? "x86_64-linux", includeDesktop ? false }:
let
  names = [ "bl_json" "code_embed" "datom_datalog" "datom_fjall" "datom_vector" "lazy_memo" ]
    ++ pkgs.lib.optional includeDesktop "wry_webview";
  products = builtins.listToAttrs (map (crate: {
    name = crate;
    value = import ./native-artifact.nix {
      requestJson = builtins.toJSON {
        version = 1;
        inherit crate target;
        source = toString (root + "/native/${crate}");
        abi = "beam-lisp-native-${crate}-v1";
      };
    };
  }) names);
  bundle = import ./native-bundle.nix { inherit pkgs products target; };
in assert target == "x86_64-linux";
{ inherit names products bundle; }
