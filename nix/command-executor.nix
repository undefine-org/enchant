# A stock launcher supplies the pre-BEAM custody protocol without a BL VM.
{ pkgs }:
pkgs.rustPlatform.buildRustPackage {
  pname = "beam-lisp-command-executor";
  version = "1";
  src = pkgs.lib.fileset.toSource { root = ../tooling/drop; fileset = ../tooling/drop; };
  cargoLock.lockFile = ../tooling/drop/Cargo.lock;
  cargoBuildFlags = [ "--bin" "drop-launcher" ];
  doCheck = false;
  installPhase = ''
    mkdir -p "$out/bin"
    install -m555 target/${pkgs.stdenv.hostPlatform.rust.rustcTarget}/release/drop-launcher "$out/bin/bl-command-executor"
  '';
  postFixup = ''
    digest=$(sha256sum "$out/bin/bl-command-executor" | cut -d' ' -f1)
    printf '{"version":1,"protocol":"BEAM_LISP_CUSTODY_COMMAND_V1","sha256":"%s"}\n' "$digest" > "$out/executor.json"
  '';
}
