# Same immutable native SDK and six real units on each provider. The label
# forces a fresh derivation; it is never passed to the compiler. Timings stay
# in build logs, and the outputs contain only reproducible target artifacts.
{ sdk, label }:
let
  lock = builtins.fromJSON (builtins.readFile ../../flake.lock);
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
  selection = builtins.storePath sdk;
  metadata = builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile (selection + "/artifact.json")));
  platform = builtins.storePath metadata.platform;
  bounded = import ../../nix/bounded-build.nix {
    inherit pkgs; memoryMiB = 3072; diskMiB = 8192; cpuCount = 4; trace = true;
  };
  boot = pkgs.writeText "producer-probe.exs" ''
    for path <- Path.wildcard("${selection}/lib/*/ebin"), do: Code.prepend_path(path)
    :code.del_path(~c".")
    BeamLisp.Launcher.start_app!(["--cold", "run", "${../fresh-preparation/probe.bl}"], %{})
  '';
in bounded (pkgs.runCommand "beam-lisp-producer-probe-${label}" {} ''
  mkdir -p /usr/bin /bin "$TMPDIR/home"
  test -e /usr/bin/env || ln -s ${pkgs.coreutils}/bin/env /usr/bin/env
  test -e /bin/sh || ln -s ${pkgs.bash}/bin/sh /bin/sh
  export HOME="$TMPDIR/home" XDG_CACHE_HOME="$TMPDIR/home/.cache"
  export BL_ROOT=${selection}/image BL_SDK_PRODUCT=${selection} BL_BIN=${selection}/bin/bl
  export BL_ARTIFACT_PLATFORM=${platform}/artifact-platform BL_PREPARED_NATIVES=${platform}/native-products
  export BL_DAEMON=off PERF_TRACE=0 PERF_OUT="$out/units"
  export PERF_NAMES=errors,proc.queue,reload.generation,datom.conn,bl.cli,build
  export ELIXIR_ERL_OPTIONS='+S 4:4 +SDcpu 2:2 +SDio 1:1'
  ${pkgs.time}/bin/time -v ${platform}/bin/elixir ${boot}
'')
