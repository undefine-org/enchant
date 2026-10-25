# A small real VM control before native/compiler work is admitted to this worker.
let
  lock = builtins.fromJSON (builtins.readFile ../../flake.lock);
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
  bounded = import ../../nix/bounded-build.nix { inherit pkgs; memoryMiB = 512; diskMiB = 1024; };
in bounded (pkgs.runCommand "beam-lisp-bounded-worker-control" {} ''
  test "$NIX_BUILD_TOP" = /build
  test "$TMPDIR" = /build
  test -w /build
  test "$BL_WORKER_MEMORY_KIB" -gt 262144
  test "$BL_WORKER_MEMORY_KIB" -le 524288
  test "$BL_WORKER_SWAP_KIB" -eq 0
  mkdir -p "$out"
  printf '{"status":"passed","memoryKiB":%s,"swapKiB":%s,"scratch":"disk","backend":"nix-kvm"}\n' \
    "$BL_WORKER_MEMORY_KIB" "$BL_WORKER_SWAP_KIB" > "$out/worker.json"
'')
