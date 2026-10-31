# One immutable stock launcher/codec producer for checkout and release builds.
{ pkgs, root ? ../tooling/drop }:
(import ./bounded-build.nix { inherit pkgs; }) (pkgs.rustPlatform.buildRustPackage {
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
  doCheck = false;
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
