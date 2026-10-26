# Snapshot the complete declared crate/workspace root. Generated state is not
# an input; sibling path dependencies and supporting files inside the root are.
{ source, crate, version ? 1, member ? ".", package ? null }:
let
  snapshot = builtins.path {
    name = if version == 1 then "${crate}-source" else "native-workspace-source";
    path = /. + source;
    filter = path: type:
      if builtins.elem (baseNameOf path) [ ".git" "target" ".bl" ] then false
      else if type == "symlink" then throw "Native source snapshots require self-contained files, not symlinks"
      else type == "regular" || type == "directory";
  };
  workspace = import ./native-workspace.nix { source = snapshot; inherit member package; };
in
assert builtins.isString source && builtins.substring 0 1 source == "/" && source != "/";
assert builtins.isString crate && builtins.stringLength crate <= 128 && builtins.match "[a-zA-Z_][a-zA-Z0-9_]*" crate != null;
assert builtins.isInt version && builtins.elem version [ 1 2 ];
assert version != 1 || (member == "." && package == null);
assert version != 2 || builtins.deepSeq workspace true;
snapshot
