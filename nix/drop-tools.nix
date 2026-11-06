# One immutable stock launcher/codec producer for checkout and release builds.
{ pkgs, root ? ../tooling/drop }:
(import ./bounded-build.nix { inherit pkgs; trace = true; }) (pkgs.rustPlatform.buildRustPackage {
  pname = "beam-lisp-drop-tools";
  version = "1";
  src = pkgs.lib.fileset.toSource {
    inherit root;
    fileset = pkgs.lib.fileset.unions [
      (root + "/Cargo.toml") (root + "/Cargo.lock") (root + "/src")
    ];
  };
  cargoLock.lockFile = root + "/Cargo.lock";
  cargoBuildFlags = [ "--bin" "drop-launcher" "--bin" "drop" ];
  doCheck = true;
  nativeCheckInputs = [ pkgs.python3 ];
  cargoTestFlags = [ "--bin" "drop-launcher" "checkout_tests::" ];
  # Store/build tests mutate process environment; keep the qualification serial.
  RUST_TEST_THREADS = "1";
  postCheck = ''
    for group in payload_cache_tests:: gc_tests::; do
      cargo test --release --target ${pkgs.stdenv.hostPlatform.rust.rustcTarget} \
        --offline --bin drop-launcher "$group"
    done
    python3 ${../test/scripts/test_engine_snapshot.py} \
      --launcher target/${pkgs.stdenv.hostPlatform.rust.rustcTarget}/release/drop-launcher \
      --reference ${../scripts/sdk-inputs}
  '';
  installPhase = ''
    mkdir -p "$out/bin"
    for executable in drop-launcher drop; do
      install -m555 target/${pkgs.stdenv.hostPlatform.rust.rustcTarget}/release/$executable "$out/bin/$executable"
    done
    ln -s drop-launcher "$out/bin/bl-command-executor"
  '';
  postFixup = ''
    digest=$(sha256sum "$out/bin/drop-launcher" | cut -d' ' -f1)
    printf '{"version":1,"protocol":"BEAM_LISP_CUSTODY_COMMAND_V1","sha256":"%s"}\n' "$digest" > "$out/executor.json"
  '';
})
