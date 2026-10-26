# The self-contained `bl` drop, built entirely inside nix (no network, no Mix).
#
# It runs the same sequence as .github/workflows/release.yml's linux leg
# (deps -> prepare natives/app -> qualified floor check -> z3 -> self-build), with inputs pinned and fetched
# by nix: hex tarballs (bl.lock digests), crates (Cargo.lock, vendored), the
# pinned z3 zip and explorer's precompiled NIF. The toolchain (OTP 29, Elixir
# 1.20, rustc, gcc) comes from the pinned nixpkgs, so every ELF the drop carries
# is linked against THAT glibc. docs/native-bundler.md, "Nix-built server drop".
#
# Final step: ELF files are rewritten to the FHS loader (/lib64/ld-linux-x86-64.so.2)
# with no RUNPATH, so the drop does not depend on /nix/store paths existing on
# the target. On NixOS that loader is nix-ld's, which resolves libc from the HOST:
# the host's glibc must therefore be >= the drop's symbol floor, which is the point.
{ pkgs, rustPkgs, erlang, elixir, includeDesktop ? false }:
let
  inherit (pkgs) lib;

  # ── hex libraries, exactly the digests bl.lock names ─────────────────────────
  lockLines = lib.filter (l: lib.hasPrefix "[:dep " l) (lib.splitString "\n" (builtins.readFile ../bl.lock));
  hexDeps = map
    (l:
      let m = builtins.match "[[]:dep ([^ ]+) ([^ ]+) ([0-9a-f]+) hex[]]" l; in
      assert m != null;
      rec {
        name = builtins.elemAt m 0;
        vsn = builtins.elemAt m 1;
        sha = builtins.elemAt m 2;
        tarball = pkgs.fetchurl {
          url = "https://repo.hex.pm/tarballs/${name}-${vsn}.tar";
          sha256 = sha;
        };
      })
    lockLines;
  # the store layout `bl deps` reads: <name>-<vsn>-<sha8>/ + .hex-sha
  hexStore = pkgs.runCommand "bl-hex-store" { } ''
    mkdir -p $out
    ${lib.concatMapStringsSep "\n" (d: ''
      d=$out/${d.name}-${d.vsn}-${builtins.substring 0 8 d.sha}
      t=$(mktemp -d)
      mkdir -p $d
      tar -xf ${d.tarball} -C $t
      tar -xzf $t/contents.tar.gz -C $d
      printf %s ${d.sha} > $d/.hex-sha
      rm -rf $t
    '') hexDeps}
  '';

  # Shared with the automatic checkout prerequisites and command executor.
  drop-tools = import ./drop-tools.nix { inherit pkgs; };
  nativeCrates = nativeProducts.names;

  # 2. Independent verified native products, also consumed by interactive builds.
  nativeProducts = import ./native-products.nix { inherit pkgs includeDesktop; };
  natives = nativeProducts.bundle;
  buildPlatform = import ./artifact-platform.nix { inherit pkgs; commandExecutor = drop-tools; };
  buildCheckout = import ./checkout-platform.nix {
    inherit pkgs erlang elixir;
    executor = drop-tools;
    inherit includeDesktop;
  };

  # ── pinned binary assets ─────────────────────────────────────────────────────
  z3 = pkgs.fetchurl {
    url = "https://github.com/Z3Prover/z3/releases/download/z3-4.16.0/z3-4.16.0-x64-glibc-2.39.zip";
    sha256 = "7288c49a5bd6dbafd7b0b0d1f65956b91672da24b08f09242919af159be3418e";
  };
  z3Runtime = import ./z3-runtime.nix { inherit pkgs; archive = z3; };
  # explorer's polars NIF (rustler_precompiled), the non-legacy-CPU build; its
  # sha256 is the one explorer's own checksum file pins. glibc floor 2.35.
  explorerNif = pkgs.fetchurl {
    url = "https://github.com/elixir-explorer/explorer/releases/download/v0.12.0/libexplorer-v0.12.0-nif-2.15-x86_64-unknown-linux-gnu.so.tar.gz";
    sha256 = "4315e0dcc03fdd48e4861c5ea02ccf3e65a0a7a2646fad0c57367d1c6eb68114";
  };

  # The SDK's terminal seam is also a Rustler precompiled dependency. Seed its
  # locked-package checksum explicitly: an ordinary derivation must not need
  # Rustler to reach GitHub during `bl deps compile`.
  ratatuiNif = pkgs.fetchurl {
    url = "https://github.com/mcass19/ex_ratatui/releases/download/v0.13.0/libex_ratatui-v0.13.0-nif-2.17-x86_64-unknown-linux-gnu.so.tar.gz";
    sha256 = "95a23a060aadc58adea3fefd724dc7bb8ad4aead3152fac0ee62f130fe510320";
  };

  # The checkout, as the build needs it. wry_webview (gtk/webkit, desktop only)
  # is left out of server products; the managed checkout SDK includes it.
  cleanDirectory = directory: omitted:
    lib.fileset.difference directory
      (lib.fileset.unions (map (name: lib.fileset.maybeMissing (directory + "/${name}")) omitted));
  src = lib.fileset.toSource {
    root = ../.;
    fileset = lib.fileset.unions [
      ../bin
      (cleanDirectory ../priv [ "native" "z3" ".bl" "codegen.sources" "precompiled.term" "sdk-code.term" ])
      ../env.bl ../bl.lock
      ../scripts/prepare-release.bl
      ../scripts/qualify-artifact-generation
      ../scripts/demo-artifact-production
      ../scripts/check-source-floor
      ../scripts/check-execution-history
      ../test/scripts/artifact-generation.bl
      (lib.fileset.unions (map (crate:
        cleanDirectory (../native + "/${crate}") [ "target" ".git" ".bl" ]) nativeCrates))
      ../tooling/drop/src ../tooling/drop/Cargo.toml ../tooling/drop/Cargo.lock
    ];
  };

  setupTree = ''
      export HOME=$TMPDIR/home XDG_CACHE_HOME=$TMPDIR/home/.cache
      export BL_DAEMON=off LANG=C.UTF-8 ELIXIR_ERL_OPTIONS="+fnu"
      export BL_NATIVE_PROVIDER=nix BL_PREPARED_NATIVES=${natives}
      export BL_ARTIFACT_PLATFORM=${buildPlatform} BL_BIN=${drop-tools}/bin/drop-launcher
      export BL_CHECKOUT_PLATFORM=${buildCheckout}
      export RUSTLER_PRECOMPILED_GLOBAL_CACHE_PATH=$TMPDIR/rp-cache
      export EXPLORER_USE_LEGACY_ARTIFACTS=false
      mkdir -p $HOME $XDG_CACHE_HOME/beam_lisp $RUSTLER_PRECOMPILED_GLOBAL_CACHE_PATH

      cp ${explorerNif} $RUSTLER_PRECOMPILED_GLOBAL_CACHE_PATH/libexplorer-v0.12.0-nif-2.15-x86_64-unknown-linux-gnu.so.tar.gz
      cp ${ratatuiNif} $RUSTLER_PRECOMPILED_GLOBAL_CACHE_PATH/libex_ratatui-v0.13.0-nif-2.17-x86_64-unknown-linux-gnu.so.tar.gz
      cp -r ${hexStore} $XDG_CACHE_HOME/beam_lisp/lib
      chmod -R u+w $XDG_CACHE_HOME/beam_lisp/lib

      # the writable working copy bin/bl builds inside (it links .bl/ + build/ into the tree)
      cp -r $src $TMPDIR/tree && chmod -R u+w $TMPDIR/tree
      cd $TMPDIR/tree
      # The closed Nix recipe bootstraps its producers directly. Ordinary
      # checkout entry instead selects the completed immutable SDK.
      cp bin/bl-producer bin/bl
      patchShebangs bin

      # the one native the boot itself needs (see release.yml "Bootstrap the native crates")
      mkdir -p priv/native
      for crate in ${toString nativeCrates}; do
        install -m755 ${natives}/$crate.so priv/native/$crate.so
      done

  '';
  worker = import ./bounded-build.nix {
    inherit pkgs;
    memoryMiB = 6144;
    diskMiB = 32768;
    cpuCount = 4;
    commandManager = true;
  };
  producerTools = [ erlang elixir pkgs.patchelf pkgs.binutils pkgs.unzip pkgs.git pkgs.gnutar pkgs.gzip pkgs.findutils ];

  dependencies = worker (pkgs.stdenv.mkDerivation {
    pname = "beam-lisp-dependencies";
    version = "1";
    inherit src;
    nativeBuildInputs = producerTools;
    dontConfigure = true;
    dontFixup = true;
    buildPhase = setupTree + ''
      ./bin/bl deps verify --cold
      ./bin/bl deps compile --cold
    '';
    installPhase = ''
      mkdir -p "$out"
      cp -a --no-preserve=ownership "$XDG_CACHE_HOME/beam_lisp/ebin" "$out/ebin"
    '';
  });
  compiler = import ./compiler-product.nix {
    inherit pkgs erlang elixir src dependencies;
    checkoutPlatform = buildCheckout;
    nativeProducts = nativeProducts;
  };

  # 3. the bl build + self-build + ELF retarget. Compiles no Rust: NIFs and the
  # launcher come from the two derivations above.
  bl-drop = worker (pkgs.stdenv.mkDerivation {
    pname = "bl-drop";
    version = "0.1.0";
    outputs = [ "out" "sdk" ];
    inherit src;
    nativeBuildInputs = producerTools;
    dontConfigure = true;
    dontFixup = true; # the drop is one opaque file

    buildPhase = setupTree + ''
      runHook preBuild
      rm -rf "$XDG_CACHE_HOME/beam_lisp/ebin"
      cp -a --no-preserve=ownership ${dependencies}/ebin "$XDG_CACHE_HOME/beam_lisp/ebin"
      rm -rf priv/bootstrap/seed build .bl/lib/beam_lisp-0.1.0
      mkdir -p priv/bootstrap/seed
      cp -a --no-preserve=ownership ${compiler}/seed/. priv/bootstrap/seed/
      ./bin/bl --cold run scripts/prepare-release.bl
      # Package the source-validated compiler floor. Compiler regeneration is
      # a bare-VM operation, independent of the runtime's retained SDK lease.
      ./bin/bl --cold seed --check

      # pinned z3, laid out as `bl install z3` leaves it
      mkdir -p priv/z3/bin
      cp ${z3Runtime}/bin/z3 ${z3Runtime}/bin/libz3.so priv/z3/bin/
      cp ${z3Runtime}/LICENSE.txt priv/z3/
      echo 7288c49a5bd6dbafd7b0b0d1f65956b91672da24b08f09242919af159be3418e > priv/z3/.fetched

      # the launcher the target executes: FHS loader, no store RUNPATH
      cp ${drop-tools}/bin/drop-launcher $TMPDIR/launcher
      cp ${drop-tools}/bin/drop $TMPDIR/drop
      chmod u+w $TMPDIR/launcher
      patchelf --set-interpreter /lib64/ld-linux-x86-64.so.2 --remove-rpath $TMPDIR/launcher

      ./bin/bl --cold self-build --reuse-floor --bin ${drop-tools}/bin/drop-launcher --out $TMPDIR/selfbuilt.drop --jobs $NIX_BUILD_CORES

      # unpack, retarget every ELF at the FHS loader, repack with the same launcher
      $TMPDIR/drop unpack $TMPDIR/selfbuilt.drop --dir $TMPDIR/payload
      chmod -R u+w $TMPDIR/payload
      # Keep the Nix-linked SDK before portable ELF retargeting. Its receiver
      # checks the existing sealed metadata and actual bytes at load time.
      mkdir -p "$sdk"
      cp -a --no-preserve=ownership $TMPDIR/payload/lib "$sdk/lib"
      for application in "$sdk"/lib/beam_lisp-*; do
        ln -s "lib/$(basename "$application")" "$sdk/image"
      done
      cp $TMPDIR/selfbuilt.drop "$sdk/bl"
      chmod 555 "$sdk/bl"
      mkdir -p "$sdk/bin"
      cat > "$sdk/bin/bl" <<EOF
      #!${pkgs.runtimeShell}
      export PATH=${buildCheckout}/bin:\$PATH
      export BL_ARTIFACT_PLATFORM=${buildCheckout}/artifact-platform
      exec "$sdk/bl" "\$@"
      EOF
      chmod 555 "$sdk/bin/bl"
      printf '%s\n' '${builtins.toJSON {
        version = 1;
        kind = "sdk";
        compiler = toString compiler;
        dependencies = toString dependencies;
        platform = toString buildCheckout;
        target = "x86_64-linux";
      }}' > "$sdk/artifact.json"
      # A portable drop carries bytes rather than references to its build store.
      for native in $TMPDIR/payload/lib/beam_lisp-*/priv/native/*.so; do
        if [ -L "$native" ]; then
          cp --dereference "$native" "$native.materialized"
          mv "$native.materialized" "$native"
        fi
      done
      find $TMPDIR/payload -type f | while read -r f; do
        if [ "$(head -c4 "$f" | od -An -c | tr -d ' ')" = '177ELF' ]; then
          if patchelf --print-interpreter "$f" >/dev/null 2>&1; then
            patchelf --set-interpreter /lib64/ld-linux-x86-64.so.2 --remove-rpath "$f"
          else
            patchelf --remove-rpath "$f" 2>/dev/null || true
          fi
        fi
      done
      $TMPDIR/drop pack --release $TMPDIR/payload --launcher $TMPDIR/launcher --out $TMPDIR/bl.drop
      runHook postBuild
    '';

    installPhase = ''
      runHook preInstall
      mkdir -p $out
      cp $TMPDIR/bl.drop $out/bl.drop
      runHook postInstall
    '';
  });
in
{ inherit bl-drop drop-tools natives dependencies compiler; sdk = bl-drop.sdk; }
