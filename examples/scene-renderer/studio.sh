#!/usr/bin/env bash
set -euo pipefail
scene_runtime=$(mktemp -d /tmp/bl-scene-preview.XXXXXX)
export XDG_RUNTIME_DIR="$scene_runtime"
cleanup() {
  python3 examples/scene-renderer/cleanup.py "$scene_runtime"
  rm -rf "$scene_runtime"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
scene_out=${1:-/tmp/bl-postcard-studio}
mkdir -p "$scene_out"
flock -n "$scene_out/.studio.lock" ./bin/bl --cold -p examples/scene-renderer run examples/scene-renderer/studio.bl -- "$scene_out"
