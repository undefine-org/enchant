# Resolve the lock through Nix's flake input cache, but snapshot the working
# native/tool sources themselves, including new files not yet staged in Git.
{ root ? toString ../. }:
let
  lock = builtins.fromJSON (builtins.readFile (/. + root + "/flake.lock"));
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
  beam = import (/. + root + "/nix/beam.nix") {
    inherit pkgs;
    otp-src = (builtins.fetchTree lock.nodes.otp-src.locked).outPath;
    elixir-src = (builtins.fetchTree lock.nodes.elixir-src.locked).outPath;
  };
in import (/. + root + "/nix/checkout-platform.nix") {
  inherit pkgs;
  root = /. + root;
  inherit (beam) erlang elixir;
}
