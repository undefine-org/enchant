# One sequential transfer replaces per-file shared-store RPCs in SDK guests.
# The receiver still verifies each restored unit against current inputs.
{ pkgs, units }:
pkgs.runCommand "beam-lisp-sdk-unit-archive" {
  nativeBuildInputs = [ pkgs.gnutar pkgs.gzip pkgs.findutils ];
} ''
  test -f ${units}/unit-index.json
  test -z "$(find ${units} -type l -print -quit)"
  mkdir -p "$out"
  tar --sort=name --mtime=@1 --owner=0 --group=0 --numeric-owner \
    -czf "$out/units.tar.gz" --exclude=./producer -C ${units} .
''
