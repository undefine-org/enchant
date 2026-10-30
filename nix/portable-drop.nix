# Portable packaging consumes the produced SDK/release pair. It changes only
# deployable files; sealed SDK code and unit metadata remain untouched.
{ pkgs, product, sdk, tools }:
(import ./bounded-build.nix {
  inherit pkgs;
  memoryMiB = 1024;
  diskMiB = 8192;
}) (pkgs.runCommand "beam-lisp-portable-release" {
  nativeBuildInputs = [ pkgs.python3 pkgs.patchelf ];
} ''
  python3 - <<'VERIFY'
  import hashlib, json
  from pathlib import Path
  release = json.loads(Path('${product}/artifact.json').read_text())
  image = json.loads(Path('${sdk}/artifact.json').read_text())
  assert release['version'] == 1 and release['kind'] == 'release'
  assert release['target'] == image['target'] == 'x86_64-linux'
  assert release['compiler'] == image['compiler']
  with Path('${product}/bl.drop').open('rb') as stream:
      assert hashlib.file_digest(stream, 'sha256').hexdigest() == release['sha256']
  VERIFY
  ${tools}/bin/drop unpack ${product}/bl.drop --dir payload
  chmod -R u+w payload
  python3 - <<'PY'
  from pathlib import Path
  changed = []
  for path in Path('payload').rglob('*'):
      if path.is_symlink() or not path.is_file():
          continue
      with path.open('rb') as stream:
          first = stream.readline(4096)
      if first.startswith(b'#!') and b'/nix/store/' in first:
          interpreter = first.strip().split()[0].rsplit(b'/', 1)[-1]
          if interpreter not in (b'sh', b'bash', b'dash'):
              raise SystemExit(f'undeclared portable interpreter: {path}: {first!r}')
          replacement = b'#!/bin/bash\n' if interpreter == b'bash' else b'#!/bin/sh\n'
          path.write_bytes(replacement + path.read_bytes()[len(first):])
          changed.append(str(path))
  print('Repaired portable interpreters:', changed)
  PY
  cp ${tools}/bin/drop-launcher launcher
  chmod u+w launcher
  patchelf --set-interpreter /lib64/ld-linux-x86-64.so.2 --remove-rpath launcher
  mkdir -p "$out"
  ${tools}/bin/drop pack --release payload --launcher launcher --out "$out/bl.drop"
  python3 - <<'MANIFEST'
  import hashlib, json, os
  from pathlib import Path
  out = Path(os.environ['out'])
  manifest = json.loads(Path('${product}/artifact.json').read_text())
  with (out / 'bl.drop').open('rb') as stream:
      manifest['sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
  manifest['packaging'] = 'portable-shell-v1'
  (out / 'artifact.json').write_text(json.dumps(manifest, sort_keys=True) + '\n')
  MANIFEST
'')
