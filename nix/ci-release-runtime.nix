# Test the unchanged FHS release with its producer's pinned loader and libraries.
# This small adapter has no SDK, compiler or native compilation dependency.
let
  lock = builtins.fromJSON (builtins.readFile ../flake.lock);
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
  libraries = [ pkgs.glibc pkgs.openssl pkgs.ncurses pkgs.zlib pkgs.stdenv.cc.cc.lib pkgs.brotli pkgs.zstd ];
  runner = pkgs.writeShellScriptBin "with-release-runtime" ''
    set -eu
    export PROOT_NO_SECCOMP=1
    exec ${pkgs.proot}/bin/proot --kill-on-exit \
      -b ${pkgs.glibc}/lib/ld-linux-x86-64.so.2:/lib64/ld-linux-x86-64.so.2 \
      -w "$PWD" ${pkgs.coreutils}/bin/env \
      LD_LIBRARY_PATH=${pkgs.lib.makeLibraryPath libraries} "$@"
  '';
in pkgs.runCommand "beam-lisp-ci-release-runtime" {} ''
  mkdir -p "$out/bin"
  ln -s ${runner}/bin/with-release-runtime "$out/bin/with-release-runtime"
  ln -s ${pkgs.binutils}/bin/readelf "$out/bin/readelf"
  cat > "$out/runtime.json" <<'JSON'
  ${builtins.toJSON {
    version = 1;
    kind = "ci-release-runtime";
    target = "x86_64-linux";
    nixpkgs = lock.nodes.nixpkgs.locked.rev;
    glibc = toString pkgs.glibc;
    glibcVersion = pkgs.glibc.version;
  }}
  JSON
''
