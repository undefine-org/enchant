# Validate the captured Cargo closure without executing Cargo metadata or a
# caller expression. Cargo owns workspace glob expansion; we inspect the root,
# selected package and every transitively reachable path dependency. Unused
# Cargo.toml fixtures remain ordinary supporting bytes.
{ source, member, package }:
let
  sourceText = toString source;
  split = value: builtins.filter builtins.isString (builtins.split "/" value);
  reserved = [ ".git" ".bl" "target" ];
  validMember = builtins.isString member && builtins.stringLength member <= 4096 && (member == "." ||
    (member != "" && builtins.substring 0 1 member != "/"
      && builtins.all (part: part != "" && part != "." && part != ".."
        && builtins.stringLength part <= 255
        && builtins.match "[A-Za-z0-9_.-]+" part != null
        && builtins.substring 0 1 part != "-"
        && !(builtins.elem part reserved)) (split member)));
  validPackage = builtins.isString package && builtins.stringLength package <= 128
    && builtins.match "[A-Za-z0-9_][A-Za-z0-9_-]*" package != null;
  parent = parts: builtins.genList (index: builtins.elemAt parts index) (builtins.length parts - 1);
  normalize = base: value:
    assert builtins.isString value && value != "" && builtins.stringLength value <= 4096
      && builtins.substring 0 1 value != "/";
    builtins.foldl' (parts: part:
      if part == "" || part == "." then parts
      else if part == ".." then
        if parts == [] then throw "Native path dependency escapes the captured workspace root"
        else parent parts
      else if builtins.elem part reserved then throw "Native dependencies cannot use reserved build/cache directories"
      else parts ++ [ part ]) base (split value);
  join = parts: if parts == [] then "." else builtins.concatStringsSep "/" parts;
  at = relative: source + "/${relative}";
  checkTree = relative: depth:
    if depth > 64 then throw "Native workspace source nesting exceeds capacity"
    else let entries = builtins.readDir (at relative);
    in builtins.all (name:
      let path = if relative == "." then name else relative + "/" + name;
          type = entries.${name};
      in if builtins.elem name reserved then throw "Native workspace store inputs must omit reserved build/cache directories"
         else if type == "directory" then checkTree path (depth + 1)
         else if type == "regular" then true
         else throw "Native workspace sources require self-contained regular files and directories"
    ) (builtins.attrNames entries);
  readManifest = path: builtins.fromTOML (builtins.readFile (at path));
  memberPath = if member == "." then "Cargo.toml" else member + "/Cargo.toml";
  rootManifest = readManifest "Cargo.toml";
  memberManifest = readManifest memberPath;
  dependencyTables = manifest:
    [ (manifest.dependencies or {}) (manifest.dev-dependencies or {}) (manifest.build-dependencies or {})
      (manifest.workspace.dependencies or {}) (manifest.replace or {}) ]
    ++ builtins.concatLists (map (target:
      [ (target.dependencies or {}) (target.dev-dependencies or {}) (target.build-dependencies or {}) ])
      (builtins.attrValues (manifest.target or {})))
    ++ builtins.attrValues (manifest.patch or {});
  dependencyPath = base: definition:
    if builtins.isAttrs definition && definition ? path then
      let relative = join (normalize base definition.path);
          manifestPath = if relative == "." then "Cargo.toml" else relative + "/Cargo.toml";
      in if builtins.pathExists (at manifestPath) then [ manifestPath ]
         else throw "Native path dependency is missing its manifest inside the captured root: ${relative}"
    else [];
  pathsFrom = path:
    let manifest = readManifest path;
        directory = builtins.dirOf path;
        base = if directory == "." then [] else split directory;
    in builtins.concatLists (map (table:
         assert builtins.isAttrs table;
         builtins.concatLists (map (dependencyPath base) (builtins.attrValues table))) (dependencyTables manifest));
  visit = pending: seen:
    if builtins.length seen > 1024 then throw "Native path dependency closure exceeds capacity"
    else if pending == [] then true
    else let path = builtins.head pending;
    in if builtins.elem path seen then visit (builtins.tail pending) seen
       else visit ((builtins.tail pending) ++ pathsFrom path) (seen ++ [ path ]);
  workspace = rootManifest.workspace or {};
  # Cargo supports globs here. Validate lexical containment, not membership.
  checkPattern = rejectReserved: value: builtins.isString value && value != "" && builtins.stringLength value <= 4096
    && builtins.substring 0 1 value != "/"
    && builtins.all (part: part != ".." && (!rejectReserved || !(builtins.elem part reserved))) (split value);
  patterns = (workspace.members or []) ++ (workspace.default-members or []);
  excludes = workspace.exclude or [];
  rawVersion = memberManifest.package.version or null;
  version = if builtins.isString rawVersion then rawVersion
    else if builtins.isAttrs rawVersion && rawVersion == { workspace = true; }
      then rootManifest.workspace.package.version or null
      else null;
in
assert validMember;
assert validPackage;
assert builtins.substring 0 1 sourceText == "/" && sourceText != "/";
assert builtins.pathExists (at "Cargo.toml") && builtins.pathExists (at "Cargo.lock");
assert member == "." || rootManifest ? workspace;
assert (memberManifest.package.name or null) == package;
assert builtins.isString version && version != "";
assert builtins.isList patterns && builtins.all (checkPattern true) patterns;
assert builtins.isList excludes && builtins.all (checkPattern false) excludes;
assert checkTree "." 0;
assert visit [ "Cargo.toml" memberPath ] [];
{ manifest = memberManifest; inherit version; }
