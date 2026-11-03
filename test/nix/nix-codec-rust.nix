let
  lock = builtins.fromJSON (builtins.readFile ../../flake.lock);
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
  bounded = import ../../nix/bounded-build.nix { inherit pkgs; memoryMiB = 2048; cpuCount = 2; trace = true; };
in bounded (pkgs.rustPlatform.buildRustPackage {
  pname = "beam-lisp-nix-codec-laws";
  version = "0.1.0";
  src = pkgs.lib.cleanSource ../../native/bl_nix;
  cargoLock.lockFile = ../../native/bl_nix/Cargo.lock;
  doCheck = true;
  cargoTestFlags = [ "--lib" ];
  installPhase = ''
    mkdir -p "$out"
    echo '{"status":"passed","suite":"bl_nix Rust laws"}' > "$out/result.json"
  '';
})
