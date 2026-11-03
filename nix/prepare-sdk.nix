# Select the lock through the flake cache; read complete working producer
# sources, including new files, through the production recipe's input filters.
{ root ? toString ../., product ? "sdk", previous ? null }:
let
  lock = builtins.fromJSON (builtins.readFile (/. + root + "/flake.lock"));
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
  beam = import (/. + root + "/nix/beam.nix") {
    inherit pkgs;
    otp-src = (builtins.fetchTree lock.nodes.otp-src.locked).outPath;
    elixir-src = (builtins.fetchTree lock.nodes.elixir-src.locked).outPath;
  };
  products = import (/. + root + "/nix/bl-drop.nix") {
    previousSdk = if previous == null then null else builtins.storePath previous;
    inherit pkgs;
    rustPkgs = pkgs;
    includeDesktop = builtins.pathExists (/. + root + "/native/wry_webview/Cargo.toml");
    inherit (beam) erlang elixir;
  };
in assert builtins.elem product [ "sdk" "compiler" "dependencies" "bl-drop" ];
products.${product}
