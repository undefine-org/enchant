# Capture the complete declared engine producer tree, including recipes and
# pinned coordinator sources. Generated state never becomes a producer input.
{ source }:
let
  lock = builtins.fromJSON (builtins.readFile ../flake.lock);
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
  root = /. + source;
  text = toString root;
  prefix = parent: child: parent == child || pkgs.lib.hasPrefix (parent + "/") child;
  policy = builtins.fromJSON (builtins.readFile ./engine-inputs.json);
  roots = policy.roots;
  excluded = policy.excluded;
  captured = builtins.path {
    name = "beam-lisp-engine-source";
    path = root;
    filter = path: type:
      let
        full = toString path;
        relative = if full == text then "." else builtins.substring (builtins.stringLength text + 1) (builtins.stringLength full) full;
        reserved = builtins.elem (baseNameOf path) policy.reserved
          || (baseNameOf path == "target" && builtins.any (entry: prefix entry relative) policy.targetRoots)
          || builtins.any (entry: prefix entry relative) excluded;
        selected = builtins.any (entry: prefix entry relative || prefix relative entry) roots;
      in if relative == "." then true
         else if reserved || !selected then false
         else if type == "symlink" then throw "Engine production requires a self-contained source tree"
         else if type == "directory" || type == "regular" then true
         else throw "Engine production rejects special inputs";
  };
in
assert policy.version == 1;
assert builtins.isString source && pkgs.lib.hasPrefix "/" source && text != "/";
assert builtins.all (entry: builtins.pathExists (root + "/${entry}")) roots;
pkgs.runCommand "beam-lisp-engine-snapshot" { nativeBuildInputs = [ pkgs.python3 ]; } ''
  python3 ${captured}/scripts/sdk-inputs --root ${captured} >/dev/null
  mkdir -p "$out"
  cp -a ${captured}/. "$out/"
''
