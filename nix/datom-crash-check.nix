# Actual process death at durable whole-root boundaries, on synthetic data only.
{ source, sdk, mode ? "process" }:
let
  input = import ./project-source.nix {
    inherit source;
    rootsJson = builtins.toJSON [ "scripts/datom-crash-check.py" "scripts/datom-power-cut.py"
      "test/support/datom_crash_fsync.c" "test/support/datom_root_crash.bl"
      "test/fixtures/datom/legacy-control-v1.tar.gz" "test/fixtures/datom/legacy-library-v1.tar.gz"
      "test/fixtures/datom/legacy-root-v1.json" "flake.lock" ];
    excludedJson = "[]";
  };
  lock = builtins.fromJSON (builtins.readFile (input + "/flake.lock"));
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
  selection = builtins.storePath sdk;
  metadata = builtins.fromJSON (builtins.unsafeDiscardStringContext
    (builtins.readFile (selection + "/artifact.json")));
  platform = builtins.storePath metadata.platform;
  release = if metadata ? release then builtins.storePath metadata.release else
    import (platform + "/artifact-platform/nix/portable-artifact.nix") { sdk = toString selection; };
  injector = pkgs.runCommand "datom-synthetic-fsync-injector" {
    nativeBuildInputs = [ pkgs.stdenv.cc ];
  } ''
    mkdir -p $out
    $CC -std=c11 -O2 -Wall -Wextra -Werror -fPIC -shared \
      ${input}/test/support/datom_crash_fsync.c -ldl -o $out/injector.so
  '';
  qemu = pkgs.writeShellScript "datom-power-cut-qemu" ''
    exec ${pkgs.python3}/bin/python3 ${input}/scripts/datom-power-cut.py \
      --qemu ${pkgs.qemu_kvm}/bin/qemu-system-x86_64 \
      --virtiofsd ${pkgs.virtiofsd}/bin/virtiofsd -- "$@"
  '';
  vmPkgs = if mode == "power" then pkgs // {
    vmTools = pkgs.vmTools.override { customQemu = qemu; };
  } else pkgs;
  # This proof owns cold SDK processes and native file descriptors directly;
  # it does not exercise application service-manager activation.
  bounded = import ./bounded-build.nix { pkgs = vmPkgs; memoryMiB = 6144; diskMiB = 24576; cpuCount = 2; commandManager = false; trace = true; };
in assert builtins.elem mode [ "process" "power" ];
bounded (pkgs.runCommand "datom-whole-root-${mode}-death" {
  __structuredAttrs = true;
  nativeBuildInputs = [ pkgs.python3 pkgs.util-linux pkgs.gnutar pkgs.gzip ];
  outputChecks.out.allowedReferences = [];
  postVM = pkgs.lib.optionalString (mode == "power") ''
    cp xchg/power-controller.json $out/
    ${pkgs.python3}/bin/python3 -c 'import json, sys; from pathlib import Path; assert json.loads(Path(sys.argv[1]).read_text())["status"] == "passed"' "$out/result.json"
  '';
} ''
  ${pkgs.lib.optionalString (mode == "power") ''
    # vmTools otherwise drops a rebooted disk into an interactive debug shell.
    # Remove only its own sentinel, durably, before any fixture SDK execution.
    rm -f /.debug
    sync /
  ''}
  mkdir -p /build/project /build/home /usr/bin /bin /lib64
  cp -a --no-preserve=ownership ${input}/. /build/project
  chmod -R u+w /build/project
  test -e /usr/bin/env || ln -s ${pkgs.coreutils}/bin/env /usr/bin/env
  test -e /bin/sh || ln -s ${pkgs.bash}/bin/sh /bin/sh
  test -e /lib64/ld-linux-x86-64.so.2 || ln -s ${pkgs.glibc}/lib/ld-linux-x86-64.so.2 /lib64/ld-linux-x86-64.so.2
  export LD_LIBRARY_PATH=${pkgs.lib.makeLibraryPath [ pkgs.openssl pkgs.ncurses pkgs.zlib pkgs.glibc pkgs.stdenv.cc.cc.lib pkgs.brotli pkgs.zstd ]}
  # The selected SDK is immutable. Its disposable portable extraction is not
  # the application database and must not become a durability prerequisite.
  export XDG_DATA_HOME=/run/datom-runtime
  export HOME=/build/home BL_DAEMON=off BL_SDK_PRODUCT=${selection}
  export PATH=${platform}/bin:$PATH
  export ELIXIR_ERL_OPTIONS='+fnu +S 2:2 +SDcpu 1:1 +SDio 1:1'
  cd /build/project
  power_args=()
  ${pkgs.lib.optionalString (mode == "power") ''
    read -r operation boundary < /tmp/xchg/power-stage
    power_args=(--power "$operation" --boundary "$boundary")
  ''}
  python3 scripts/datom-crash-check.py --candidate ${release}/bl.drop \
    --injector ${injector}/injector.so --out /tmp/xchg/crash-receipts "''${power_args[@]}" || {
      tail -n 60 /tmp/xchg/crash-receipts/*.log
      exit 1
    }
  mkdir -p $out
  cp /tmp/xchg/crash-receipts/* $out/
'')
