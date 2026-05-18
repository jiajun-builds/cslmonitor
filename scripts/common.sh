#!/usr/bin/env bash

CSL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CSL_CONDA_SH="${CSL_CONDA_SH:-$HOME/anaconda3/etc/profile.d/conda.sh}"
CSL_ENV_NAME="${CSL_ENV_NAME:-csl-workflows}"
CSL_ENV_FILE="${CSL_ENV_FILE:-$CSL_ROOT/.env.local}"

csl_repo_root() {
  printf '%s\n' "$CSL_ROOT"
}

csl_activate_environment() {
  if [ ! -f "$CSL_CONDA_SH" ]; then
    echo "Conda init script not found: $CSL_CONDA_SH" >&2
    return 1
  fi

  # shellcheck disable=SC1090
  source "$CSL_CONDA_SH"
  conda activate "$CSL_ENV_NAME"
}

csl_load_local_env() {
  if [ -f "$CSL_ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$CSL_ENV_FILE"
    set +a
  fi
}

csl_bootstrap() {
  csl_activate_environment || return 1
  cd "$CSL_ROOT" || return 1
  csl_load_local_env
  export PYTHONPATH="${CSL_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
  export PYTHON="${PYTHON:-python3}"
}

csl_require_env() {
  local missing=0
  local var_name
  for var_name in "$@"; do
    if [ -z "${!var_name:-}" ]; then
      echo "Missing required environment variable: $var_name" >&2
      missing=1
    fi
  done
  return "$missing"
}
