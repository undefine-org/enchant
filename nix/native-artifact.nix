# Fixed trusted recipe. Requests carry data, never caller-supplied expressions.
{ requestJson }:
let
  # JSON is data. The source field re-enters Nix dependency tracking through
  # storePath/path below, including requests constructed by flake outputs.
  request = builtins.fromJSON (builtins.unsafeDiscardStringContext requestJson);
  legacy = request.version == 1;
  expected = if legacy then [ "abi" "crate" "source" "target" "version" ]
    else [ "abi" "crate" "member" "package" "source" "target" "version" ];
  validName = value: builtins.isString value && builtins.stringLength value <= 128 && builtins.match "[a-zA-Z_][a-zA-Z0-9_]*" value != null;
  lock = builtins.fromJSON (builtins.readFile ../flake.lock);
  nixpkgs = builtins.fetchTree lock.nodes.nixpkgs.locked;
  pkgs = import nixpkgs.outPath { system = request.target; };
  source = if builtins.match "/nix/store/[0-9a-z]{32}-[^/]+" request.source != null
    then builtins.storePath request.source
    else import ./native-source.nix {
      inherit (request) source crate version;
      member = request.member or ".";
      package = request.package or null;
    };
  workspace = if legacy then null else import ./native-workspace.nix {
    inherit source;
    inherit (request) member package;
  };
  manifest = if legacy then builtins.fromTOML (builtins.readFile (source + "/Cargo.toml"))
    else workspace.manifest;
  library = manifest.lib.name or (builtins.replaceStrings [ "-" ] [ "_" ] manifest.package.name);
  desktop = if legacy then request.crate == "wry_webview"
    else library == "wry_webview" || builtins.elem request.package [ "wry_webview" "wry-webview" ];
  compiledLibrary = if legacy then request.crate else library;
  memoryMiB = if desktop then 6144 else 3072;
  # Compile identity excludes the BL consumer's ABI label. Changing consumer
  # metadata must not compile the same Rust source/toolchain a second time.
  compiled = (import ./bounded-build.nix {
    inherit pkgs memoryMiB;
    diskMiB = if desktop then 16384 else 12288;
  }) (pkgs.rustPlatform.buildRustPackage ({
    pname = if legacy then "bl-native-code-${request.crate}" else "bl-native-code-${request.package}";
    version = if legacy then manifest.package.version else workspace.version;
    src = source;
    cargoLock.lockFile = source + "/Cargo.lock";
    doCheck = false;
    strictDeps = true;
    nativeBuildInputs = pkgs.lib.optionals desktop [ pkgs.pkg-config ];
    buildInputs = pkgs.lib.optionals desktop [ pkgs.gtk3 pkgs.webkitgtk_4_1 pkgs.gtk-layer-shell ];
    cargoBuildFlags = [ "--lib" ] ++ pkgs.lib.optionals (!legacy) [
      "--manifest-path" (if request.member == "." then "Cargo.toml" else request.member + "/Cargo.toml")
      "--package" request.package
    ];
    installPhase = ''
      runHook preInstall
      mkdir -p "$out/lib"
      install -m444 "target/${pkgs.stdenv.hostPlatform.rust.rustcTarget}/release/lib${library}.so" "$out/lib/${compiledLibrary}.so"
      runHook postInstall
    '';
    postInstall = ''
      printf '{"backend":"nix-kvm","memoryMiB":${toString memoryMiB},"memoryKiB":%s,"swapKiB":%s}\n' \
        "$BL_WORKER_MEMORY_KIB" "$BL_WORKER_SWAP_KIB" > "$out/worker.json"
    '';
  } // pkgs.lib.optionalAttrs (!legacy) {
    # A workspace's .cargo/config.toml must not redirect publication to an
    # undeclared target tree. Cargo still receives the selected member manifest.
    CARGO_TARGET_DIR = "target";
  }));
  product = pkgs.runCommand "bl-native-${request.crate}" {} ''
    mkdir -p "$out/lib"
    cp ${compiled}/lib/${compiledLibrary}.so "$out/lib/${request.crate}.so"
    digest=$(sha256sum "$out/lib/${request.crate}.so" | cut -d' ' -f1)
    cat > "$out/artifact.json" <<'MANIFEST'
    ${builtins.toJSON ({
      version = request.version;
      kind = "native-library";
      crate = request.crate;
      abi = request.abi;
      target = request.target;
      source = toString source;
      toolchain = {
        name = "rustc";
        version = pkgs.rustc.version;
        identity = builtins.hashString "sha256" (toString pkgs.rustc);
      };
      compiled = toString compiled;
      library = "lib/${request.crate}.so";
    } // pkgs.lib.optionalAttrs (!legacy) {
      inherit (request) member package;
      cargoLibrary = library;
    })}
    MANIFEST
    ${pkgs.jq}/bin/jq --arg digest "$digest" --slurpfile worker ${compiled}/worker.json \
      '. + {sha256: $digest, worker: $worker[0]}' "$out/artifact.json" > "$out/manifest.tmp"
    mv "$out/manifest.tmp" "$out/artifact.json"
  '';
in
assert builtins.attrNames request == expected;
assert builtins.isInt request.version && builtins.elem request.version [ 1 2 ];
assert validName request.crate;
assert builtins.isString request.abi && builtins.stringLength request.abi > 0 && builtins.stringLength request.abi <= 128;
assert builtins.isString request.source && builtins.substring 0 1 request.source == "/";
assert request.target == "x86_64-linux";
assert validName library;
assert !legacy || library == request.crate;
assert builtins.elem "cdylib" (manifest.lib.crate-type or []);
product
