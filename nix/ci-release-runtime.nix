# Test the unchanged FHS release with its producer's pinned loader and libraries.
# This adapter does not produce an SDK, compiler cohort or native NIF.
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
  command = pkgs.writeShellScript "ci-release-command" ''
    unset BL_CI_RELEASE_CALLER_PATH
    exec "$@"
  '';
  fhs = pkgs.buildFHSEnv {
    name = "beam-lisp-ci-fhs-runtime";
    targetPkgs = _: libraries ++ tools;
    multiPkgs = _: [];
    multiArch = false;
    # Custody tickets and cgroup limits use the host's actual process identity.
    unsharePid = false;
    unshareCgroup = false;
    privateTmp = false;
    runScript = toString command;
    # The standard /etc/profile prepends FHS paths. Restore the caller's exact
    # SDK platform selection after pinned utility paths; do not lose its OTP.
    profile = ''
      export PATH=${toolsPath}:"$BL_CI_RELEASE_CALLER_PATH"
    '';
  };
  runner = pkgs.writeShellScriptBin "with-release-runtime" ''
    set -eu
    export BL_CI_RELEASE_CALLER_PATH="$PATH"
    export LD_LIBRARY_PATH=${pkgs.lib.makeLibraryPath libraries}
    exec ${fhs}/bin/beam-lisp-ci-fhs-runtime "$@"
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
    backend = "bubblewrap-fhs";
    inherit toolsPath;
  }}
  JSON
''
