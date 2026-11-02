# Optional GPU examples extend the ordinary scene tools without entering the
# compiler/SDK engine-input set. Both shells use the repository's package lock.
let
  lock = builtins.fromJSON (builtins.readFile ../../flake.lock);
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath {
    system = "x86_64-linux";
  };
in (import ../../nix/scene-tools.nix).overrideAttrs (old: {
  nativeBuildInputs = (old.nativeBuildInputs or []) ++ [ pkgs.libglvnd pkgs.mesa ];
  SCENE_RSVG = "${pkgs.librsvg}/bin/rsvg-convert";
  SCENE_EGL = "${pkgs.libglvnd}/lib/libEGL.so.1";
  SCENE_GLES = "${pkgs.libglvnd}/lib/libGLESv2.so.2";
  __EGL_VENDOR_LIBRARY_FILENAMES = "${pkgs.mesa}/share/glvnd/egl_vendor.d/50_mesa.json";
})
