# Test-only transport: existing SDK + immutable proof inputs, never SDK production.
{ source, requestPath, sdk, memoryMiB ? 3072, cpuCount ? 2, tools ? [], nativeLibraries ? [], portableHost ? false }:
let
  input = builtins.storePath source;
  selection = builtins.storePath sdk;
  lock = builtins.fromJSON (builtins.readFile (input + "/flake.lock"));
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
  metadata = builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile (selection + "/artifact.json")));
  platform = builtins.storePath metadata.platform;
  bounded = import (input + "/nix/bounded-build.nix") {
    inherit pkgs memoryMiB cpuCount; diskMiB = 12288; commandManager = true;
  };
in bounded (pkgs.runCommand "beam-lisp-historical-case-proof" {
  nativeBuildInputs = [ pkgs.python3 pkgs.git pkgs.ripgrep pkgs.util-linux ] ++ map (name: pkgs.${name}) tools;
} ''
  cp -a --no-preserve=ownership ${input}/. /build/proof
  chmod -R u+w /build/proof
  mkdir -p "$out" /usr/bin
  test -e /usr/bin/env || ln -s ${pkgs.coreutils}/bin/env /usr/bin/env
  ${pkgs.lib.optionalString portableHost ''
    mkdir -p /lib64 /bin
    test -e /lib64/ld-linux-x86-64.so.2 || ln -s ${pkgs.glibc}/lib/ld-linux-x86-64.so.2 /lib64/ld-linux-x86-64.so.2
    test -e /bin/sh || ln -s ${pkgs.bash}/bin/sh /bin/sh
    test -e /bin/bash || ln -s ${pkgs.bash}/bin/bash /bin/bash
    export LD_LIBRARY_PATH=${pkgs.lib.makeLibraryPath [ pkgs.openssl pkgs.ncurses pkgs.zlib pkgs.glibc pkgs.stdenv.cc.cc.lib ]}
  ''}
  export PATH=${platform}/bin:$PATH
  ${pkgs.lib.optionalString (nativeLibraries != []) ''export LD_LIBRARY_PATH=${pkgs.lib.makeLibraryPath (map (name: pkgs.${name}) nativeLibraries)}''}
  export ELIXIR_ERL_OPTIONS='+S ${toString cpuCount}:${toString cpuCount} +SDcpu 1:1 +SDio 1:1 +fnu'
  cd /build/proof
  python3 ${./worker.py} --sdk ${selection} --root /build/proof \
    --request ${requestPath} --out "$out"
'')
