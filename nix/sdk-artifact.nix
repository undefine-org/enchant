# SDK-family production from an already captured immutable full engine tree.
# The coordinator recipe is fixed; requests supply the engine input and one
# enumerated product, never an expression or a mutable Git checkout.
{ source, product ? "sdk" }:
let
  storeObject = value: builtins.isString value
    && builtins.match "/nix/store/[0-9a-z]{32}-[^/]+" value != null;
  engine = builtins.storePath source;
  lock = builtins.fromJSON (builtins.readFile (engine + "/flake.lock"));
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
  beam = import (engine + "/nix/beam.nix") {
    inherit pkgs;
    otp-src = (builtins.fetchTree lock.nodes.otp-src.locked).outPath;
    elixir-src = (builtins.fetchTree lock.nodes.elixir-src.locked).outPath;
  };
  products = import (engine + "/nix/bl-drop.nix") {
    inherit pkgs;
    rustPkgs = pkgs;
    inherit (beam) erlang elixir;
    includeDesktop = builtins.pathExists (engine + "/native/wry_webview/Cargo.toml");
  };
in
assert storeObject source;
assert builtins.elem product [ "sdk" "compiler" "dependencies" "bl-drop" ];
products.${product}
