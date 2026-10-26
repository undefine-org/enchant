# A self-contained upstream input; private Git credentials are not build inputs.
let
  root = ../vendor/foundry-ledger;
  manifest = builtins.fromJSON (builtins.readFile (root + "/manifest.json"));
  expected = [ "bin/jobs.bl" "src/foundry/credentials/deployment-keyring.bl"
    "src/foundry/operations/deployment-runner.bl" "src/foundry/support/cli-kit.bl"
    "src/foundry/support/deployment-exec.bl" "src/foundry/support/deployment-runtime.bl"
    "src/foundry/support/deployment-tar.bl" ];
in
assert manifest.version == 1;
assert manifest.revision == "1e945f2aedcef4c26ccada8d8208bd76aecec4a7";
assert builtins.attrNames manifest.files == expected;
assert builtins.all (file: builtins.hashFile "sha256" (root + "/${file}") == manifest.files.${file}) expected;
root
