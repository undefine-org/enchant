# Snapshot the declared project input roots, not a mutable compiler cache.
{ source, rootsJson, excludedJson ? "[]" }:
let
  roots = builtins.fromJSON rootsJson;
  excluded = builtins.fromJSON excludedJson;
  rootPath = /. + source;
  rootText = toString rootPath;
  split = value: builtins.filter builtins.isString (builtins.split "/" value);
  relative = value: builtins.isString value && value != ""
    && builtins.substring 0 1 value != "/"
    && builtins.all (part: part != ".." && part != "") (split value);
  prefix = parent: child: parent == "." || parent == child
    || builtins.substring 0 (builtins.stringLength parent + 1) child == parent + "/";
  selected = path: builtins.any (root: prefix root path || prefix path root) roots;
in
assert builtins.isString source && builtins.substring 0 1 source == "/" && rootText != "/";
assert builtins.isList roots && roots != [] && builtins.all relative roots;
assert builtins.all (root: builtins.pathExists (rootPath + "/${root}")) roots;
assert builtins.isList excluded && builtins.all relative excluded;
builtins.path {
  name = "beam-lisp-project-source";
  path = rootPath;
  filter = path: type:
    let
      text = toString path;
      relativePath = if text == rootText then "."
        else builtins.substring (builtins.stringLength rootText + 1) (builtins.stringLength text) text;
      reserved = builtins.elem (baseNameOf path) [ ".git" ".bl" ]
        || relativePath == "target" || (prefix "native" relativePath && baseNameOf path == "target");
    in if relativePath == "." then true
       else if reserved || !selected relativePath || builtins.any (root: prefix root relativePath) excluded then false
       else if type == "symlink" then throw "Project inputs require an explicit self-contained source closure, not symlinks"
       else type == "regular" || type == "directory";
}
