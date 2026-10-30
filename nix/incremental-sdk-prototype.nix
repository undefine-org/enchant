# Opt-in experiment: a sealed SDK fragment, using an already qualified compiler.
# Refuse compiler/driver edits instead of silently reusing a foreign generation.
{ sdk, source, selectionJson, previous ? null, reproduction ? false }:
let
  lock = builtins.fromJSON (builtins.readFile ../flake.lock);
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
  base = builtins.storePath sdk;
  metadata = builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile (base + "/artifact.json")));
  original = /. + metadata.source;
  root = /. + source;
  # Conservative prototype boundary. The toolchain, host runtime, build driver,
  # prelude, project declaration and lock must all match the qualified baseline.
  compilerSource = tree: pkgs.lib.fileset.toSource {
    root = tree;
    fileset = pkgs.lib.fileset.unions (map (name: tree + "/${name}") [
      "priv/boot" "priv/host" "priv/build" "priv/bootstrap" "priv/std/multi.bl"
      "env.bl" "bl.lock"
    ]);
  };
  compilerUnchanged = toString (compilerSource root) == toString (compilerSource original);
  selection = builtins.fromJSON selectionJson;
  relative = path: builtins.isString path && pkgs.lib.hasPrefix "priv/" path
    && builtins.all (part: part != "" && part != "." && part != "..") (pkgs.lib.splitString "/" path);
  # Capture only the explicit overlay. Everything else comes from base, so an
  # unselected edit cannot accidentally influence a unit in this experiment.
  overlay = pkgs.lib.fileset.toSource {
    root = root;
    fileset = pkgs.lib.fileset.unions (map (name: root + "/${name}") selection);
  };
  request = pkgs.writeText "incremental-sdk-request.json" (builtins.toJSON {
    inherit selection;
    compiler = metadata.compiler;
    dependencies = metadata.dependencies;
    baseline = sdk;
    previous = if previous == null then null else toString (builtins.storePath previous);
  });
  compiler = builtins.storePath metadata.compiler;
  platform = builtins.storePath metadata.platform;
  product = (import ./bounded-build.nix {
    inherit pkgs;
    memoryMiB = 4096;
    diskMiB = 16384;
    cpuCount = 4;
    commandManager = true;
  }) (pkgs.runCommand "beam-lisp-incremental-sdk-prototype" {
    # A second independent realization for the reproducibility control. This
    # value is never read by the producer or included in emitted artifacts.
    BL_INCREMENTAL_REPRODUCTION = if reproduction then "1" else "0";
  } ''
    export HOME=/build/home XDG_CACHE_HOME=/build/home/.cache BL_DAEMON=off
    export LANG=C.UTF-8 ELIXIR_ERL_OPTIONS='+S 4:4 +SDcpu 2:2 +SDio 1:1'
    export BL_ROOT=/build/sdk/lib/beam_lisp-0.1.0
    export BL_INCREMENTAL_BASE=${base} BL_INCREMENTAL_REQUEST=${request}
    export BL_INCREMENTAL_OUTPUT="$out"
    mkdir -p "$BL_ROOT" "$HOME" "$XDG_CACHE_HOME"
    cp -a --no-preserve=ownership ${base}/image/priv "$BL_ROOT/priv"
    chmod -R u+w "$BL_ROOT"
    rm -f "$BL_ROOT/priv/sdk-code.term" "$BL_ROOT/priv/precompiled.term"
    cp -a --no-preserve=ownership ${compiler}/seed "$BL_ROOT/ebin"
    chmod -R u+w "$BL_ROOT/ebin"
    cp -a --no-preserve=ownership ${overlay}/priv/. "$BL_ROOT/priv/"
    cd "$BL_ROOT"
    ${platform}/bin/elixir ${../scripts/incremental-sdk-worker.exs}
  '');
in
assert metadata.kind == "sdk" && metadata.version == 1;
assert builtins.isBool reproduction;
assert builtins.isList selection && selection != [] && builtins.all relative selection;
assert pkgs.lib.assertMsg compilerUnchanged "incremental SDK prototype: compiler/driver inputs changed; qualify a new compiler first";
{
  inherit product;
  compiler = builtins.storePath metadata.compiler;
  dependencies = builtins.storePath metadata.dependencies;
}
