# Portable packaging is a separate product of the exact native image.
# Selecting an SDK cannot realize this derivation or run its ELF mutations.
{ pkgs, image, tools }:
let
  metadata = builtins.fromJSON (builtins.readFile (image + "/artifact.json"));
  worker = import ./bounded-build.nix {
    inherit pkgs; memoryMiB = 4096; diskMiB = 16384; cpuCount = 2;
    commandManager = false; trace = true;
  };
in
assert metadata.version == 1 && metadata.kind == "sdk" && metadata.target == "x86_64-linux";
worker (pkgs.runCommand "beam-lisp-portable-release" {
  nativeBuildInputs = [ pkgs.patchelf pkgs.python3 pkgs.coreutils ];
} ''
  sdk_phase_start() { sdk_phase_label=$1; sdk_phase_started=$(date +%s%N); }
  sdk_phase_end() {
    local elapsed=$(( ($(date +%s%N) - sdk_phase_started) / 1000 ))
    printf 'SDK-SHELL-PHASE {"stage":"%s","elapsed-us":%s}\n' "$sdk_phase_label" "$elapsed"
  }
  sdk_phase_start materialize-native-image
  cp -a --reflink=auto --no-preserve=ownership ${image}/payload "$TMPDIR/payload"
  chmod -R u+w "$TMPDIR/payload"
  cp ${tools}/bin/drop-launcher "$TMPDIR/launcher"
  cp ${tools}/bin/drop "$TMPDIR/drop"
  chmod u+w "$TMPDIR/launcher"
  patchelf --set-interpreter /lib64/ld-linux-x86-64.so.2 --remove-rpath "$TMPDIR/launcher"
  sdk_phase_end
  sdk_phase_start portable-retarget
  # A portable drop carries bytes rather than references to its build store.
  for native in $TMPDIR/payload/lib/beam_lisp-*/priv/native/*.so; do
    if [ -L "$native" ]; then
      cp --dereference "$native" "$native.materialized"
      mv "$native.materialized" "$native"
    fi
  done
  ${pkgs.python3}/bin/python3 - <<'PORTABLE'
  import json, os
  from pathlib import Path
  import subprocess
  patcher = '${pkgs.patchelf}/bin/patchelf'
  counts = dict(files=0, elf=0, interpreters=0)
  for path in (Path(os.environ['TMPDIR']) / 'payload').rglob('*'):
      if path.is_symlink() or not path.is_file():
          continue
      counts['files'] += 1
      with path.open('rb') as stream:
          marker = stream.read(4)
          first = marker + stream.readline(4092) if marker.startswith(b'#!') else marker
      if marker == b'\x7fELF':
          counts['elf'] += 1
          dynamic = subprocess.run([patcher, '--print-interpreter', path],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
          if dynamic:
              subprocess.run([patcher, '--set-interpreter', '/lib64/ld-linux-x86-64.so.2',
                              '--remove-rpath', path], check=True)
          else:
              subprocess.run([patcher, '--remove-rpath', path],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
      elif first.startswith(b'#!') and b'/nix/store/' in first:
          interpreter = first.strip().split()[0].rsplit(b'/', 1)[-1]
          if interpreter not in (b'sh', b'bash', b'dash'):
              raise SystemExit(f'undeclared portable interpreter: {path}: {first!r}')
          replacement = b'#!/bin/bash\n' if interpreter == b'bash' else b'#!/bin/sh\n'
          path.write_bytes(replacement + path.read_bytes()[len(first):])
          counts['interpreters'] += 1
  print('PORTABLE-PAYLOAD ' + json.dumps(counts), flush=True)
  PORTABLE
  sdk_phase_end
  sdk_phase_start pack-portable
  $TMPDIR/drop pack --release $TMPDIR/payload --launcher $TMPDIR/launcher --out $TMPDIR/bl.drop
  sdk_phase_end

  mkdir -p "$out"
  cp "$TMPDIR/bl.drop" "$out/bl.drop"
  ${pkgs.python3}/bin/python3 - <<'RECEIPT'
  import hashlib, json, os
  from pathlib import Path
  output = Path(os.environ['out'])
  descriptor = ${builtins.toJSON (builtins.toJSON {
    version = 1; kind = "release"; packaging = "portable-shell-v1";
    inherit (metadata) compiler target; image = toString image; file = "bl.drop";
  })}
  descriptor = json.loads(descriptor)
  with (output / 'bl.drop').open('rb') as stream:
      descriptor['sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
  (output / 'artifact.json').write_text(json.dumps(descriptor, sort_keys=True) + '\n')
  RECEIPT
'')
