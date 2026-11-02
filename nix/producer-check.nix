# The real receiver/negative controls execute on the configured Nix builder.
{ sdk, source ? ../. }:
let
  lock = builtins.fromJSON (builtins.readFile (source + "/flake.lock"));
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
  files = [ "scripts/retain-producer.bl" "scripts/restore-producer.exs"
            "test/scripts/retained_producer_cache.py" "test/scripts/retained_producer_cache.exs" ];
  inputs = pkgs.lib.fileset.toSource {
    root = source;
    fileset = pkgs.lib.fileset.unions (map (name: source + "/${name}") files);
  };
  worker = import ./bounded-build.nix {
    inherit pkgs; memoryMiB = 2048; diskMiB = 16384; cpuCount = 2;
    commandManager = false; trace = true;
  };
in worker (pkgs.runCommand "beam-lisp-producer-cache-check" {
  nativeBuildInputs = [ pkgs.python3 ];
} ''
  export HOME="$TMPDIR/home" XDG_CACHE_HOME="$TMPDIR/home/.cache"
  mkdir -p "$HOME"
  python3 ${inputs}/test/scripts/retained_producer_cache.py --sdk ${builtins.storePath sdk} --out "$TMPDIR/probe"
  mkdir -p "$out"
  cp "$TMPDIR/probe/result.json" "$TMPDIR/probe/retain.log" "$TMPDIR/probe/receive.log" "$out/"
'')
