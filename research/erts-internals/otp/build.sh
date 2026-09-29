#!/bin/sh
# Build a patched beam.smp for the INSTALLED OTP version -- emulator only.
#
#   research/erts-internals/otp/build.sh            fetch + configure + build
#   research/erts-internals/otp/build.sh rebuild    re-apply patches, relink
#
# Only erts/emulator is built. Every OTP application (.beam) is reused from
# the system install, which is why the tag MUST equal the installed release
# (erlang:system_info(otp_release) + releases/*/OTP_VERSION). A mismatched
# beam.smp would load .beam files compiled for another emulator.
#
# Heavy steps run in a memory/CPU-capped systemd scope (host policy).
# Measured on this host (Ryzen AI 7 350, load ~20): configure 66 s, cold
# emulator build ~2.7 min (-j12), relink after one .c change 18 s, after a
# shared header change (global.h) 140 s.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
VSN=$(cat /usr/lib/erlang/releases/*/OTP_VERSION | head -1)
BASE=${OTP_BASE:-$HOME/.cache/bl/otp}
TREE=$BASE/otp-OTP-$VSN
LIM="systemd-run --user --scope -q -p MemoryMax=12G -p MemorySwapMax=2G -p CPUQuota=1200%"
# OTP names its build dir by config.guess (x86_64-pc-linux-gnu here).

mkdir -p "$BASE"
if [ "${1:-}" != rebuild ]; then
  if [ ! -d "$TREE" ]; then
    curl -sSL -o "$BASE/otp-$VSN.tar.gz" \
      "https://github.com/erlang/otp/archive/refs/tags/OTP-$VSN.tar.gz"
    tar -C "$BASE" -xzf "$BASE/otp-$VSN.tar.gz"
  fi
  cd "$TREE"
  # Track the emulator sources so patches apply and diff cleanly.
  if [ ! -d .git ]; then
    git init -q
    git add -f erts/emulator/beam erts/emulator/Makefile.in erts/emulator/sys/common
    git -c user.email=bl@local -c user.name=bl commit -qm "OTP-$VSN pristine"
  fi
  export ERL_TOP="$TREE"
  $LIM ./configure --without-wx --without-javac --without-odbc \
       --without-jinterface > "$BASE/configure.log" 2>&1
fi

cd "$TREE"
export ERL_TOP="$TREE"
for p in "$HERE"/patches/*.patch; do
  git apply --check "$p" 2>/dev/null && git apply "$p" && echo "applied $(basename "$p")"
done
# erl_nif_trace.c is #included by erl_nif.c; make's dep file does not know.
# (erl_binary.h / global.h changes are tracked and rebuild what they must.)
touch erts/emulator/beam/erl_nif.c
$LIM make -C erts/emulator -j12 opt TYPE= FLAVOR=jit > "$BASE/emulator.log" 2>&1

BIN=$(dirname "$(ls "$TREE"/bin/*/beam.smp | head -1)")
# erlexec/epmd/heart/inet_gethost are not rebuilt; borrow the system's.
for f in erlexec inet_gethost epmd heart; do
  ln -sf /usr/lib/erlang/erts-*/bin/$f "$BIN/$f"
done
echo "patched emulator: $BIN/beam.smp"
"$HERE/erl-patched" -noshell -eval \
  'io:format("~p~n", [maps:with([enabled, auto, threshold, shards], erlang:system_info(resource_cycles))]), halt().'
