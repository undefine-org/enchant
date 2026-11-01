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
{ pkgs, rustPkgs, erlang, elixir, includeDesktop ? false, previousSdk ? null, previousPreparation ? null }:
let
  inherit (pkgs) lib;

  sources = import ./producer-sources.nix { inherit lib; };
  previousMetadata = if previousSdk == null then null else
    builtins.fromJSON (builtins.unsafeDiscardStringContext
      (builtins.readFile (previousSdk + "/artifact.json")));
  previousPlatform = if previousMetadata == null then null else
    builtins.fromJSON (builtins.unsafeDiscardStringContext
      (builtins.readFile (builtins.storePath previousMetadata.platform + "/platform.json")));

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
  compilerNatives = { names = [ "lazy_memo" ]; bundle = import ./native-bundle.nix {
    inherit pkgs;
    products = { inherit (nativeProducts.products) lazy_memo; };
  }; };
  compilerPlatform = import ./checkout-platform.nix {
    inherit pkgs erlang elixir;
    executor = drop-tools;
    nativeProducts = { inherit (nativeProducts.products) lazy_memo; };
    includeRecipes = false;
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
      ../scripts/produce-sdk.bl
      ../scripts/qualify-artifact-generation
      ../scripts/demo-artifact-production
      ../scripts/check-source-floor
      ../scripts/check-execution-history
      ../nix/android-native-contract.py
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
      mkdir -p priv/android
      ${pkgs.python3}/bin/python3 nix/android-native-contract.py --root "$PWD" > priv/android/native-contract.json

  '';
  workerFor = trace: import ./bounded-build.nix {
    inherit pkgs trace;
    memoryMiB = 6144;
    diskMiB = 32768;
    cpuCount = 4;
    commandManager = true;
  };
  worker = workerFor false;
  producerTools = [ erlang elixir pkgs.patchelf pkgs.binutils pkgs.unzip pkgs.git pkgs.gnutar pkgs.gzip pkgs.findutils ];
  previousUnits = if previousMetadata == null then null else
    builtins.storePath (previousMetadata.image or (toString previousSdk)) + "/unit-store";
  previousUnitArchive = if previousUnits != null
      && builtins.pathExists (previousUnits + "/unit-index.json")
    then import ./sdk-unit-archive.nix { inherit pkgs; units = previousUnits; }
    else null;

  dependencies = worker (pkgs.runCommand "beam-lisp-dependencies-1" {
    nativeBuildInputs = producerTools;
  } ''
    export HOME=$TMPDIR/home XDG_CACHE_HOME=$TMPDIR/home/.cache BL_DAEMON=off
    export LANG=C.UTF-8 ELIXIR_ERL_OPTIONS='+S 4:4 +SDcpu 2:2 +SDio 1:1'
    export BL_ROOT=/build/dependency-tool/lib/beam_lisp-0.1.0
    export BL_DEPENDENCY_SOURCE=${sources.dependencies}
    export BL_DEPENDENCY_NATIVE=${nativeProducts.products.lazy_memo}/lib/lazy_memo.so
    export RUSTLER_PRECOMPILED_GLOBAL_CACHE_PATH=$TMPDIR/rp-cache
    export EXPLORER_USE_LEGACY_ARTIFACTS=false
    mkdir -p "$HOME" "$XDG_CACHE_HOME/beam_lisp" "$RUSTLER_PRECOMPILED_GLOBAL_CACHE_PATH"
    cp ${explorerNif} "$RUSTLER_PRECOMPILED_GLOBAL_CACHE_PATH/libexplorer-v0.12.0-nif-2.15-x86_64-unknown-linux-gnu.so.tar.gz"
    cp ${ratatuiNif} "$RUSTLER_PRECOMPILED_GLOBAL_CACHE_PATH/libex_ratatui-v0.13.0-nif-2.17-x86_64-unknown-linux-gnu.so.tar.gz"
    cp -a ${hexStore} "$XDG_CACHE_HOME/beam_lisp/lib"
    chmod -R u+w "$XDG_CACHE_HOME/beam_lisp/lib"
    mkdir -p "$BL_ROOT"
    cd "$BL_ROOT"
    ${elixir}/bin/elixir ${../scripts/produce-dependencies.exs}
    mkdir -p "$out"
    cp -aL --no-preserve=ownership "$XDG_CACHE_HOME/beam_lisp/ebin" "$out/ebin"
  '');
  compiler = import ./compiler-product.nix {
    inherit previousPreparation;
    inherit pkgs erlang elixir dependencies;
    src = sources.compiler;
    checkoutPlatform = compilerPlatform;
    nativeProducts = compilerNatives;
    previousCompiler = if previousMetadata == null then null else builtins.storePath previousMetadata.compiler;
    previousSource = if previousMetadata == null then null else builtins.storePath previousMetadata.source;
    cacheCompatible = previousPlatform != null
      && previousPlatform.erlang == toString erlang
      && previousPlatform.elixir == toString elixir
      && previousMetadata.dependencies == toString dependencies;
  };

  # 3. the bl build + self-build + ELF retarget. Compiles no Rust: NIFs and the
  # launcher come from the two derivations above.
  bl-drop = workerFor true (pkgs.stdenv.mkDerivation {
    pname = "bl-drop";
    version = "0.1.0";
    outputs = [ "out" "sdk" ];
    inherit src;
    nativeBuildInputs = producerTools;
    dontConfigure = true;
    dontFixup = true; # the drop is one opaque file

    buildPhase = ''
      sdk_phase_start() {
        sdk_phase_label=$1
        sdk_phase_started=$(date +%s%N)
      }
      sdk_phase_end() {
        local elapsed=$(( ($(date +%s%N) - sdk_phase_started) / 1000 ))
        printf 'SDK-SHELL-PHASE {"stage":"%s","elapsed-us":%s}\n' "$sdk_phase_label" "$elapsed"
      }
      sdk_phase_start setup
    '' + setupTree + ''
      sdk_phase_end
      runHook preBuild
      rm -rf "$XDG_CACHE_HOME/beam_lisp/ebin"
      cp -a --no-preserve=ownership ${dependencies}/ebin "$XDG_CACHE_HOME/beam_lisp/ebin"
      rm -rf priv/bootstrap/seed build .bl/lib/beam_lisp-0.1.0
      mkdir -p priv/bootstrap/seed build
      cp -a --no-preserve=ownership ${compiler}/seed/. priv/bootstrap/seed/
      # This worker already has the complete qualified floor. Host-only staging
      # would leave boot namespaces absent and trigger a second boot compiler.
      cp -a --no-preserve=ownership ${compiler}/seed/. build/
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

      export BL_PRODUCTION_LAUNCHER=${drop-tools}/bin/drop-launcher
      export BL_PRODUCTION_PACKER=$TMPDIR/drop
      export BL_PRODUCTION_DROP_OUTPUT=$TMPDIR/selfbuilt.drop
      export BL_PRODUCTION_PAYLOAD=$TMPDIR/payload
      export BL_PRODUCTION_UNIT_STORE=$TMPDIR/unit-store
      ${lib.optionalString (previousUnitArchive != null) ''
        sdk_phase_start materialize-previous-units
        mkdir -p "$TMPDIR/previous-units"
        tar -xzf ${previousUnitArchive}/units.tar.gz -C "$TMPDIR/previous-units"
        export BL_PREVIOUS_UNIT_STORE="$TMPDIR/previous-units"
        sdk_phase_end
      ''}
      # Preparation, floor validation and assembly share one producer VM.
      sdk_phase_start producer
      ./bin/bl --cold run scripts/produce-sdk.bl
      sdk_phase_end

      sdk_phase_start copy-sdk-image
      chmod -R u+w $TMPDIR/payload
      # Keep the Nix-linked SDK before portable ELF retargeting. Its receiver
      # checks the existing sealed metadata and actual bytes at load time.
      mkdir -p "$sdk"
      cp -a --no-preserve=ownership "$TMPDIR/unit-store" "$sdk/unit-store"
      cp -a --no-preserve=ownership $TMPDIR/payload/lib "$sdk/lib"
      for application in "$sdk"/lib/beam_lisp-*; do
        ln -s "lib/$(basename "$application")" "$sdk/image"
      done
      cp $TMPDIR/selfbuilt.drop "$sdk/bl"
      chmod 555 "$sdk/bl"
      mkdir -p "$sdk/bin"
      cat > "$sdk/boot.exs" <<EOF
      # The platform owns the running Elixir installation and its CLI scripts.
      # The portable payload's ebin-only copy must not shadow that installation.
      elixir_ebin = :code.lib_dir(:elixir, :ebin)
      for path <- Path.wildcard("$sdk/lib/*/ebin"), do: Code.prepend_path(path)
      Code.prepend_path(elixir_ebin)
      Code.prepend_path("$sdk/image/ebin")
      :code.del_path(~c".")
      BeamLisp.Launcher.start_app!(System.argv(), %{})
      EOF
      cat > "$sdk/bin/bl" <<EOF
      #!${pkgs.runtimeShell}
      unset BL_INTERNAL_PRODUCER
      export PATH=${buildCheckout}/bin:\$PATH
      export BL_ARTIFACT_PLATFORM=${buildCheckout}/artifact-platform
      export BL_PREPARATION_COORDINATOR=${coordinator}
      export BL_SDK_PRODUCT="$sdk"
      export BL_ROOT="$sdk/image" BL_EBIN="$sdk/image/ebin" BL_BUILD_ID=src BEAM_LISP_DEV=0
      export BL_BIN=${buildCheckout}/bin/drop-launcher
      export BL_PREPARED_NATIVES="$(readlink -f ${buildCheckout}/native-products)"
      exec ${buildCheckout}/bin/elixir "$sdk/boot.exs" "\$@"
      EOF
      chmod 555 "$sdk/bin/bl"
      printf '%s\n' '${builtins.toJSON {
        version = 1;
        kind = "sdk";
        producerAPI = 2;
        compiler = toString compiler;
        dependencies = toString dependencies;
        platform = toString buildCheckout;
        coordinator = toString coordinator;
        target = "x86_64-linux";
      }}' > "$sdk/artifact.json"
      ${pkgs.jq}/bin/jq --arg release "$out" --arg source "$src" \
        '. + {release: $release, source: $source}' "$sdk/artifact.json" > "$sdk/artifact.tmp"
      mv "$sdk/artifact.tmp" "$sdk/artifact.json"
      sdk_phase_end
      sdk_phase_start portable-retarget
      # A portable drop carries bytes rather than references to its build store.
      for native in $TMPDIR/payload/lib/beam_lisp-*/priv/native/*.so; do
        if [ -L "$native" ]; then
          cp --dereference "$native" "$native.materialized"
          mv "$native.materialized" "$native"
        fi
      done
      ${pkgs.python3}/bin/python3 - <<'PORTABLE'
      import json, os
      from pathlib import Path
      import subprocess
      patcher = '${pkgs.patchelf}/bin/patchelf'
      counts = dict(files=0, elf=0, interpreters=0)
      for path in (Path(os.environ['TMPDIR']) / 'payload').rglob('*'):
          if path.is_symlink() or not path.is_file():
              continue
          counts['files'] += 1
          with path.open('rb') as stream:
              marker = stream.read(4)
              first = marker + stream.readline(4092) if marker.startswith(b'#!') else marker
          if marker == b'\x7fELF':
              counts['elf'] += 1
              dynamic = subprocess.run([patcher, '--print-interpreter', path],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
              if dynamic:
                  subprocess.run([patcher, '--set-interpreter', '/lib64/ld-linux-x86-64.so.2',
                                  '--remove-rpath', path], check=True)
              else:
                  subprocess.run([patcher, '--remove-rpath', path],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
          elif first.startswith(b'#!') and b'/nix/store/' in first:
              interpreter = first.strip().split()[0].rsplit(b'/', 1)[-1]
              if interpreter not in (b'sh', b'bash', b'dash'):
                  raise SystemExit(f'undeclared portable interpreter: {path}: {first!r}')
              replacement = b'#!/bin/bash\n' if interpreter == b'bash' else b'#!/bin/sh\n'
              path.write_bytes(replacement + path.read_bytes()[len(first):])
              counts['interpreters'] += 1
      print('PORTABLE-PAYLOAD ' + json.dumps(counts), flush=True)
      PORTABLE
      sdk_phase_end
      sdk_phase_start pack-portable
      $TMPDIR/drop pack --release $TMPDIR/payload --launcher $TMPDIR/launcher --out $TMPDIR/bl.drop
      sdk_phase_end
      runHook postBuild
    '';

    installPhase = ''
      runHook preInstall
      mkdir -p $out
      cp $TMPDIR/bl.drop $out/bl.drop
      digest=$(sha256sum "$out/bl.drop" | cut -d' ' -f1)
      printf '%s\n' '${builtins.toJSON {
        version = 1;
        kind = "release";
        packaging = "portable-shell-v1";
        target = "x86_64-linux";
        compiler = toString compiler;
        file = "bl.drop";
      }}' > "$out/artifact.json"
      ${pkgs.jq}/bin/jq --arg sha "$digest" '. + {sha256: $sha}' \
        "$out/artifact.json" > "$out/artifact.tmp"
      mv "$out/artifact.tmp" "$out/artifact.json"
      runHook postInstall
    '';
  });
  # SDK bytes depend on their producer inputs; command/coordinator recipes are
  # selection data. Provider-only edits can select the same qualified payload.
  assemblyIdentity = builtins.hashString "sha256" (builtins.toJSON {
    source = toString src;
    compiler = toString compiler;
    dependencies = toString dependencies;
    natives = toString natives;
    executor = toString drop-tools;
    erlang = toString erlang;
    elixir = toString elixir;
    z3 = toString z3Runtime;
    explorer = toString explorerNif;
    terminal = toString ratatuiNif;
    toolchain = toString pkgs.path;
    recipe = builtins.readFile ./bl-drop.nix;
    unitArchive = builtins.readFile ./sdk-unit-archive.nix;
    worker = builtins.readFile ./bounded-build.nix;
  });
  reuseAssembly = previousMetadata != null
    && (previousMetadata.assemblyIdentity or null) == assemblyIdentity;
  image = if reuseAssembly then builtins.storePath previousMetadata.image else bl-drop.sdk;
  portable = if reuseAssembly then builtins.storePath previousMetadata.release else bl-drop;
  coordinator = import ./coordinator-runtime.nix {
    inherit pkgs;
    # The control plane boots a matching, already qualified runtime. Submitting
    # a target compiler build must never require building that target first.
    compiler = if previousMetadata == null then compiler else builtins.storePath previousMetadata.compiler;
    dependencies = if previousMetadata == null then dependencies else builtins.storePath previousMetadata.dependencies;
    source = if previousMetadata == null then src else builtins.storePath previousMetadata.source;
    platform = buildCheckout;
  };
  selection = import ./sdk-selection.nix {
    inherit pkgs coordinator image assemblyIdentity;
    release = portable;
    platform = buildCheckout;
  };
in
{ inherit drop-tools natives dependencies compiler coordinator;
  bl-drop = portable;
  sdk = selection;
  sdk-image = image;
}
