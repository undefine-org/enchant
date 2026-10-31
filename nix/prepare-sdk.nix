# Select the lock through the flake cache; read complete working producer
# sources, including new files, through the production recipe's input filters.
{ root ? toString ../., product ? "sdk", previous ? null }:
let
  locked = builtins.getFlake ("git+file://" + root);
  pkgs = import locked.inputs.nixpkgs.outPath { system = "x86_64-linux"; };
  products = import (/. + root + "/nix/bl-drop.nix") {
    previousSdk = if previous == null then null else builtins.storePath previous;
    inherit pkgs;
    rustPkgs = pkgs;
    includeDesktop = builtins.pathExists (/. + root + "/native/wry_webview/Cargo.toml");
    inherit (locked.packages.x86_64-linux) erlang elixir;
  };
in assert builtins.elem product [ "sdk" "compiler" "dependencies" "bl-drop" ];
products.${product}
