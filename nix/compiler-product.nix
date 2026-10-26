# The existing artifact-only producer emits B, B emits C, and the existing
# independent fresh-boot checks qualify both. No manifest is rewritten by Nix.
{ pkgs, erlang, elixir, src, dependencies, checkoutPlatform, nativeProducts }:
(import ./bounded-build.nix {
  inherit pkgs;
  memoryMiB = 6144;
  diskMiB = 32768;
  cpuCount = 4;
  commandManager = true;
}) (pkgs.stdenv.mkDerivation {
  pname = "beam-lisp-compiler";
  version = "1";
  inherit src;
  nativeBuildInputs = [ erlang elixir pkgs.python3 pkgs.git ];
  dontConfigure = true;
  dontFixup = true;
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
    python3 scripts/qualify-artifact-generation --root "$PWD" --out "$TMPDIR/reproduction"
    ${pkgs.jq}/bin/jq -e \
      '.self_reproduction_qualified == true and .changed_files == [] and (.stages | length) == 2 and all(.stages[]; .produced and .fresh_boot_qualified)' \
      "$TMPDIR/reproduction/result.json"
  '';
  installPhase = ''
    mkdir -p "$out/seed" "$out/qualification"
    cp -a --no-preserve=ownership "$TMPDIR/reproduction/C/." "$out/seed/"
    cp "$TMPDIR/reproduction/"*.json "$TMPDIR/reproduction/"*.log "$out/qualification/"
  '';
})
