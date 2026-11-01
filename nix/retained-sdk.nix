# Observe the retained SDK and its genuine Source without demanding a producer.
{ sdk, sdkReference, sdkSource, source, descriptorSha256 }:
let
  alias = toString sdk;
  sdkRoot = toString sdkSource;
  sourceRoot = toString source;
  # Flake path inputs are source aliases with no retained product references.
  # The explicit qualified reference must remain an actual package dependency.
  selected = builtins.appendContext sdkReference { "${sdkReference}" = { path = true; }; };
  require = condition: message: value:
    if condition then value else throw "Beam Lisp retained SDK: ${message}";
  passive = path: builtins.unsafeDiscardStringContext (builtins.readFile path);
  metadata = builtins.fromJSON (passive (alias + "/artifact.json"));
  launcher = passive (alias + "/bin/bl");
  rustFiles = root: directory:
    let entries = builtins.readDir (root + "/${directory}"); in
    builtins.concatLists (map (name:
      let relative = "${directory}/${name}"; type = entries.${name}; in
      if type == "directory" then rustFiles root relative
      else if type == "regular" && builtins.match ".*\\.rs" name != null
      then [ relative ] else []) (builtins.attrNames entries));
  fileNames = root: builtins.sort builtins.lessThan
    ([ "Cargo.toml" "Cargo.lock" "build.rs" ] ++ rustFiles root "src");
  crate = sourceRoot + "/native/lazy_memo";
  sdkCrate = sdkRoot + "/native/lazy_memo";
  names = fileNames crate;
  matchingFiles = builtins.all (name:
    builtins.hashFile "sha256" (crate + "/${name}")
      == builtins.hashFile "sha256" (sdkCrate + "/${name}")) names;
  matchingApi = builtins.hashFile "sha256" (sourceRoot + "/priv/host/lazy_memo.bl")
    == builtins.hashFile "sha256" (sdkRoot + "/priv/host/lazy_memo.bl");
in
require (builtins.hashFile "sha256" (alias + "/artifact.json") == descriptorSha256)
  "qualified artifact descriptor changed; explicitly qualify and update the SDK selection" (
require (metadata.version == 1 && metadata.kind == "sdk" && metadata.target == "x86_64-linux")
  "expected a qualified x86_64-linux SDK selection" (
require (builtins.match "/nix/store/[0-9a-z]{32}-beam-lisp-sdk-selection" sdkReference != null
  && builtins.match ".*\nexport BL_SDK_PRODUCT=\"${sdkReference}\"\n.*" launcher != null)
  "retained SDK reference does not match the qualified launcher" (
require (metadata.source == sdkRoot) "SDK Source does not match the qualified selection" (
require (names == fileNames sdkCrate && matchingFiles)
  "public Source pin and SDK Android native Source differ" (
require matchingApi "public Source pin and SDK native API declarations differ"
selected)))))
