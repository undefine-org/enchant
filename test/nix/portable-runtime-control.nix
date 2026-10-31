# Reuse the actually qualified FHS receiver baseline, against one immutable
# portable release. This is a glibc/C++/OTP baseline control, not a claim that
# every Linux distribution or arbitrary FHS runtime can execute the drop.
{ release }:
let
  lock = builtins.fromJSON (builtins.readFile ../../flake.lock);
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath {
    system = "x86_64-linux";
  };
  beam = import ../../nix/beam.nix {
    inherit pkgs;
    otp-src = (builtins.fetchTree lock.nodes.otp-src.locked).outPath;
    elixir-src = (builtins.fetchTree lock.nodes.elixir-src.locked).outPath;
  };
  address = toString release;
  product = builtins.storePath address;
  # Parse descriptor fields as data; product itself remains an explicit
  # storePath dependency. Embedded compiler addresses are not expressions.
  manifest = builtins.fromJSON (builtins.unsafeDiscardStringContext
    (builtins.readFile (product + "/artifact.json")));
in
assert builtins.match "/nix/store/[0-9a-z]{32}-[^/]+" address != null;
assert manifest.version == 1 && manifest.kind == "release" && manifest.target == "x86_64-linux";
assert manifest.file == "bl.drop";
assert builtins.hashFile "sha256" (product + "/bl.drop") == manifest.sha256;
import ./portable-runtime.nix {
  drop = product + "/bl.drop";
  inherit (beam) erlang;
}
