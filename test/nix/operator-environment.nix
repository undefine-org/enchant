# Current client Source in a fresh compiler world, separate from SDK admission.
{ sdk, source ? ../.. }:
let
  lock = builtins.fromJSON (builtins.readFile (source + "/flake.lock"));
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
  selection = builtins.storePath sdk;
  metadata = builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile (selection + "/artifact.json")));
  platform = builtins.storePath metadata.platform;
  compiler = builtins.storePath metadata.compiler;
  inputs = pkgs.lib.fileset.toSource {
    root = source;
    fileset = pkgs.lib.fileset.unions (map (name: source + "/${name}") [
      "priv/build/artifact-process.bl" "priv/build/artifact-jobs.bl" "priv/build/artifact.bl"
      "test/scripts/operator_environment.exs"
    ]);
  };
  bounded = import ../../nix/bounded-build.nix { inherit pkgs; memoryMiB = 2048; cpuCount = 2; trace = true; };
in bounded (pkgs.runCommand "beam-lisp-operator-environment-check" {} ''
  mkdir -p /usr/bin /bin "$TMPDIR/home"
  test -e /usr/bin/env || ln -s ${pkgs.coreutils}/bin/env /usr/bin/env
  test -e /bin/sh || ln -s ${pkgs.bash}/bin/sh /bin/sh
  export HOME="$TMPDIR/home" XDG_CACHE_HOME="$TMPDIR/home/.cache"
  image="$PWD/lib/beam_lisp-0.1.0"
  mkdir -p "$image/ebin"
  cp -a --no-preserve=ownership ${selection}/image/priv "$image/priv"
  chmod -R u+w "$image/priv"
  rm -f "$image/priv/precompiled.term" "$image/priv/sdk-code.term"
  rm -rf "$image/priv/parts"
  cp -a --no-preserve=ownership ${compiler}/seed/. "$image/ebin/"
  for name in artifact-process artifact-jobs artifact; do
    cp ${inputs}/priv/build/$name.bl "$image/priv/build/$name.bl"
  done
  export BL_ROOT="$image" BL_POLICY_SDK=${selection}
  export BL_ARTIFACT_PLATFORM=${platform}/artifact-platform
  export ELIXIR_ERL_OPTIONS='+fnu +S 2:2 +SDcpu 1:1 +SDio 1:1'
  mkdir -p "$out"
  ${platform}/bin/elixir ${inputs}/test/scripts/operator_environment.exs > "$out/result.json"
'')
