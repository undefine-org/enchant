# Select the lock through the flake cache; read complete working producer
# sources, including new files, through the production recipe's input filters.
{ root ? toString ../., product ? "sdk" }:
let
  locked = builtins.getFlake ("git+file://" + root);
  pkgs = import locked.inputs.nixpkgs.outPath { system = "x86_64-linux"; };
  products = import (/. + root + "/nix/bl-drop.nix") {
    inherit pkgs;
    rustPkgs = pkgs;
    inherit (locked.packages.x86_64-linux) erlang elixir;
  };
in assert builtins.elem product [ "sdk" "compiler" "dependencies" "bl-drop" ];
products.${product}
