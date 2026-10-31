#!/usr/bin/env sh
# glibc-floor.sh DROP|DIR — highest required GLIBC symbol version in the
# launcher and payload. This measures ELF version needs, not exported versions.
# Requires readelf (binutils); a packed drop also needs DROP_BIN or drop on PATH.
set -eu
export LC_ALL=C
target=${1:?usage: glibc-floor.sh DROP|DIR}
readelf=${READELF:-readelf}
"$readelf" --version >/dev/null 2>&1 || { echo "glibc-floor: usable readelf not found (binutils)" >&2; exit 2; }
[ -e "$target" ] || { echo "glibc-floor: target does not exist: $target" >&2; exit 2; }
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

dir=$target
launcher=""
if [ -f "$target" ]; then
  drop=${DROP_BIN:-$(command -v drop || true)}
  [ -n "$drop" ] || { echo "glibc-floor: no drop unpacker (set DROP_BIN)" >&2; exit 2; }
  "$drop" unpack "$target" --dir "$work/payload" >/dev/null
  dir=$work/payload
  launcher=$target
fi
[ -d "$dir" ] || { echo "glibc-floor: payload is not a directory" >&2; exit 2; }
export GLIBC_SCAN_ROOT="$dir" GLIBC_SCAN_LAUNCHER="$launcher" READELF="$readelf"
# find passes each pathname as an argument, preserving spaces. Inspect failures
# are errors: silently treating them as an absent GLIBC requirement is unsafe.
# shellcheck disable=SC2016 # Variables belong to the child shell, not this one.
scan='
  set -eu
  for f do
    magic=$(od -An -tx1 -N4 "$f" | tr -d " \n")
    [ "$magic" = 7f454c46 ] || continue
    versions=$("$READELF" --version-info --wide "$f") || exit 2
    v=$(printf "%s\n" "$versions" |
      awk "/Version needs section/ { needs=1; next } /^Version / { needs=0 } needs" |
      grep -oE "GLIBC_[0-9]+(\.[0-9]+)+" | sed "s/GLIBC_//" | sort -V | tail -1)
    [ -n "$v" ] || continue
    if [ "$f" = "$GLIBC_SCAN_LAUNCHER" ]; then label="(launcher)"; else label=${f#"$GLIBC_SCAN_ROOT"/}; fi
    printf "%s  %s\n" "$v" "$label"
  done
'
if ! find "$dir" -type f -size +0c -exec sh -c "$scan" sh {} + >"$work/versions"; then
  echo "glibc-floor: could not inspect payload ELF requirements" >&2
  exit 2
fi
if [ -n "$launcher" ]; then
  if ! sh -c "$scan" sh "$launcher" >>"$work/versions"; then
    echo "glibc-floor: could not inspect launcher ELF requirements" >&2
    exit 2
  fi
fi
if [ -s "$work/versions" ]; then
  sort -V -k1,1 "$work/versions" | tail -1
else
  printf '0.0  (no dynamic glibc ELF)\n'
fi
