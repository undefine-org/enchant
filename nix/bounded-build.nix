# Resource ownership stays with the Nix realization even when a client exits.
# KVM-backed RAM and a finite scratch disk bound the whole guest process tree;
# they do not depend on an unprivileged client changing daemon settings.
{ pkgs, memoryMiB ? 3072, diskMiB ? 12288, commandManager ? false, cpuCount ? 1, trace ? false }:
drv:
assert builtins.isInt memoryMiB && memoryMiB >= 256 && memoryMiB <= 8192;
assert builtins.isInt diskMiB && diskMiB >= 1024 && diskMiB <= 65536;
assert builtins.isBool commandManager;
assert builtins.isBool trace;
assert builtins.isInt cpuCount && cpuCount >= 1 && cpuCount <= 8;
pkgs.vmTools.runInLinuxVM (pkgs.lib.overrideDerivation drv (old: {
  memSize = memoryMiB;
  enableParallelBuilding = false;
  QEMU_OPTS = pkgs.lib.optionalString (cpuCount != 1) "-smp cpus=${toString cpuCount}";
  preVM = ''
    ${pkgs.lib.optionalString (commandManager || trace) (if trace then ''
      touch xchg/worker-debug
      ${pkgs.coreutils}/bin/tail -n +1 --follow=name --retry --sleep-interval=0.1 xchg/worker-debug &
      compiler_trace_pid=$!
      trap 'kill "$compiler_trace_pid" 2>/dev/null || true; wait "$compiler_trace_pid" 2>/dev/null || true; test ! -f xchg/worker-debug || cat xchg/worker-debug' EXIT
    '' else "trap 'test ! -f xchg/worker-debug || cat xchg/worker-debug' EXIT")}
    diskImage="$PWD/worker.ext4"
    truncate -s ${toString diskMiB}M "$diskImage"
    ${pkgs.e2fsprogs}/bin/mkfs.ext4 -q -F "$diskImage"
    mountDisk=/dev/vda
  '';
  builder = toString (pkgs.writeShellScript "beam-lisp-bounded-worker" ''
    set -euo pipefail
    memory_kib=$(awk '/^MemTotal:/ { print $2 }' /proc/meminfo)
    swap_kib=$(awk '/^SwapTotal:/ { print $2 }' /proc/meminfo)
    test "$memory_kib" -le ${toString (memoryMiB * 1024)}
    test "$swap_kib" -eq 0
    mkdir -p /build
    export NIX_BUILD_TOP=/build TMPDIR=/build
    export BL_WORKER_MEMORY_KIB="$memory_kib" BL_WORKER_SWAP_KIB="$swap_kib"
    ${pkgs.lib.optionalString (trace && !commandManager) "exec > /tmp/xchg/worker-debug 2>&1"}${pkgs.lib.optionalString commandManager ''
      exec > /tmp/xchg/worker-debug 2>&1
      # Use the existing command-domain implementation inside the private
      # worker too. It retains real filesystem loans in a real service manager.
      mkdir -p /sys/fs/cgroup /run/systemd/system /run/user/0 /run/current-system/sw/bin
      ${pkgs.util-linux}/bin/mount -t cgroup2 none /sys/fs/cgroup
      chmod 700 /run/user/0
      printf '4fdf61b7a9ea451c87c14b6e6d9fded1\n' > /etc/machine-id
      ln -s ${pkgs.systemd}/bin/systemd-run /run/current-system/sw/bin/systemd-run
      ln -s ${pkgs.systemd}/bin/systemctl /run/current-system/sw/bin/systemctl
      export XDG_RUNTIME_DIR=/run/user/0
      export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/0/bus
      mkdir -p /etc/systemd/user/sockets.target.wants
      cp ${pkgs.dbus}/etc/systemd/user/dbus.socket /etc/systemd/user/dbus.socket
      sed 's|--session |--config-file=${pkgs.dbus}/share/dbus-1/session.conf |' \
        ${pkgs.dbus}/etc/systemd/user/dbus.service > /etc/systemd/user/dbus.service
      ln -s ../dbus.socket /etc/systemd/user/sockets.target.wants/dbus.socket
      export SYSTEMD_UNIT_PATH=/etc/systemd/user:${pkgs.systemd}/example/systemd/user
      ${pkgs.systemd}/lib/systemd/systemd --user --unit=basic.target --log-target=console > /tmp/command-manager.log 2>&1 &
      ready=0
      for attempt in $(seq 1 50); do
        if timeout 1 ${pkgs.systemd}/bin/busctl --user status org.freedesktop.systemd1 >/dev/null 2>&1; then ready=1; break; fi
        sleep 0.1
      done
      if [ "$ready" != 1 ]; then cat /tmp/command-manager.log; exit 1; fi
    ''}
    cd /build
    exec ${old.builder} "$@"
  '');
}))
