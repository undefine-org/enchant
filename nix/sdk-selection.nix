# Product references are selection data. Runtime SDK authority remains in the
# original image's compiler-produced sealed units, which this recipe never edits.
{ pkgs, image, release, platform }:
pkgs.runCommand "beam-lisp-sdk-selection" {
  nativeBuildInputs = [ pkgs.python3 ];
} ''
  mkdir -p "$out/bin"
  ln -s ${image}/lib "$out/lib"
  ln -s ${image}/image "$out/image"
  ln -s ${image}/bl "$out/bl"
  cat > "$out/bin/bl" <<EOF
  #!${pkgs.runtimeShell}
  unset BL_INTERNAL_PRODUCER
  export PATH=${platform}/bin:\$PATH
  export BL_ARTIFACT_PLATFORM=${platform}/artifact-platform
  export BL_SDK_PRODUCT="$out"
  exec "${image}/bl" "\$@"
  EOF
  chmod 555 "$out/bin/bl"
  python3 - <<'PY'
  import json, os
  from pathlib import Path
  metadata = json.loads(Path('${image}/artifact.json').read_text())
  portable = json.loads(Path('${release}/artifact.json').read_text())
  assert metadata['kind'] == 'sdk' and metadata['version'] == 1
  assert metadata['compiler'] == portable['compiler']
  assert portable['kind'] == 'release' and portable['target'] == metadata['target']
  metadata.update(release='${release}', image='${image}')
  (Path(os.environ['out']) / 'artifact.json').write_text(json.dumps(metadata, sort_keys=True) + '\n')
  PY
''
