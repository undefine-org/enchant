# Cross products bind the Android library to the SDK's native source/interface.
# Call with the pinned Android SDK and Rust overlay from the consuming flake.
{ pkgs, sdk, rust-overlay, root ? ../. }:
let
  rustPkgs = pkgs.extend (import rust-overlay);
  rust = rustPkgs.rust-bin.stable."1.95.0".minimal.override {
    targets = [ "x86_64-linux-android" "aarch64-linux-android" ];
  };
  rustPlatform = pkgs.makeRustPlatform { cargo = rust; rustc = rust; };
  src = import ./native-source.nix { source = toString (root + "/native/lazy_memo"); crate = "lazy_memo"; };
  contractSource = pkgs.lib.fileset.toSource {
    inherit root;
    fileset = pkgs.lib.fileset.unions [
      (root + "/native/lazy_memo/Cargo.toml") (root + "/native/lazy_memo/Cargo.lock")
      (root + "/native/lazy_memo/build.rs") (root + "/native/lazy_memo/src")
      (root + "/priv/host/lazy_memo.bl") (root + "/nix/android-native-contract.py")
    ];
  };
  contract = pkgs.runCommand "bl-android-native-contract" { nativeBuildInputs = [ pkgs.python3 ]; } ''
    python3 ${contractSource}/nix/android-native-contract.py --root ${contractSource} > "$out"
  '';
  ndkBin = "${sdk}/libexec/android-sdk/ndk/27.2.12479018/toolchains/llvm/prebuilt/linux-x86_64/bin";
  compile = target: clang: (import ./bounded-build.nix {
    inherit pkgs;
    memoryMiB = 3072;
    cpuCount = 2;
  }) (pkgs.stdenv.mkDerivation {
    pname = "bl-android-lazy-memo-${target}";
    version = "1";
    inherit src;
    cargoDeps = rustPlatform.importCargoLock { lockFile = src + "/Cargo.lock"; };
    nativeBuildInputs = [ rust rustPlatform.cargoSetupHook pkgs.binutils ];
    buildPhase = ''
      export CARGO_TARGET_${pkgs.lib.toUpper (builtins.replaceStrings ["-"] ["_"] target)}_LINKER=${ndkBin}/${clang}
      cargo build --release --frozen --target ${target} -j "$NIX_BUILD_CORES"
    '';
    installPhase = ''
      mkdir -p "$out"
      install -m644 target/${target}/release/liblazy_memo.so "$out/liblazy_memo.so"
      readelf -h "$out/liblazy_memo.so" > "$out/elf.txt"
      printf '%s\n' "$BL_WORKER_MEMORY_KIB $BL_WORKER_SWAP_KIB" > "$out/worker.txt"
    '';
    dontFixup = true;
  });
  # Interface metadata belongs to the consumer product, outside Cargo's key.
  # Editing the facade's policy or ABI manifest never recompiles Rust.
  build = abi: target: clang:
    let compiled = compile target clang;
    in pkgs.runCommand "bl-android-lazy-memo-${abi}" { nativeBuildInputs = [ pkgs.jq ]; } ''
      mkdir -p "$out/${abi}"
      cp ${compiled}/liblazy_memo.so ${compiled}/elf.txt ${compiled}/worker.txt "$out/${abi}/"
      sha=$(sha256sum "$out/${abi}/liblazy_memo.so" | cut -d' ' -f1)
      jq --arg abi '${abi}' --arg target '${target}' --arg sha "$sha" \
        '. + {kind: "android-native-library", abi: $abi, target: $target, library: "liblazy_memo.so", sha256: $sha}' \
        ${contract} > "$out/${abi}/artifact.json"
    '';
  x86_64 = build "x86_64" "x86_64-linux-android" "x86_64-linux-android28-clang";
  arm64 = build "arm64-v8a" "aarch64-linux-android" "aarch64-linux-android28-clang";
in {
  inherit x86_64 arm64 contract;
  bundle = pkgs.linkFarm "bl-android-natives" [
    { name = "x86_64"; path = x86_64 + "/x86_64"; }
    { name = "arm64-v8a"; path = arm64 + "/arm64-v8a"; }
  ];
}
