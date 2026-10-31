# Pressure beyond guest RAM must be refused or killed, leave the worker
# controllable and permit subsequent work; host memory is never unbounded.
let
  lock = builtins.fromJSON (builtins.readFile ../../flake.lock);
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
  bounded = import ../../nix/bounded-build.nix {
    inherit pkgs;
    memoryMiB = 512;
    diskMiB = 1024;
    cpuCount = 4;
    commandManager = true;
  };
in bounded (pkgs.runCommand "beam-lisp-bounded-memory-pressure-control" {
  nativeBuildInputs = [ pkgs.python3 ];
} ''
  before=$(awk '$1 == "oom_kill" { print $2 }' /proc/vmstat)
  status=0
  python3 -c 'buffer = bytearray(1024 * 1024 * 1024); buffer[::4096] = b"x" * len(buffer[::4096])' > pressure.log 2>&1 || status=$?
  after=$(awk '$1 == "oom_kill" { print $2 }' /proc/vmstat)
  if [ "$status" -eq 137 ]; then
    test "$after" -gt "$before"
    containment=oom-killed
  else
    test "$status" -eq 1
    grep -q MemoryError pressure.log
    containment=allocation-refused
  fi
  test "$(nproc)" -eq 4
  python3 -c 'buffer = bytearray(1024 * 1024); assert len(buffer) == 1048576'
  test "$BL_WORKER_SWAP_KIB" -eq 0
  mkdir -p "$out"
  printf '{"status":"passed","containment":"%s","subsequentWorkPassed":true,"cpuCount":4,"memoryKiB":%s,"swapKiB":0}\n' \
    "$containment" "$BL_WORKER_MEMORY_KIB" > "$out/control.json"
'')
