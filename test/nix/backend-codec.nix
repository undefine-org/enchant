# One ordinary private compiler world qualifies the codec and Source policy.
{ sdk, source ? ../.. }:
let
  lock = builtins.fromJSON (builtins.readFile (source + "/flake.lock"));
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
  selection = builtins.storePath sdk;
  metadata = builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile (selection + "/artifact.json")));
  platform = builtins.storePath metadata.platform;
  compiler = builtins.storePath metadata.compiler;
  native = (import ../../nix/native-products.nix { inherit pkgs; root = source; }).bundle;
  inputs = pkgs.lib.fileset.toSource {
    root = source;
    fileset = pkgs.lib.fileset.unions (map (name: source + "/${name}") [
      "priv/lib/nix.bl" "priv/lib/nix/native.bl" "priv/lib/build/backend.bl"
      "test/scripts/nix_backend_codec.exs" "test/bl/nix_test.bl" "test/bl/build_backend_test.bl"
      "test/fixtures/nix/flake.nix" "tooling/build-backends" "flake.nix"
    ]);
  };
  bounded = import ../../nix/bounded-build.nix { inherit pkgs; memoryMiB = 3072; cpuCount = 2; trace = true; };
in bounded (pkgs.runCommand "beam-lisp-backend-codec-check" {} ''
  mkdir -p /usr/bin /bin "$TMPDIR/home"
  test -e /usr/bin/env || ln -s ${pkgs.coreutils}/bin/env /usr/bin/env
  test -e /bin/sh || ln -s ${pkgs.bash}/bin/sh /bin/sh
  image="$PWD/lib/beam_lisp-0.1.0"
  mkdir -p "$image/ebin"
  cp -a --no-preserve=ownership ${selection}/image/priv "$image/priv"
  chmod -R u+w "$image/priv"
  rm -f "$image/priv/precompiled.term" "$image/priv/sdk-code.term"
  rm -rf "$image/priv/parts"
  cp -a --no-preserve=ownership ${compiler}/seed/. "$image/ebin/"
  mkdir -p "$image/priv/lib/nix" "$image/priv/lib/build"
  cp ${inputs}/priv/lib/nix.bl "$image/priv/lib/nix.bl"
  cp ${inputs}/priv/lib/nix/native.bl "$image/priv/lib/nix/native.bl"
  cp ${inputs}/priv/lib/build/backend.bl "$image/priv/lib/build/backend.bl"
  ln -sfn ${native}/bl_nix.so "$image/priv/native/bl_nix.so"
  cp -a --no-preserve=ownership ${inputs}/. project
  chmod -R u+w project
  export HOME="$TMPDIR/home" XDG_CACHE_HOME="$TMPDIR/home/.cache"
  export BL_ROOT="$image" BL_CODEC_SDK=${selection} BL_CODEC_GENERATED="$out/generated"
  export BL_ARTIFACT_PLATFORM=${platform}/artifact-platform BL_PREPARED_NATIVES=${native}
  export BL_BIN=${platform}/bin/drop-launcher BL_DAEMON=off
  export ELIXIR_ERL_OPTIONS='+fnu +S 2:2 +SDcpu 1:1 +SDio 1:1'
  mkdir -p "$out"
  cd project
  if ! ${platform}/bin/elixir ${inputs}/test/scripts/nix_backend_codec.exs > "$out/check.log" 2>&1; then
    cat "$out/check.log"
    exit 1
  fi
  cat "$out/check.log"
  echo '{"status":"passed","scope":"private Source codec and backend world"}' > "$out/result.json"
'')
