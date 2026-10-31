{ answer ? 42, mode ? "normal", token ? "stable" }:
let
  busy = builtins.storePath "/nix/store/r6zw8gd10c7qv9sifzg4r7h1s5qmrxjp-busybox-1.37.0";
  core = builtins.storePath "/nix/store/2gfxiwls9hbgwdwcy43mprchwsq36mg6-coreutils-9.11";
  rust = builtins.storePath "/nix/store/53lvgpxsb3b9ghkgb4v0jra6zzlnyw8n-rustc-1.98.1";
  cargo = builtins.storePath "/nix/store/gmgfpzc0w2pgby0lmq9r88m39albiyfw-cargo-1.98.1";
  cc = builtins.storePath "/nix/store/788mx070y81zjlg5ipcl0cra3afviw9k-gcc-wrapper-15.2.0";
in assert builtins.isInt answer && answer >= 0 && answer <= 1000;
assert builtins.elem mode [ "normal" "slow" "fail" "descendant" "isolation" ];
builtins.derivation {
  name = "bl-nix-execution-probe-${mode}";
  system = "x86_64-linux";
  builder = "${busy}/bin/sh";
  PATH = "${core}/bin:${busy}/bin:${cargo}/bin:${rust}/bin:${cc}/bin";
  inherit token;
  args = [ "-eu" "-c" ''
    echo PROTOTYPE_BUILD_STARTED
    ${if mode == "isolation" then ''
      test ! -e /home/othman/projects/nix-execution-prototype/host-canary
    '' else ""}
    export HOME="$TMPDIR/home" CARGO_HOME="$TMPDIR/cargo" CARGO_NET_OFFLINE=true
    mkdir -p "$HOME" "$CARGO_HOME" src "$out"
    cat > Cargo.toml <<'EOF'
    [package]
    name="execution_probe"
    version="0.0.0"
    edition="2021"
    [lib]
    crate-type=["cdylib"]
    [workspace]
    EOF
    cat > Cargo.lock <<'EOF'
    version=4
    [[package]]
    name="execution_probe"
    version="0.0.0"
    EOF
    echo '#[no_mangle] pub extern "C" fn answer() -> u32 { ${toString answer} }' > src/lib.rs
    cargo build --release --offline --locked --target-dir "$TMPDIR/target"
    cp "$TMPDIR/target/release/libexecution_probe.so" "$out/libprobe.so"
    echo '{"schema":1,"answer":${toString answer},"target":"x86_64-linux"}' > "$out/manifest.json"
    ${if mode == "slow" then "sleep 5" else ""}
    ${if mode == "fail" then "echo deliberate-failure >&2; exit 23" else ""}
    ${if mode == "descendant" then ''
      # This child intentionally retains no extra lease descriptor. It must not
      # be able to write the published result after the builder exits.
      (exec 3>&- 4>&- 5>&- 6>&- 7>&- 8>&- 9>&-; echo ready > "$out/child-ready"; sleep 2; echo escaped > "$out/late-write") </dev/null >/dev/null 2>&1 &
      echo "$!" > "$out/child-pid"
      kill -0 "$!"
      while [ ! -f "$out/child-ready" ]; do sleep 0.01; done
    '' else ""}
  '' ];
}
