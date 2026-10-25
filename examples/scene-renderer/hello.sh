#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
: "${SCENE_RSVG:?Set SCENE_RSVG}"; : "${SCENE_EGL:?Set SCENE_EGL}"; : "${SCENE_GLES:?Set SCENE_GLES}"
hello_out=${1:-/tmp/bl-hello-film};hello_mode=${2:-review}
case "$hello_mode" in review|film) ;; *) echo 'Choose review or film' >&2; exit 2;; esac
scripts/bl-mem
systemd-run --user --collect --wait --pipe --working-directory="$PWD" --setenv=PATH="$PATH" --setenv=SCENE_RSVG="$SCENE_RSVG" \
 --property=MemoryMax=4G --property=MemorySwapMax=512M --property=RuntimeMaxSec=10min \
 ./bin/bl --cold -p examples/scene-renderer run examples/scene-renderer/hello.bl -- "$hello_out"
hello_dir=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["directory"])' "$hello_out/manifest.json")
hello_flags=();if [ "$hello_mode" = film ];then hello_flags+=(--film);fi
hello_env=(--setenv=PATH="$PATH");if [ -n "${__EGL_VENDOR_LIBRARY_FILENAMES:-}" ];then hello_env+=(--setenv=__EGL_VENDOR_LIBRARY_FILENAMES="$__EGL_VENDOR_LIBRARY_FILENAMES");fi
systemd-run --user --collect --wait --pipe --working-directory="$PWD" "${hello_env[@]}" \
 --property=MemoryMax=4G --property=MemorySwapMax=512M --property=RuntimeMaxSec=20min \
 python3 "$hello_dir/sources/examples__scene-renderer__hello_worker.py" "$hello_dir" \
 --gpu-worker "$hello_dir/sources/examples__scene-renderer__showcase_worker.py" --helper "$hello_dir/sources/priv__lib__scene__text_worker.py" \
 --shaders "$hello_dir/shaders" --rsvg "$SCENE_RSVG" --egl "$SCENE_EGL" --gles "$SCENE_GLES" "${hello_flags[@]}"
echo "Completed $hello_mode: $hello_dir"
