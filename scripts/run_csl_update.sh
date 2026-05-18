#!/usr/bin/env bash
# CSL data workflow: fixtures -> (xG + merge) -> HExpG+/AExpG+
# Run from repo root: ./scripts/run_csl_update.sh

set -euo pipefail

source "$(cd "$(dirname "$0")" && pwd)/common.sh"
csl_bootstrap

echo "Running in: ${CONDA_DEFAULT_ENV:-$CSL_ENV_NAME}"
step=1

run_step() {
  local title="$1"
  shift
  printf "Step %d: %s -- " "$step" "$title"
  if "$@"; then
    echo "Success"
  else
    echo "Failed"
    exit 1
  fi
  step=$((step + 1))
}

run_step "Update Fixtures" "$PYTHON" -m csl.fixtures.chn_fixture_v5

pull_xg_and_merge() {
  "$PYTHON" -m csl.xg.xg_pipeline && "$PYTHON" -m csl.xg.chn_merge
}
run_step "Pull xG & Update to Fixtures" pull_xg_and_merge

run_step "Calculate Expected Goal+" "$PYTHON" -m csl.xg.compute_expg

echo "All steps completed."
