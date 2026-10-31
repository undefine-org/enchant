{ diagnostic ? false }:
let
  root = /home/othman/code/undefine/beam-lisp--execution-protocol;
  lock = builtins.fromJSON (builtins.readFile (root + "/flake.lock"));
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
  beam = import (root + "/nix/beam.nix") {
    inherit pkgs;
    otp-src = (builtins.fetchTree lock.nodes.otp-src.locked).outPath;
    elixir-src = (builtins.fetchTree lock.nodes.elixir-src.locked).outPath;
  };
  products = import (root + "/nix/bl-drop.nix") {
    inherit pkgs;
    rustPkgs = pkgs;
    inherit (beam) erlang elixir;
    includeDesktop = true;
  };
  image = products.sdk-image;
  debug = pkgs.lib.overrideDerivation image (old: {
    buildPhase = builtins.replaceStrings [ "./bin/bl --cold run scripts/produce-sdk.bl" ] [ ''
      ${pkgs.python3}/bin/python3 - <<'PATCH'
      from pathlib import Path
      path = Path('scripts/produce-sdk.bl')
      source = path.read_text()
      old = '(throw (ex-info "Immutable SDK production failed" {:errors (:errors result)}))'
      new = '(throw (ex-info (str "Immutable SDK production failed: " (pr-str (:errors result))) {}))'
      assert old in source
      path.write_text(source.replace(old, new))
      PATCH
      ./bin/bl --cold run scripts/produce-sdk.bl
    '' ] old.drvAttrs.buildPhase;
  });
in if diagnostic then debug else image
