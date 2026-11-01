#!/usr/bin/env bash
# Run from repository root, under a cgroup cap (see README).
set -euo pipefail
scene_runtime=$(mktemp -d /tmp/bl-scene-preview.XXXXXX)
export XDG_RUNTIME_DIR="$scene_runtime"
cleanup() {
  timeout 3 ./bin/bl realm stop >/dev/null 2>&1 || true
  python3 examples/scene-renderer/cleanup.py "$scene_runtime"
  rm -rf "$scene_runtime"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
./bin/bl --cold run examples/scene-renderer/preview.bl -- "${1:-/tmp/bl-scene}"
