# Read-only host observation, deliberately outside the guest. Each observation
# has a caller-supplied sample identity so an old cached result is not live state.
{ sample }:
let
  lock = builtins.fromJSON (builtins.readFile ../../flake.lock);
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
in pkgs.runCommand "beam-lisp-builder-observation-${sample}" {} ''
  mkdir -p "$out"
  cp /proc/meminfo "$out/meminfo"
  cp /proc/self/cgroup "$out/cgroup"
  printf '%s\n' '${sample}' > "$out/sample"
  nproc > "$out/processors"
  for control in memory.max memory.swap.max; do
    if [ -r /sys/fs/cgroup/$control ]; then
      cat /sys/fs/cgroup/$control > "$out/$control"
    fi
  done
''
