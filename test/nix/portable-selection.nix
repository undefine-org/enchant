# Recipe identity depends on the native image, not its selection wrapper.
{ sdk }:
let
  lock = builtins.fromJSON (builtins.readFile ../../flake.lock);
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
  read = path: builtins.fromJSON (builtins.unsafeDiscardStringContext
    (builtins.readFile (path + "/artifact.json")));
  metadata = read (builtins.storePath sdk);
  platform = import ../../nix/artifact-platform.nix { inherit pkgs; };
  wrapper = note: pkgs.writeTextDir "artifact.json" (builtins.toJSON (metadata // { inherit note; }));
  select = selection:
    assert (read selection).kind == "sdk";
    import (platform + "/nix/portable-artifact.nix") { sdk = toString selection; };
  first = select (wrapper "first control plane");
  second = select (wrapper "second control plane");
  direct = import ../../nix/portable-product.nix {
    inherit pkgs;
    image = builtins.storePath metadata.image;
    tools = builtins.storePath (builtins.unsafeDiscardStringContext
      (toString (import ../../nix/drop-tools.nix { inherit pkgs; })));
  };
in
assert first.outPath == second.outPath;
assert first.outPath == direct.outPath;
{ status = "passed"; portable = first.outPath; sameNativeImage = metadata.image; }
