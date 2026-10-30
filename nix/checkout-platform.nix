# Pinned prerequisites selected before starting a checkout VM.
{ pkgs, erlang, elixir, executor ? import ./command-executor.nix { inherit pkgs; },
  root ? ../., includeDesktop ? builtins.pathExists (root + "/native/wry_webview/Cargo.toml"),
  nativeProducts ? null, includeRecipes ? true }:
let
  recipes = import ./artifact-platform.nix { inherit pkgs includeRecipes; commandExecutor = executor; };
  server = import ./native-products.nix { inherit pkgs root; };
  products = if nativeProducts != null then nativeProducts else server.products // pkgs.lib.optionalAttrs includeDesktop {
    wry_webview = import ./native-artifact.nix {
    requestJson = builtins.toJSON {
      version = 1;
      crate = "wry_webview";
      source = toString (root + "/native/wry_webview");
      abi = "beam-lisp-native-wry_webview-v1";
      target = "x86_64-linux";
    };
    };
  };
  native = products.lazy_memo;
  bundle = import ./native-bundle.nix { inherit pkgs products; };
in pkgs.runCommand "beam-lisp-checkout-platform" {} ''
  mkdir -p "$out/bin"
  ln -s ${executor}/bin/bl-command-executor "$out/bin/drop-launcher"
  ln -s ${executor}/bin/bl-command-executor "$out/bin/bl-command-executor"
  for executable in ${erlang}/bin/* ${elixir}/bin/*; do
    test -e "$out/bin/$(basename "$executable")" || ln -s "$executable" "$out/bin/$(basename "$executable")"
  done
  for executable in ${pkgs.nix}/bin/*; do
    ln -s "$executable" "$out/bin/$(basename "$executable")"
  done
  ln -s ${pkgs.systemd}/bin/systemd-run "$out/bin/systemd-run"
  ln -s ${pkgs.systemd}/bin/systemctl "$out/bin/systemctl"
  ln -s ${recipes} "$out/artifact-platform"
  ln -s ${native} "$out/lazy_memo"
  ln -s ${bundle} "$out/native-products"
  printf '%s\n' '${builtins.toJSON {
    version = 1;
    kind = "checkout-platform";
    target = "x86_64-linux";
    native = toString native;
    recipes = toString recipes;
    erlang = toString erlang;
    elixir = toString elixir;
    executor = toString executor;
  }}' > "$out/platform.json"
''
