#!/usr/bin/env bash
# Capture the BL plan in one capped cold VM, then draw/encode it in a capped GPU worker.
# Usage: research/ora-intro-film/proof/render.sh [OUT] [review|film]
set -euo pipefail
cd "$(dirname "$0")/../../.."
: "${SCENE_EGL:?Set SCENE_EGL to libEGL.so.1}"; : "${SCENE_GLES:?Set SCENE_GLES to libGLESv2.so.2}"
ora_out=${1:-/tmp/ora-layers};ora_mode=${2:-review}
case "$ora_mode" in review|film) ;; *) echo 'Choose review or film' >&2; exit 2;; esac
scripts/bl-mem
systemd-run --user --collect --wait --pipe --working-directory="$PWD" --setenv=PATH="$PATH" \
 --property=MemoryMax=3G --property=MemorySwapMax=256M --property=RuntimeMaxSec=10min \
 ./bin/bl --cold -p research/ora-intro-film/proof run research/ora-intro-film/proof/build.bl -- "$ora_out"
ora_dir=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["directory"])' "$ora_out/manifest.json")
ora_flags=();if [ "$ora_mode" = film ];then ora_flags+=(--film);fi
ora_env=(--setenv=PATH="$PATH");if [ -n "${__EGL_VENDOR_LIBRARY_FILENAMES:-}" ];then ora_env+=(--setenv=__EGL_VENDOR_LIBRARY_FILENAMES="$__EGL_VENDOR_LIBRARY_FILENAMES");fi
systemd-run --user --collect --wait --pipe --working-directory="$PWD" "${ora_env[@]}" \
 --property=MemoryMax=2G --property=MemorySwapMax=256M --property=RuntimeMaxSec=15min \
 python3 "$ora_dir/sources/research__ora-intro-film__proof__worker.py" "$ora_dir" \
 --gpu-worker "$ora_dir/sources/examples__scene-renderer__showcase_worker.py" --shaders "$ora_dir/shaders" \
 --egl "$SCENE_EGL" --gles "$SCENE_GLES" "${ora_flags[@]}"
echo "Completed $ora_mode: $ora_dir"
