#!/usr/bin/env bash
# Capture in one bounded checkout VM, then render captured sources in a GPU worker.
set -euo pipefail
cd "$(dirname "$0")/../.."
: "${SCENE_RSVG:?Set SCENE_RSVG to rsvg-convert}"
: "${SCENE_EGL:?Set SCENE_EGL to libEGL.so.1}"
: "${SCENE_GLES:?Set SCENE_GLES to libGLESv2.so.2}"
showcase_out=${1:-/tmp/bl-showcase}
showcase_mode=${2:-review}
case "$showcase_mode" in review|film) ;; *) echo 'Choose review or film' >&2; exit 2 ;; esac
scripts/bl-mem
systemd-run --user --collect --wait --pipe --working-directory="$PWD" \
 --setenv=PATH="$PATH" --setenv=SCENE_RSVG="$SCENE_RSVG" \
 --property=MemoryMax=3G --property=MemorySwapMax=256M --property=RuntimeMaxSec=10min \
 ./bin/bl --cold -p examples/scene-renderer run examples/scene-renderer/showcase.bl -- "$showcase_out"
showcase_dir=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["directory"])' "$showcase_out/manifest.json")
showcase_flags=()
if [ "$showcase_mode" = film ]; then showcase_flags+=(--film); fi
showcase_env=(--setenv=PATH="$PATH")
if [ -n "${__EGL_VENDOR_LIBRARY_FILENAMES:-}" ]; then showcase_env+=(--setenv=__EGL_VENDOR_LIBRARY_FILENAMES="$__EGL_VENDOR_LIBRARY_FILENAMES"); fi
systemd-run --user --collect --wait --pipe --working-directory="$PWD" \
 "${showcase_env[@]}" --property=MemoryMax=3G --property=MemorySwapMax=256M --property=RuntimeMaxSec=15min \
 python3 "$showcase_dir/sources/examples__scene-renderer__showcase_worker.py" "$showcase_dir" \
 --shaders "$showcase_dir/shaders" --rsvg "$SCENE_RSVG" \
 --text-worker "$showcase_dir/sources/priv__lib__scene__text_worker.py" \
 --egl "$SCENE_EGL" --gles "$SCENE_GLES" "${showcase_flags[@]}"
echo "Completed $showcase_mode: $showcase_dir"
