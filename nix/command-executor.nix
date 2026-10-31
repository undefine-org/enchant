# The executor and transport share one stock binary and final-byte manifest.
{ pkgs }:
import ./drop-tools.nix { inherit pkgs; }
