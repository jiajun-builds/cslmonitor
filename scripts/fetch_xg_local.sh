#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Local xG refresh — run on a residential-IP machine (e.g. an old Mac at home).
#
# SofaScore's Cloudflare 403s GitHub Actions' datacenter IPs, so xG can't be
# fetched from CI. This script fetches it from *this* machine's residential IP,
# then commits & pushes ONLY data/raw_data/xg_data.csv. GitHub CI's scheduled
# run then reads that fresh file and does everything else (merge, model, odds,
# dashboard, site). Because the merge is no-erase, a CI run that 403s just
# retains this file unchanged — no conflict.
#
# Safe to run anytime: it is a no-op if xG hasn't changed. Designed for launchd
# (see scripts/install_local_xg.sh) but also fine to run by hand.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

BRANCH="${CSL_BRANCH:-main}"
XG_FILE="data/raw_data/xg_data.csv"
# Full-season is robust (schedule-independent) and safe via the no-erase merge.
# Override with XG_MODE="" for the faster two-round incremental refresh.
XG_MODE="${XG_MODE:---full-season}"

log() { printf '%s  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }

# Single-instance lock so a slow network run can't overlap the next trigger.
LOCK="${TMPDIR:-/tmp}/cslmonitor-fetch-xg.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  log "Another fetch is already running ($LOCK). Exiting."
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT

# Activate the conda env, load .env.local, set PYTHONPATH (shared bootstrap).
source "$REPO/scripts/common.sh"
csl_bootstrap

log "Repo: $REPO  |  env: ${CONDA_DEFAULT_ENV:-?}  |  branch: $BRANCH  |  mode: ${XG_MODE:-incremental}"

# 1) Sync to the latest main so we build on CI's newest committed data.
git switch --quiet "$BRANCH"
git fetch --quiet origin "$BRANCH"
git pull --quiet --rebase origin "$BRANCH"

# 2) Fetch fresh xG from the official SofaScore API (writes xg_data.csv).
log "Fetching xG ${XG_MODE:+($XG_MODE)} ..."
"$PYTHON" -m csl.xg.xg_pipeline ${XG_MODE:+$XG_MODE}

# 3) Commit only xg_data.csv, and only if it actually changed.
if git diff --quiet -- "$XG_FILE"; then
  log "No xG changes — nothing to commit. Done."
  exit 0
fi

git add "$XG_FILE"
git commit --quiet -m "chore(xg): refresh xG from SofaScore (local $(date +%Y-%m-%d))"
log "Committed xG update."

# 4) Push, rebasing if CI pushed in the meantime.
for attempt in 1 2 3; do
  if git pull --quiet --rebase origin "$BRANCH" && git push --quiet origin "$BRANCH"; then
    log "Pushed to origin/$BRANCH. Done."
    exit 0
  fi
  log "Push attempt $attempt failed; retrying in 5s ..."
  sleep 5
done

log "ERROR: push failed after 3 attempts." >&2
exit 1
