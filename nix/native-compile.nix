# Cache compiled Cargo dependencies independently of the selected crate's body.
# The real crate is always built from the complete captured Source. Only the
# preparatory dependency build sees stubs, and none of its selected-crate
# artifacts can cross into the real build.
{ pkgs, source, manifest, version, package, library, flags, desktop, memoryMiB }:
let
  lib = pkgs.lib;
  member = flags.member;
  prefix = if member == "." then "" else member + "/";
  within = parent: child: parent == "" || parent == child || lib.hasPrefix (parent + "/") child;
  packages = relative:
    let
      directory = source + (if relative == "" then "" else "/${relative}");
      entries = builtins.readDir directory;
      cargo = directory + "/Cargo.toml";
      own = lib.optional (builtins.pathExists cargo
        && (builtins.fromTOML (builtins.readFile cargo)) ? package) relative;
    in own ++ lib.concatMap (name:
      if entries.${name} == "directory" && !(builtins.elem name [ "target" ".git" ".bl" ])
      then packages (if relative == "" then name else relative + "/" + name) else []) (builtins.attrNames entries);
  others = builtins.filter (name: name != (if member == "." then "" else member)) (packages "");
  sourceText = toString source;
  skeleton = builtins.path {
    name = "native-dependency-inputs";
    path = source;
    filter = path: type:
      let relative = lib.removePrefix (sourceText + "/") (toString path);
          selected = within (if member == "." then "" else member) relative
            && !(builtins.any (other: within other relative) others);
      in type == "directory" || !(selected && lib.hasSuffix ".rs" relative);
  };
  buildScript = manifest.package.build or
    (if builtins.pathExists (source + "/${prefix}build.rs") then "build.rs" else false);
  paths = pkgs.writeText "native-stub-paths.json" (builtins.toJSON {
    library = prefix + (manifest.lib.path or "src/lib.rs");
    build = if builtins.isString buildScript then prefix + buildScript else null;
  });
  dummy = pkgs.runCommand "native-dependency-source" { nativeBuildInputs = [ pkgs.python3 ]; } ''
    mkdir -p "$out"
    cp -a --no-preserve=ownership ${skeleton}/. "$out/"
    chmod -R u+w "$out"
    python3 - "$out" ${paths} <<'PY'
    import json, pathlib, sys
    root = pathlib.Path(sys.argv[1]).resolve()
    paths = json.loads(pathlib.Path(sys.argv[2]).read_text())
    for name, contents in [('library', ""), ('build', 'fn main() {}\n')]:
        if paths[name] is None:
            continue
        target = (root / paths[name]).resolve()
        if not target.is_relative_to(root):
            raise SystemExit('native target escapes captured source')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents)
    PY
  '';
  # Retain lock bytes as their own input. The enclosing source store address
  # must not change dependency compilation or vendoring when a body changes.
  lockContents = builtins.unsafeDiscardStringContext (builtins.readFile (source + "/Cargo.lock"));
  lock = pkgs.writeText "native-Cargo.lock" lockContents;
  # Parse the captured bytes without realizing the writeText derivation during
  # evaluation. Keep that same lock-file input in the vendor derivation, so its
  # existing identity and compiled dependency cache remain unchanged.
  cargoDeps = (pkgs.rustPlatform.importCargoLock.override {
    lib = lib // {
      readFile = path: if toString path == toString lock then lockContents else lib.readFile path;
    };
  }) { lockFile = lock; };
  common = {
    pname = "bl-native-code-${package}";
    inherit version;
    cargoLock.lockFile = lock;
    inherit cargoDeps;
    CARGO_TARGET_DIR = "target";
    doCheck = false;
    strictDeps = true;
    # cargoSetup copies vendored sources without preserving timestamps. Keep
    # those inputs at the store epoch so imported fingerprints stay fresh.
    postPatch = ''
      find "../$(stripHash "$cargoDeps")" -exec touch -h -d @1 {} +
    '';
    nativeBuildInputs = lib.optionals desktop [ pkgs.pkg-config ];
    buildInputs = lib.optionals desktop [ pkgs.gtk3 pkgs.webkitgtk_4_1 pkgs.gtk-layer-shell ];
    cargoBuildFlags = [ "--lib" ] ++ lib.optionals flags.workspace [
      "--manifest-path" (if member == "." then "Cargo.toml" else member + "/Cargo.toml")
      "--package" package
    ];
  } // lib.optionalAttrs flags.workspace {
    # Local Cargo package identities include their physical workspace path.
    # Give dependency and final builds the same root as well as the same bytes.
    postUnpack = ''
      mv "$sourceRoot" source
      sourceRoot=source
    '';
  };
  bounded = import ./bounded-build.nix {
    inherit pkgs memoryMiB;
    commandManager = true;
    diskMiB = if desktop then 16384 else 12288;
  };
  artifacts = bounded (pkgs.rustPlatform.buildRustPackage (common // {
    pname = "bl-native-dependencies-${package}";
    src = dummy;
    dontFixup = true;
    installPhase = ''
      mkdir -p "$out"
      cp -a --no-preserve=ownership target "$out/target"
      package=${lib.escapeShellArg package}
      library=${lib.escapeShellArg library}
      for directory in "$out"/target/*/release "$out"/target/release; do
        # Cargo's ordinary mtime freshness must never adopt a stub, even when
        # unpacking gives the real and dummy source identical timestamps.
        rm -rf "$directory/.fingerprint/$package-"* "$directory/build/$package-"*
        rm -f "$directory/lib$library".* "$directory/deps/lib$library"* "$directory/deps/$library-"*
      done
    '';
  }));
in bounded (pkgs.rustPlatform.buildRustPackage (common // {
  src = source;
  preBuild = ''
    mkdir -p target
    cp -a ${artifacts}/target/. target/
    chmod -R u+w target
  '';
  installPhase = ''
    runHook preInstall
    mkdir -p "$out/lib"
    install -m444 "target/${pkgs.stdenv.hostPlatform.rust.rustcTarget}/release/lib${library}.so" "$out/lib/${library}.so"
    runHook postInstall
  '';
  postInstall = ''
    printf '{"backend":"nix-kvm","memoryMiB":${toString memoryMiB},"memoryKiB":%s,"swapKiB":%s}\n' \
      "$BL_WORKER_MEMORY_KIB" "$BL_WORKER_SWAP_KIB" > "$out/worker.json"
  '';
}))
