#!/usr/bin/env bash
set -euo pipefail
# Run from the frozen native checkout on Build, under a process-tree cap.
# The caller supplies platform PATH, scheduler settings and backend limits.
before_root=${1:?baseline checkout required}
experiment_tag=${2:?unique SDK edit tag required}
export BL_TEST_SOURCE_ROOT=$PWD
unset PERF_COMPILED
cp .local/produce-sdk.original scripts/produce-sdk.bl
command time -v scripts/prepare-checkout-sdk > .local/sdk-final.txt 2> .local/sdk-final.log
./bin/bl --cold test test/bl/aot_reader_cache_test.bl > .local/reader-regression.log 2>&1
./bin/bl --cold test test/bl/aot_artifact_workspace_test.bl test/bl/aot_artifact_emission_test.bl test/bl/aot_host_artifact_test.bl test/bl/aot_sdk_constructor_staging_test.bl test/bl/aot_constructor_cache_test.bl test/bl/aot_constructor_diagnostics_test.bl test/bl/aot_constructor_machine_test.bl test/bl/aot_constructor_recipe_test.bl test/bl/aot_constructor_empty_recipes_test.bl test/bl/aot_constructor_walk_budget_test.bl test/bl/aot_constructor_atom_test.bl test/bl/constructor_data_limits_test.bl test/bl/compiler_constructor_data_test.bl test/bl/contextual_artifact_unit_test.bl test/bl/compiler_unit_store_test.bl test/bl/aot_reproducible_test.bl test/bl/host_atom_guard_test.bl test/bl/host_reader_test.bl test/bl/host_reader_exception_test.bl test/bl/loader_resolution_snapshot_test.bl > .local/constructor-regressions.log 2>&1
python3 research/sdk-compiler-child/benchmark.py --root "$PWD" --runs 1 --tag "$experiment_tag" --out .local/reader-sdk-incremental > .local/reader-sdk-incremental.log 2>&1
python3 research/remaining-latency/qualify.py --before-root "$before_root" --after-root "$PWD" --out .local/reader-commands > .local/reader-commands.log 2>&1
scripts/bl-mem > .local/reader-final-memory.txt
printf 'passed\n' > .local/reader-qualified.complete
