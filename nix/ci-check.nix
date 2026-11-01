# Execute a finite check where the retained SDK lives; return only receipts.
# Existing SDK selection is optional. The default uses the ordinary SDK recipe.
{ source, request, sdk ? null, previous ? null, models ? null, memoryMiB ? 6144, cpuCount ? 2 }:
let
  root = /. + source;
  roots = builtins.filter (name: builtins.pathExists (root + "/${name}")) [
    ".gitignore" ".github" "AGENTS.md" "README.md" "README.bl.org" "examples" "bin" "nix" "scripts"
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
  requestData = builtins.fromJSON (builtins.readFile (/. + request));
  prerequisites = (builtins.fromJSON (builtins.readFile (input + "/scripts/test-prerequisites.json"))).tests;
  selectedFiles = if requestData.kind == "shard" then builtins.attrNames prerequisites else requestData.files;
  tools = pkgs.lib.unique (pkgs.lib.concatMap (name:
    let entry = prerequisites.${name} or {}; in (entry.all or []) ++ (entry.linux or [])
  ) selectedFiles);
  toolPackages = { cargo = pkgs.cargo; rustc = pkgs.rustc; inotifywait = pkgs.inotify-tools;
    ssh = pkgs.openssh; ssh-keygen = pkgs.openssh; tesseract = pkgs.tesseract;
    rsvg-convert = pkgs.librsvg; ldd = pkgs.glibc.bin; };
  nativeFixture = builtins.elem "test/bl/execution_qualification_test.bl" selectedFiles;
  # E50 compiles two private Rustler variants with --offline. Retain the same
  # lock-addressed vendor input used by native-compile.nix, without compiling
  # the SDK/native producer again or relying on a developer Cargo registry.
  fixtureCargoDeps = pkgs.rustPlatform.importCargoLock {
    lockFile = pkgs.writeText "native-Cargo.lock" (builtins.unsafeDiscardStringContext
      (builtins.readFile (input + "/native/lazy_memo/Cargo.lock")));
  };
  # The SDK platform supplies the exact Erlang/Elixir, Nix and user-manager
  # tools. Add only the remaining declared external test tools here.
  fixtureTools = map (name: toolPackages.${name}) (builtins.filter (name: builtins.hasAttr name toolPackages) tools)
    ++ pkgs.lib.optionals nativeFixture [ pkgs.stdenv.cc ];
  selection = if sdk == null then import (input + "/nix/sdk-artifact.nix") {
    source = toString input;
    inherit previous;
  } else builtins.storePath sdk;
  bounded = import ./bounded-build.nix { inherit pkgs memoryMiB cpuCount; diskMiB = 24576; commandManager = true; };
in bounded (pkgs.runCommand "beam-lisp-ci-check" {
  __structuredAttrs = true;
  nativeBuildInputs = [ pkgs.python3 pkgs.git pkgs.ripgrep pkgs.util-linux pkgs.nodejs ] ++ fixtureTools;
  outputChecks.out.allowedReferences = [];
} ''
  cp -a --no-preserve=ownership ${input}/. /build/project
  chmod -R u+w /build/project
  mkdir -p /usr/bin /bin /lib64 /etc/ssl/certs
  test -e /usr/bin/env || ln -s ${pkgs.coreutils}/bin/env /usr/bin/env
  test -e /bin/sh || ln -s ${pkgs.bash}/bin/sh /bin/sh
  test -e /bin/bash || ln -s ${pkgs.bash}/bin/bash /bin/bash
  test -e /lib64/ld-linux-x86-64.so.2 || ln -s ${pkgs.glibc}/lib/ld-linux-x86-64.so.2 /lib64/ld-linux-x86-64.so.2
  # OTP's public_key.cacerts_get/0 uses the operating system's trust store even
  # when a connector's served fixture is HTTP. Keep normal TLS verification.
  ln -s ${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt /etc/ssl/certs/ca-certificates.crt
  export LD_LIBRARY_PATH=${pkgs.lib.makeLibraryPath [ pkgs.openssl pkgs.ncurses pkgs.zlib pkgs.glibc pkgs.stdenv.cc.cc.lib pkgs.brotli pkgs.zstd ]}
  export ELIXIR_ERL_OPTIONS='+fnu +S ${toString cpuCount}:${toString cpuCount} +SDcpu 1:1 +SDio 1:1'
  export HOME=/build/home GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null
  export CI_CHECK_SDK_RETAINED=${if sdk == null then "0" else "1"}
  ${pkgs.lib.optionalString (models != null) ''
    export BEAM_LISP_MODEL_DIR=${builtins.storePath models}
  ''}
  mkdir -p "$HOME"
  ${pkgs.lib.optionalString nativeFixture ''
    export CARGO_HOME="$HOME/.cargo"
    mkdir -p "$CARGO_HOME"
    cat > "$CARGO_HOME/config.toml" <<'CARGO'
    [source.crates-io]
    replace-with = "ci-pinned-vendor"
    [source.ci-pinned-vendor]
    directory = "${fixtureCargoDeps}"
    CARGO
  ''}
  cd /build/project
  # The VM's user manager needs uid 0, but ordinary filesystem checks must
  # observe permission bits just as developer commands do. Keep the manager
  # and remove only the capabilities that bypass discretionary file access.
  setpriv --bounding-set=-dac_override,-dac_read_search --no-new-privs \
    python3 ${./../scripts/ci-check-worker.py} --sdk ${selection} --request ${/. + request} --root /build/project --out /build/raw-receipts
  python3 ${./../scripts/ci-receipt.py} --source /build/raw-receipts --out "$out"
'')
