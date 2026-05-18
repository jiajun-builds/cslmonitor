#!/usr/bin/env bash

set -euo pipefail

source "$(cd "$(dirname "$0")" && pwd)/common.sh"
csl_bootstrap

format_duration() {
  local total_seconds="$1"
  local hours=$((total_seconds / 3600))
  local minutes=$(((total_seconds % 3600) / 60))
  local seconds=$((total_seconds % 60))

  if [ "$hours" -gt 0 ]; then
    printf '%dh%02dm%02ds' "$hours" "$minutes" "$seconds"
  elif [ "$minutes" -gt 0 ]; then
    printf '%dm%02ds' "$minutes" "$seconds"
  else
    printf '%ds' "$seconds"
  fi
}

print_phase_header() {
  local step_label="$1"
  local title="$2"

  printf '\n[%s] %s\n' "$step_label" "$title"
}

run_timed_phase() {
  local step_label="$1"
  local title="$2"
  local command_label="$3"
  shift 3

  local started_at
  local finished_at
  local elapsed

  print_phase_header "$step_label" "$title"
  printf 'Command: %s\n' "$command_label"

  started_at="$(date +%s)"
  if "$@"; then
    finished_at="$(date +%s)"
    elapsed=$((finished_at - started_at))
    printf '[%s] Done in %s\n' "$step_label" "$(format_duration "$elapsed")"
  else
    finished_at="$(date +%s)"
    elapsed=$((finished_at - started_at))
    printf '[%s] Failed after %s\n' "$step_label" "$(format_duration "$elapsed")" >&2
    printf 'Failed command: %s\n' "$command_label" >&2
    return 1
  fi
}

run_update() {
  csl_require_env RAPIDAPI_KEY || return 1
  ./scripts/run_csl_update.sh
}

run_model() {
  ./scripts/csl-model.sh
}

run_dashboard() {
  "$PYTHON" -m csl.dashboard.export_dashboard_csv
  "$PYTHON" -m csl.dashboard.export_dashboard_json
}

run_odds() {
  csl_require_env THE_ODDS_API_KEY || return 1
  "$PYTHON" -m csl.odds.fetch_pinnacle_spreads
  "$PYTHON" -m csl.odds.export_upcoming_market_comparison
}

run_odds_fetch() {
  csl_require_env THE_ODDS_API_KEY || return 1
  "$PYTHON" -m csl.odds.fetch_pinnacle_spreads
}

run_market_comparison() {
  "$PYTHON" -m csl.odds.export_upcoming_market_comparison
}

run_site_build() {
  ./scripts/build_dashboard_site.sh
}

run_publish() {
  run_dashboard
  run_site_build
}

run_all() {
  local started_at
  local finished_at
  local elapsed

  csl_require_env RAPIDAPI_KEY THE_ODDS_API_KEY || return 1

  started_at="$(date +%s)"

  cat <<'EOF'
Running full CSL workflow:
  1. Data update
  2. Model export
  3. Odds fetch
  4. Market comparison export
  5. Dashboard export
  6. Publish site
EOF

  run_timed_phase "STEP 1/6" "Data Update" "./scripts/run_csl_update.sh" run_update
  run_timed_phase "STEP 2/6" "Model Export" "./scripts/csl-model.sh" run_model
  run_timed_phase "STEP 3/6" "Odds Fetch" "python -m csl.odds.fetch_pinnacle_spreads" run_odds_fetch
  run_timed_phase "STEP 4/6" "Market Comparison Export" "python -m csl.odds.export_upcoming_market_comparison" run_market_comparison
  run_timed_phase "STEP 5/6" "Dashboard Export" "python -m csl.dashboard.export_dashboard_csv && python -m csl.dashboard.export_dashboard_json" run_dashboard
  run_timed_phase "STEP 6/6" "Publish Site" "./scripts/build_dashboard_site.sh" run_site_build

  finished_at="$(date +%s)"
  elapsed=$((finished_at - started_at))

  printf '\nAll steps completed in %s\n' "$(format_duration "$elapsed")"
  printf 'site/ is ready for Netlify deploy.\n'
}

show_help() {
  cat <<'EOF'
Usage:
  ./scripts/csl.sh <command>
  ./scripts/csl.sh

Commands:
  update     Run fixtures/xG/expg data update pipeline
  model      Run Dixon-Coles model export
  dashboard  Export dashboard CSV and JSON
  odds       Fetch Pinnacle odds and export market comparison
  publish    Rebuild dashboard exports and site/
  all        Run the full local workflow, including odds
  help       Show this help message
EOF
}

dispatch_command() {
  case "${1:-}" in
    update) run_update ;;
    model) run_model ;;
    dashboard) run_dashboard ;;
    odds) run_odds ;;
    publish) run_publish ;;
    all) run_all ;;
    help|-h|--help) show_help ;;
    *)
      echo "Unknown command: $1" >&2
      show_help >&2
      return 1
      ;;
  esac
}

show_menu() {
  echo "CSL workflow menu"
  echo "  1) update"
  echo "  2) model"
  echo "  3) dashboard"
  echo "  4) odds"
  echo "  5) publish"
  echo "  6) all"
  echo "  7) help"
  echo "  q) quit"
  printf "Choose an action: "

  local choice
  read -r choice

  case "$choice" in
    1) dispatch_command update ;;
    2) dispatch_command model ;;
    3) dispatch_command dashboard ;;
    4) dispatch_command odds ;;
    5) dispatch_command publish ;;
    6) dispatch_command all ;;
    7) dispatch_command help ;;
    q|Q) exit 0 ;;
    *)
      echo "Unknown menu choice: $choice" >&2
      return 1
      ;;
  esac
}

if [ "$#" -eq 0 ]; then
  show_menu
else
  dispatch_command "$1"
fi
