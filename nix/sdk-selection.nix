# Product references are selection data. Runtime SDK authority remains in the
# original image's compiler-produced sealed units, which this recipe never edits.
{ pkgs, image, release, platform, coordinator }:
pkgs.runCommand "beam-lisp-sdk-selection" {
  nativeBuildInputs = [ pkgs.python3 ];
} ''
  mkdir -p "$out/bin"
  ln -s ${image}/lib "$out/lib"
  ln -s ${image}/image "$out/image"
  ln -s ${image}/bl "$out/bl"
  ln -s ${image}/unit-store "$out/unit-store"
  ln -s ${coordinator} "$out/preparation-coordinator"
  cat > "$out/boot.exs" <<EOF
  for path <- Path.wildcard("$out/lib/*/ebin"), do: Code.prepend_path(path)
  Code.prepend_path("$out/image/ebin")
  :code.del_path(~c".")
  BeamLisp.Launcher.start_app!(System.argv(), %{})
  EOF
  cat > "$out/bin/bl" <<EOF
  #!${pkgs.runtimeShell}
  unset BL_INTERNAL_PRODUCER
  export PATH=${platform}/bin:\$PATH
  export BL_ARTIFACT_PLATFORM=${platform}/artifact-platform
  export BL_PREPARATION_COORDINATOR=${coordinator}
  export BL_SDK_PRODUCT="$out"
  export BL_ROOT="$out/image" BL_EBIN="$out/image/ebin" BL_BUILD_ID=src BEAM_LISP_DEV=0
  export BL_BIN=${platform}/bin/drop-launcher
  export BL_PREPARED_NATIVES="$(readlink -f ${platform}/native-products)"
  exec ${platform}/bin/elixir "$out/boot.exs" "\$@"
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
  metadata.update(release='${release}', image='${image}', coordinator='${coordinator}')
  (Path(os.environ['out']) / 'artifact.json').write_text(json.dumps(metadata, sort_keys=True) + '\n')
  PY
''
