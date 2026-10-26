# A runtime consumes the same per-crate manifests as an interactive preparation.
{ pkgs, products, target ? "x86_64-linux" }:
let names = builtins.attrNames products;
in
assert target == "x86_64-linux";
assert names != [];
assert builtins.all (name: builtins.match "[a-zA-Z_][a-zA-Z0-9_]*" name != null) names;
pkgs.runCommand "beam-lisp-server-natives" {} ''
  mkdir -p "$out" rows
  ${pkgs.lib.concatMapStringsSep "\n" (name: ''
    product=${products.${name}}
    test -f "$product/lib/${name}.so"
    test ! -L "$product/lib/${name}.so"
    digest=$(sha256sum "$product/lib/${name}.so" | cut -d' ' -f1)
    ${pkgs.jq}/bin/jq -e --arg crate ${name} --arg target ${target} --arg digest "$digest" \
      '(.version == 1 or .version == 2) and .kind == "native-library" and .crate == $crate and .target == $target and .library == ("lib/" + $crate + ".so") and .sha256 == $digest' \
      "$product/artifact.json" > /dev/null
    ln -s "$product/lib/${name}.so" "$out/${name}.so"
    ${pkgs.jq}/bin/jq --arg output "$product" '. + {output: $output}' \
      "$product/artifact.json" > rows/${name}.json
  '') names}
  ${pkgs.jq}/bin/jq -s \
    '{version: 1, kind: "native-set", target: "${target}", products: (map({key: .crate, value: .}) | from_entries)}' \
    rows/*.json > "$out/artifacts.json"
''
