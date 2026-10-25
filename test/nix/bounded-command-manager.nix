let
  lock = builtins.fromJSON (builtins.readFile ../../flake.lock);
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
  bounded = import ../../nix/bounded-build.nix {
    inherit pkgs;
    memoryMiB = 512;
    diskMiB = 1024;
    commandManager = true;
  };
in bounded (pkgs.runCommand "beam-lisp-bounded-command-manager-control" {} ''
  ${pkgs.systemd}/bin/systemd-run --user --collect --wait --pipe --quiet \
    --property=MemoryMax=64M --property=MemorySwapMax=0 \
    ${pkgs.coreutils}/bin/printf 'COMMAND-DOMAIN-READY\n' > answer
  grep -qx COMMAND-DOMAIN-READY answer
  mkdir -p "$out"
  printf '{"status":"passed","manager":"systemd-user","memoryKiB":%s}\n' \
    "$BL_WORKER_MEMORY_KIB" > "$out/worker.json"
'')
