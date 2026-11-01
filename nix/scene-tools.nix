# Optional graphics tools for the experimental scene examples and workers.
# Uses the same pinned package set as the engine's ordinary Nix recipes.
let
  lock = builtins.fromJSON (builtins.readFile ../flake.lock);
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath {
    system = "x86_64-linux";
  };
in pkgs.mkShell {
  packages = [ pkgs.python3 pkgs.librsvg pkgs.ffmpeg pkgs.fontconfig pkgs.glibc.bin ];
  FONTCONFIG_FILE = pkgs.makeFontsConf { fontDirectories = [ pkgs.dejavu_fonts ]; };
}
