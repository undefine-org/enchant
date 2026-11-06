# Real publication cuts of the stock portable extractor, using synthetic files.
# No SDK/BEAM or application data is needed to prove this cache boundary.
{ source, sdk ? null }:
let
  root = /. + source;
  input = import ./project-source.nix {
    inherit source;
    rootsJson = builtins.toJSON [ "scripts/datom-power-cut.py" "scripts/drop-cache-crash-check.py"
      "test/support/drop_cache_fsync.c" "flake.lock" ];
    excludedJson = "[]";
  };
  lock = builtins.fromJSON (builtins.readFile (input + "/flake.lock"));
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
  tools = import ./drop-tools.nix { inherit pkgs; root = root + "/tooling/drop"; };
  selection = if sdk == null then null else builtins.storePath sdk;
  metadata = if selection == null then null else builtins.fromJSON
    (builtins.unsafeDiscardStringContext (builtins.readFile (selection + "/artifact.json")));
  release = if selection == null then null else if metadata ? release then builtins.storePath metadata.release else
    import (builtins.storePath metadata.platform + "/artifact-platform/nix/portable-artifact.nix") { sdk = toString selection; };
  injector = pkgs.runCommand "drop-cache-synthetic-fsync-injector" {
    nativeBuildInputs = [ pkgs.stdenv.cc ];
  } ''
    mkdir -p $out
    $CC -std=c11 -O2 -Wall -Wextra -Werror -fPIC -shared \
      ${input}/test/support/drop_cache_fsync.c -ldl -o $out/injector.so
  '';
  qemu = pkgs.writeShellScript "drop-cache-power-cut-qemu" ''
    exec ${pkgs.python3}/bin/python3 ${input}/scripts/datom-power-cut.py \
      --qemu ${pkgs.qemu_kvm}/bin/qemu-system-x86_64 \
      --virtiofsd ${pkgs.virtiofsd}/bin/virtiofsd \
      --boundaries file-synced tree-synced renamed published --label DROP-CACHE-POWER -- "$@"
  '';
  vmPkgs = pkgs // { vmTools = pkgs.vmTools.override { customQemu = qemu; }; };
  bounded = import ./bounded-build.nix {
    pkgs = vmPkgs; memoryMiB = 2048; diskMiB = 4096; cpuCount = 1; commandManager = false; trace = true;
  };
in bounded (pkgs.runCommand "drop-cache-power-death" {
  __structuredAttrs = true;
  nativeBuildInputs = [ pkgs.python3 ];
  outputChecks.out.allowedReferences = [];
  postVM = ''
    cp xchg/power-controller.json $out/
    ${pkgs.python3}/bin/python3 - "$out/result.json" ${tools}/bin/drop-launcher <<'PY'
    import hashlib, json, sys
    from pathlib import Path
    path = Path(sys.argv[1])
    result = json.loads(path.read_text())
    assert result['status'] == 'passed' and len(result['controls']) == 4
    result['launcher_sha256'] = hashlib.file_digest(Path(sys.argv[2]).open('rb'), 'sha256').hexdigest()
    result['execution'] = 'bounded-kvm-same-disk-reboot'
    path.write_text(json.dumps(result, indent=2) + '\n')
    PY
  '';
} ''
  rm -f /.debug
  sync /
  mkdir -p /bin /usr/bin /lib64 /build/home
  test -e /bin/sh || ln -s ${pkgs.bash}/bin/sh /bin/sh
  test -e /usr/bin/env || ln -s ${pkgs.coreutils}/bin/env /usr/bin/env
  test -e /lib64/ld-linux-x86-64.so.2 || ln -s ${pkgs.glibc}/lib/ld-linux-x86-64.so.2 /lib64/ld-linux-x86-64.so.2
  export HOME=/build/home
  export LD_LIBRARY_PATH=${pkgs.lib.makeLibraryPath [ pkgs.openssl pkgs.ncurses pkgs.zlib pkgs.glibc pkgs.stdenv.cc.cc.lib pkgs.brotli pkgs.zstd ]}
  export ELIXIR_ERL_OPTIONS='+fnu +S 1:1 +SDcpu 1:1 +SDio 1:1'
  ${pkgs.lib.optionalString (metadata != null) ''export PATH=${builtins.storePath metadata.platform}/bin:$PATH''}
  read -r operation boundary < /tmp/xchg/power-stage
  python3 ${input}/scripts/drop-cache-crash-check.py --launcher ${tools}/bin/drop-launcher \
    --injector ${injector}/injector.so --out /tmp/xchg/cache-receipts \
    --operation "$operation" --boundary "$boundary" \
    ${if release == null then "" else "--candidate ${release}/bl.drop"}
  mkdir -p $out
  cp /tmp/xchg/cache-receipts/result.json $out/
'')
