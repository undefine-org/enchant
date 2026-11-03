# The self-contained `bl` drop and SDK, built with the pinned Nix toolchain.
# The portable drop uses the host's FHS loader and runtime libraries. Its
# measured glibc requirement is recorded in the release requirements receipt;
# see docs/native-bundler.md. The SDK retains its pinned Nix runtime.
#
# This repository's lock owns the toolchain independently of host deployments.
{
  description = "beam-lisp: incremental SDK and qualified Linux drop";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/6510408d147d8c5e6d76043e899e9251756f6a75";
    # The host pin now supplies a sufficiently recent Rust toolchain too.
    # Keep this name for the build interface, without a second libc/toolchain pin.
    nixpkgs-rust.follows = "nixpkgs";
    # Keep the language's tested OTP/Elixir versions independent of nixpkgs defaults.
    # Both are built with the host pin's toolchain and glibc.
    otp-src = { url = "github:erlang/otp/OTP-29.0.1"; flake = false; };
    elixir-src = { url = "github:elixir-lang/elixir/v1.20.4"; flake = false; };
  };

  outputs = { self, nixpkgs, nixpkgs-rust, otp-src, elixir-src }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
      beam = import ./nix/beam.nix { inherit pkgs otp-src elixir-src; };
      rustPkgs = nixpkgs-rust.legacyPackages.${system};
      drop = import ./nix/bl-drop.nix {
        inherit pkgs rustPkgs;
        inherit (beam) erlang elixir;
        # The public SDK has the same native profile as checkout preparation.
        includeDesktop = builtins.pathExists (self + "/native/wry_webview/Cargo.toml");
      };
      nativeProducts = import ./nix/native-products.nix { inherit pkgs; root = self; };
    in
    {
      nixosModules.artifacts = import ./nix/artifact-host.nix;
      nixosModules.artifact-workstation = { config, ... }: {
        imports = [ ./nix/artifact-host.nix ];
        services.beam-lisp-artifacts.enable = true;
        assertions = [{
          assertion = config.services.beam-lisp-artifacts.buildStation != null;
          message = "Supply services.beam-lisp-artifacts.buildStation from the local workstation description.";
        }];
      };
      # A module factory: callers pass their local station description.
      lib.artifact-workstation = import ./nix/workstation-artifacts.nix;
      packages.${system} = {
        artifact-platform = import ./nix/artifact-platform.nix { inherit pkgs; };
        command-executor = import ./nix/command-executor.nix { inherit pkgs; };
        checkout-platform = import ./nix/checkout-platform.nix {
          inherit pkgs;
          inherit (beam) erlang elixir;
          root = self;
        };
        native-products = nativeProducts.bundle;
        native-bl-json = nativeProducts.products.bl_json;
        native-code-embed = nativeProducts.products.code_embed;
        native-datom-datalog = nativeProducts.products.datom_datalog;
        native-datom-fjall = nativeProducts.products.datom_fjall;
        native-datom-vector = nativeProducts.products.datom_vector;
        native-wry-webview = import ./nix/native-artifact.nix {
          requestJson = builtins.toJSON {
            version = 1;
            crate = "wry_webview";
            source = toString (self + "/native/wry_webview");
            abi = "beam-lisp-native-wry_webview-v1";
            target = system;
          };
        };
        inherit (beam) erlang elixir;
        bl-drop = drop.bl-drop;
        compiler = drop.compiler;
        sdk = drop.sdk;
        dependencies = drop.dependencies;
        drop-tools = drop.drop-tools;
        native-lazy-memo = import ./nix/native-artifact.nix {
          requestJson = builtins.toJSON {
            version = 1;
            crate = "lazy_memo";
            source = toString (self + "/native/lazy_memo");
            abi = "beam-lisp-native-lazy_memo-v1";
            target = system;
          };
        };
        default = drop.bl-drop;
      };

      # `nix flake check` — the gate (CI runs it too). Fails loudly when the build
      # or its contract (runs with the pinned adapter; glibc floor <= 2.44) breaks.
      checks.${system} = {
        # Run the unchanged FHS-targeted artifact even in a strict Nix sandbox.
        drop-runs = import ./nix/drop-runs.nix { inherit pkgs; drop = drop.bl-drop; };
        glibc-floor = pkgs.runCommand "bl-glibc-floor" { nativeBuildInputs = [ pkgs.binutils pkgs.findutils ]; } ''
          export DROP_BIN=${drop.drop-tools}/bin/drop
          got=$(sh ${./tooling/drop/glibc-floor.sh} ${drop.bl-drop}/bl.drop)
          echo "$got"
          v=$(echo "$got" | cut -d' ' -f1)
          [ "$(printf '%s\n2.44\n' "$v" | sort -V | tail -1)" = 2.44 ] \
            || { echo "glibc floor $v > 2.44 (the release ABI ceiling)" >&2; exit 1; }
          touch $out
        '';
      };
    };
}
