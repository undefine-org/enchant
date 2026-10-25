# Resolve the lock through Nix's flake input cache, but snapshot the working
# native/tool sources themselves, including new files not yet staged in Git.
{ root ? toString ../. }:
let
  locked = builtins.getFlake ("git+file://" + root);
  pkgs = import locked.inputs.nixpkgs.outPath { system = "x86_64-linux"; };
in import (/. + root + "/nix/checkout-platform.nix") {
  inherit pkgs;
  root = /. + root;
  inherit (locked.packages.x86_64-linux) erlang elixir;
}
