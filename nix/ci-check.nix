# Execute a finite check where the retained SDK lives; return only receipts.
# Existing SDK selection is optional. The default uses the ordinary SDK recipe.
{ source, request, sdk ? null, previous ? null, memoryMiB ? 6144, cpuCount ? 2 }:
let
  root = /. + source;
  roots = builtins.filter (name: builtins.pathExists (root + "/${name}")) [
    ".gitignore" ".github" "AGENTS.md" "README.md" "bin" "nix" "scripts"
    "test" "priv" "native" "tooling/drop" "vendor/foundry-ledger"
    "docs" "research" "env.bl" "bl.lock" "flake.nix" "flake.lock"
    "rust-toolchain" "rust-toolchain.toml"
  ];
  input = import ./project-source.nix {
    inherit source;
    rootsJson = builtins.toJSON roots;
    excludedJson = builtins.toJSON [ "priv/native" "priv/z3" "priv/codegen.sources"
      "priv/precompiled.term" "priv/sdk-code.term" ];
  };
  lock = builtins.fromJSON (builtins.readFile (input + "/flake.lock"));
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
  selection = if sdk == null then import (input + "/nix/sdk-artifact.nix") {
    source = toString input;
    inherit previous;
  } else builtins.storePath sdk;
  bounded = import ./bounded-build.nix { inherit pkgs memoryMiB cpuCount; diskMiB = 24576; commandManager = true; };
in bounded (pkgs.runCommand "beam-lisp-ci-check" {
  nativeBuildInputs = [ pkgs.python3 pkgs.git pkgs.ripgrep pkgs.util-linux pkgs.nodejs ];
  allowedReferences = [];
} ''
  cp -a --no-preserve=ownership ${input}/. /build/project
  chmod -R u+w /build/project
  mkdir -p /usr/bin /bin /lib64
  test -e /usr/bin/env || ln -s ${pkgs.coreutils}/bin/env /usr/bin/env
  test -e /bin/sh || ln -s ${pkgs.bash}/bin/sh /bin/sh
  test -e /bin/bash || ln -s ${pkgs.bash}/bin/bash /bin/bash
  test -e /lib64/ld-linux-x86-64.so.2 || ln -s ${pkgs.glibc}/lib/ld-linux-x86-64.so.2 /lib64/ld-linux-x86-64.so.2
  export LD_LIBRARY_PATH=${pkgs.lib.makeLibraryPath [ pkgs.openssl pkgs.ncurses pkgs.zlib pkgs.glibc pkgs.stdenv.cc.cc.lib pkgs.brotli pkgs.zstd ]}
  export ELIXIR_ERL_OPTIONS='+fnu +S ${toString cpuCount}:${toString cpuCount} +SDcpu 1:1 +SDio 1:1'
  export HOME=/build/home GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null
  export CI_CHECK_SDK_RETAINED=${if sdk == null then "0" else "1"}
  mkdir -p "$HOME"
  cd /build/project
  python3 ${./../scripts/ci-check-worker.py} --sdk ${selection} --request ${/. + request} --root /build/project --out /build/raw-receipts
  python3 ${./../scripts/ci-receipt.py} --source /build/raw-receipts --out "$out"
'')
