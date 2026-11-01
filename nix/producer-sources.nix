# Separate compilation inputs from the complete deployable SDK payload.
{ lib, root ? ../. }:
let
  source = names: lib.fileset.toSource {
    inherit root;
    fileset = lib.fileset.unions (map (name: root + "/${name}") names);
  };
in {
  dependencies = source ([ "priv/bootstrap/seed" "bl.lock" ] ++ map
    (name: "priv/build/${name}.bl")
    [ "deps" "deps-compile" "store" "hex" "drop" "release" "claim"
      "app-resource" "substrate" "mix-shim" ]);
  compiler = source [
    "priv/boot" "priv/host" "priv/self" "priv/bootstrap/seed" "priv/build"
    "priv/std/multi.bl" "priv/std/bl/env.bl.md" "priv/std/bl/util.bl.md"
    "priv/std/bl/loading-policy.bl" "priv/std/bl/native-declarations.bl"
    "priv/std/proc/owner-registry.bl" "priv/std/vm/native.bl"
    "env.bl" "bl.lock" "bin/bl-producer" "bin/bl-stage-hosts"
    "scripts/qualify-artifact-generation" "scripts/check-source-floor"
    "scripts/assemble-compiler-generations.py" "scripts/check-produced-compiler.py"
    "scripts/compiler-unit-baseline.py"
    "scripts/demo-artifact-production" "scripts/check-execution-history"
    "test/scripts/artifact-generation.bl"
  ];
}
