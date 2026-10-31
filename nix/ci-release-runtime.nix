# Test the unchanged FHS release with its producer's pinned loader and libraries.
# This small adapter has no SDK, compiler or native compilation dependency.
let
  lock = builtins.fromJSON (builtins.readFile ../flake.lock);
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
  libraries = [ pkgs.glibc pkgs.openssl pkgs.ncurses pkgs.zlib pkgs.stdenv.cc.cc.lib pkgs.brotli pkgs.zstd ];
  # The FHS loader must not resolve host dirname/basename (or fixture tools)
  # whose DT_NEEDED libraries belong to Ubuntu's different runtime. Preserve
  # the SDK's Erlang/Elixir selection after these pinned utility directories.
  tools = [ pkgs.coreutils pkgs.bash pkgs.findutils pkgs.gnugrep pkgs.gnused pkgs.gawk
    pkgs.python3 pkgs.gitMinimal pkgs.util-linux pkgs.diffutils ];
  toolsPath = pkgs.lib.makeBinPath tools;
  runner = pkgs.writeShellScriptBin "with-release-runtime" ''
    set -eu
    export PROOT_NO_SECCOMP=1
    export PATH=${toolsPath}:"$PATH"
    exec ${pkgs.proot}/bin/proot --kill-on-exit \
      -b ${pkgs.glibc}/lib/ld-linux-x86-64.so.2:/lib64/ld-linux-x86-64.so.2 \
      -b ${pkgs.coreutils}/bin/env:/usr/bin/env \
      -b ${pkgs.bash}/bin/bash:/bin/sh \
      -b ${pkgs.bash}/bin/bash:/bin/bash \
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
    inherit toolsPath;
  }}
  JSON
''
