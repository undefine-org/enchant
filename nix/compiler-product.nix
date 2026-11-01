# Each generation is retained independently. Qualification assembles verified
# outputs; retrying a later stage never discards an earlier successful stage.
{ pkgs, erlang, elixir, src, dependencies, checkoutPlatform, nativeProducts,
  previousCompiler ? null, previousSource ? null }:
let
  identity = builtins.hashString "sha256" (builtins.toJSON {
    source = toString src;
    inherit (builtins) nixVersion;
    erlang = toString erlang;
    elixir = toString elixir;
    dependencies = toString dependencies;
    platform = toString checkoutPlatform;
    natives = toString nativeProducts.bundle;
    recipe = builtins.readFile ./compiler-product.nix;
    worker = builtins.readFile ./bounded-build.nix;
  });
  previousIdentity = if previousCompiler != null
      && builtins.pathExists (previousCompiler + "/producer.json")
    then (builtins.fromJSON (builtins.readFile (previousCompiler + "/producer.json"))).identity
    else null;
  worker = import ./bounded-build.nix {
    inherit pkgs;
    memoryMiB = 6144;
    diskMiB = 32768;
    cpuCount = 4;
    commandManager = true;
  };
  generation = label: predecessor: worker (pkgs.stdenv.mkDerivation {
    pname = "beam-lisp-compiler-generation-${label}";
    version = "1";
    inherit src;
    nativeBuildInputs = [ erlang elixir pkgs.python3 pkgs.git ];
    dontConfigure = true;
    dontFixup = true;
    dontInstall = true;
    buildPhase = ''
      cp bin/bl-producer bin/bl
      export HOME=$TMPDIR/home XDG_CACHE_HOME=$TMPDIR/home/.cache BL_DAEMON=off
      mkdir -p "$HOME" "$XDG_CACHE_HOME/beam_lisp"
      cp -a --no-preserve=ownership ${dependencies}/ebin "$XDG_CACHE_HOME/beam_lisp/ebin"
      mkdir -p deps priv/native
      for dependency in ${dependencies}/ebin/*; do
        ln -s "$dependency" "deps/$(basename "$dependency")"
      done
      ${pkgs.lib.concatMapStringsSep "\n" (name: ''
        ln -sfn ${nativeProducts.bundle}/${name}.so priv/native/${name}.so
      '') nativeProducts.names}
      export BL_CHECKOUT_PLATFORM=${checkoutPlatform}
      export BL_ARTIFACT_PLATFORM=${checkoutPlatform}/artifact-platform
      ${pkgs.lib.optionalString (previousCompiler != null && previousSource != null) ''
        python3 scripts/compiler-unit-baseline.py --compiler ${previousCompiler} \
          --source ${previousSource} --current "$PWD" --out "$TMPDIR/baseline.json"
      ''}
      # The baseline is a prior qualified compiler for ALL three stages. In
      # particular C cannot fetch newly emitted B units as reproduction proof.
      python3 scripts/qualify-artifact-generation --root "$PWD" --out "$out" \
        --generation ${label} --producer-timeout 1200 --stream \
        ${pkgs.lib.optionalString (predecessor != null) "--seed ${predecessor}"} \
        ${pkgs.lib.optionalString (previousCompiler != null && previousSource != null)
          ''--baseline "$TMPDIR/baseline.json"''} \
        ${pkgs.lib.optionalString (previousCompiler != null) ''
          ${pkgs.lib.optionalString (builtins.pathExists (previousCompiler + "/unit-store"))
            "--previous-units ${previousCompiler}/unit-store"}
        ''}
    '';
  });
  p = generation "P" (if previousCompiler == null then null else previousCompiler + "/seed");
  b = generation "B" (p + "/P");
  c = generation "C" (b + "/B");
in if previousIdentity == identity then previousCompiler else
pkgs.runCommand "beam-lisp-compiler-1" { nativeBuildInputs = [ pkgs.python3 ]; } ''
  python3 ${src}/scripts/assemble-compiler-generations.py --products ${p} ${b} ${c} --out "$out"
  python3 - "$out" ${src}/scripts/check-produced-compiler.py <<'PY'
  import importlib.util, pathlib, sys
  spec = importlib.util.spec_from_file_location('proof', sys.argv[2])
  proof = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(proof)
  print(proof.verify_proof(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[1]) / 'seed'))
  PY
  cat > "$out/producer.json" <<'JSON'
  ${builtins.toJSON { version = 1; inherit identity; source = toString src; }}
  JSON
''
