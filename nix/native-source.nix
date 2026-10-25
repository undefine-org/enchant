# Snapshot a complete standalone crate. Reserved build/cache directories are omitted.
{ source, crate }:
assert builtins.isString source && builtins.substring 0 1 source == "/";
assert builtins.match "[a-zA-Z_][a-zA-Z0-9_]*" crate != null;
builtins.path {
  name = "${crate}-source";
  path = /. + source;
  filter = path: type:
    if builtins.elem (baseNameOf path) [ ".git" "target" ".bl" ] then false
    else if type == "symlink" then throw "Native source snapshots require self-contained files, not symlinks"
    else true;
}
