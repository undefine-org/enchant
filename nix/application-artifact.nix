# Closed data request, exact immutable SDK, existing BL compiler/producer.
{ requestJson ? null, requestPath ? null, sdk }:
let
  request = builtins.fromJSON (builtins.unsafeDiscardStringContext (if requestPath != null
    then builtins.readFile (/. + requestPath)
    else requestJson));
  lock = builtins.fromJSON (builtins.readFile ../flake.lock);
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
  storeObject = value: builtins.isString value && builtins.match "/nix/store/[0-9a-z]{32}-[^/]+" value != null;
  relative = value: builtins.isString value && value != "" && builtins.substring 0 1 value != "/"
    && builtins.all (part: part != ".." && part != "") (pkgs.lib.splitString "/" value);
  source = builtins.storePath request.source;
  image = builtins.storePath sdk;
  descriptor = builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile (image + "/artifact.json")));
  platform = builtins.storePath descriptor.platform;
  nativeDirectory = source + "/native";
  crates = if request.native && builtins.pathExists nativeDirectory
    then builtins.filter (name: builtins.pathExists (nativeDirectory + "/${name}/Cargo.toml"))
      (builtins.attrNames (builtins.readDir nativeDirectory)) else [];
  products = builtins.listToAttrs (map (crate: {
    name = crate;
    value = import ./native-artifact.nix {
      requestJson = builtins.toJSON {
        version = 1;
        inherit crate;
        source = toString (nativeDirectory + "/${crate}");
        abi = "beam-lisp-native-${crate}-v1";
        target = "x86_64-linux";
      };
    };
  }) crates);
  nativeSet = if crates == [] then null else import ./native-bundle.nix { inherit pkgs products; };
  requestFile = pkgs.writeText "beam-lisp-application-request.json" (builtins.toJSON request);
  boot = pkgs.writeText "beam-lisp-application-producer.exs" ''
    for path <- Path.wildcard("${image}/lib/*/ebin"), do: Code.prepend_path(path)
    Code.prepend_path("${image}/image/ebin")
    Application.load(:beam_lisp)
    for app <- Application.spec(:beam_lisp, :applications) || [], do: {:ok, _} = Application.ensure_all_started(app)
    :ok = BeamLisp.LazyMemo.ensure_loaded!()
    BeamLisp.AOT.boot()
    BeamLisp.run_file("${./application-worker.bl}")
  '';
in
assert (requestJson == null) != (requestPath == null);
assert builtins.attrNames request == [ "ex" "exclude" "jobs" "native" "source" "sources" "version" "world" ];
assert request.version == 1 && storeObject request.source && storeObject sdk;
assert descriptor.version == 1 && descriptor.kind == "sdk" && descriptor.target == "x86_64-linux";
assert (descriptor.producerAPI or 1) == 2;
assert builtins.isList request.sources && builtins.all relative request.sources;
assert request.world == null || relative request.world;
assert builtins.isList request.exclude && builtins.all relative request.exclude;
assert builtins.isBool request.native;
assert builtins.isInt request.jobs && request.jobs >= 1 && request.jobs <= 4;
assert request.ex == null || (builtins.isAttrs request.ex && builtins.attrNames request.ex == [ "exclude" "root" ]
  && relative request.ex.root && builtins.isList request.ex.exclude && builtins.all builtins.isString request.ex.exclude);
(import ./bounded-build.nix {
  inherit pkgs;
  memoryMiB = 6144;
  diskMiB = 32768;
  cpuCount = 4;
  commandManager = true;
}) (pkgs.runCommand "beam-lisp-application" {
  nativeBuildInputs = [ pkgs.python3 ];
} ''
  mkdir -p /build/project "$out"
  cp -a --no-preserve=ownership ${source}/. /build/project/
  chmod -R u+w /build/project
  export HOME=/build/home XDG_CACHE_HOME=/build/home/.cache BL_DAEMON=off
  export PATH=${platform}/bin:$PATH
  export LANG=C.UTF-8 ELIXIR_ERL_OPTIONS="+fnu +S 4:4 +SDcpu 2:2 +SDio 1:1"
  export BL_ROOT=${image}/image BL_BIN=${image}/bl
  export BL_ARTIFACT_PLATFORM=${platform}/artifact-platform
  ${pkgs.lib.optionalString (nativeSet != null) "export BL_PREPARED_NATIVES=${nativeSet}"}
  export BL_APPLICATION_REQUEST=${requestFile}
  export BL_APPLICATION_SOURCE=/build/project BL_APPLICATION_OUTPUT="$out"
  mkdir -p "$HOME" "$XDG_CACHE_HOME"
  cd /build/project
  ${platform}/bin/elixir ${boot}
  rm -rf "$out/.bl"
  mkdir -p "$out/native"
  ${pkgs.lib.concatMapStringsSep "\n" (crate: ''
    ln -s ${products.${crate}}/lib/${crate}.so "$out/native/${crate}.so"
  '') crates}
  printf '%s\n' '${builtins.toJSON {
    version = 1;
    kind = "application";
    source = toString source;
    sdk = toString image;
    target = "x86_64-linux";
  }}' > "$out/artifact.json"
  ${pkgs.python3}/bin/python3 ${./application-inventory.py} write "$out"
  ${pkgs.python3}/bin/python3 ${./application-inventory.py} verify "$out" ${image} ${source} >/dev/null
'')
