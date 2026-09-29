#!/bin/sh
# Build rc_cell and run the probe suite on stock AND patched ERTS.
#
#   research/erts-internals/p1-trace-callbacks/run.sh           both
#   research/erts-internals/p1-trace-callbacks/run.sh patched   one
#
# Every heavy step runs in a memory/CPU-capped systemd scope (host policy).
# Needs: the patched tree from ../otp/build.sh (default ~/.cache/bl/otp).
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
OTP=${OTP_TREE:-$HOME/.cache/bl/otp/otp-OTP-29.0.1}
OUT=${OUT:-/tmp/erts-trace-p1}
LIM="systemd-run --user --scope -q -p MemoryMax=4G -p MemorySwapMax=1G -p CPUQuota=400%"
mkdir -p "$OUT"

# rc_cell.c includes erl_nif_trace.h from the patched tree; the .so itself
# links against nothing -- the API is resolved with dlsym at load.
$LIM cc -O2 -g -Wall -Wextra -fPIC -shared \
  -I/usr/lib/erlang/usr/include -I"$OTP/erts/emulator/beam" \
  -o "$OUT/rc_cell.so" "$HERE/nif/rc_cell.c"
$LIM erlc -o "$OUT" "$HERE/nif/rc_cell.erl" "$HERE/nif/rc_test.erl"

run_on() {
  echo "== $1"
  case $1 in
    stock)   ERL=erl ;;
    patched) ERL="$HERE/../otp/erl-patched" ;;
  esac
  $LIM $ERL -noshell -pa "$OUT" -s rc_test main
}

for which in ${1:-stock patched}; do run_on "$which"; done
