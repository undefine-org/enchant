#!/usr/bin/env bash
# Focused checks; caller supplies the cgroup cap and checkout toolchain PATH.
set -euo pipefail
scripts/bl-mem
./bin/bl --cold -p examples/scene-renderer test test/bl/scene/core_test.bl
./bin/bl --cold -p examples/scene-renderer run examples/scene-renderer/build.bl -- "${1:-/tmp/bl-scene}"
python3 examples/scene-renderer/raster.py export "${1:-/tmp/bl-scene}" --out "${1:-/tmp/bl-scene}/scene-study.mp4"
