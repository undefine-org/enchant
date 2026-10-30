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
  rawManifest = if legacy then builtins.fromTOML (builtins.readFile (source + "/Cargo.toml"))
    else workspace.manifest;
  manifest = builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.toJSON rawManifest));
  library = manifest.lib.name or (builtins.replaceStrings [ "-" ] [ "_" ] manifest.package.name);
  desktop = if legacy then request.crate == "wry_webview"
    else library == "wry_webview" || builtins.elem request.package [ "wry_webview" "wry-webview" ];
  memoryMiB = if desktop then 6144 else 3072;
  # Compile identity excludes the BL consumer's ABI label. Changing consumer
  # metadata must not compile the same Rust source/toolchain a second time.
  compiled = import ./native-compile.nix {
    inherit pkgs source manifest library desktop memoryMiB;
    package = manifest.package.name;
    flags = { workspace = !legacy; member = request.member or "."; };
  };
  product = pkgs.runCommand "bl-native-${request.crate}" {} ''
    mkdir -p "$out/lib"
    cp ${compiled}/lib/${library}.so "$out/lib/${request.crate}.so"
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
