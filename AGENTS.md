# AGENTS.md

## Project Snapshot
- Project purpose: update Chinese Super League match data, compute xG-derived features, run a Dixon-Coles model, and export dashboard- and market-comparison datasets.
- Main Python package: `src/csl/`
- Repository root entry points:
  - `./scripts/csl.sh`
  - `./scripts/run_csl_update.sh`
  - `./scripts/csl-model.sh`
  - `python DC_CHN.py`

## Environment
- Conda environment: `csl-workflows`
- Python: `3.11`
- Core packages from `environment.yml`: `pandas`, `numpy`, `scipy`, `scikit-learn`, `matplotlib`, `requests`
- Pip package: `penaltyblog`

## Setup
```bash
conda env create -f environment.yml
conda activate csl-workflows
cp .env.local.example .env.local
```

## Execution Conventions
- Prefer running commands from the repository root: `/Users/jordan/Developer/python/cslmonitor`
- The preferred local workflow entry point is `./scripts/csl.sh`
- `./scripts/csl.sh`, `./scripts/run_csl_update.sh`, and `./scripts/csl-model.sh` activate Conda, load `.env.local`, and set `PYTHONPATH` automatically
- `.env.local` is local-only and should define:
  - `RAPIDAPI_KEY`
  - `THE_ODDS_API_KEY`
- Conda initialization defaults to `~/anaconda3/etc/profile.d/conda.sh`

## Primary Workflows

### 1. Full Local Workflow
Run:
```bash
./scripts/csl.sh all
```

This command performs these steps, in order:
1. Data update pipeline
2. Model export
3. Pinnacle odds fetch
4. market comparison export
5. dashboard CSV / JSON export
6. GitHub Pages `site/` build

### 2. Data Update Pipeline
Run:
```bash
./scripts/csl.sh update
```

This maps to:
- `./scripts/run_csl_update.sh`

### 3. Run the Prediction Model
Run either:
```bash
./scripts/csl.sh model
```

or:
```bash
python DC_CHN.py
```

Outputs:
- `data/output_data/CHN_team_stats.csv`
- `data/output_data/CHN_team_stats_match_simulations.csv`

Implementation notes:
- The model entry point is `DC_CHN.py`
- Core model code is in `src/csl/models/dc.py`
- `DC_CHN.py` currently uses absolute paths for its input and output CSVs

### 4. Export Dashboard Files
Run:
```bash
./scripts/csl.sh dashboard
```

CSV outputs:
- `data/dashboard/csv/dashboard_meta.csv`
- `data/dashboard/csv/upcoming_fixtures.csv`
- `data/dashboard/csv/match_predictions.csv`
- `data/dashboard/csv/team_strength_rankings.csv`
- `data/dashboard/csv/upcoming_market_comparison.csv` if market comparison has been generated

JSON outputs:
- `data/dashboard/json/dashboard_meta.json`
- `data/dashboard/json/upcoming_fixtures.json`
- `data/dashboard/json/match_predictions.json`
- `data/dashboard/json/team_strength_rankings.json`
- `data/dashboard/json/upcoming_market_comparison.json` if the source CSV exists

### 5. Fetch Pinnacle Odds and Market Comparison
Requires local `.env.local` or exported shell vars for:
```bash
THE_ODDS_API_KEY=...
```

Run:
```bash
./scripts/csl.sh odds
```

Default output:
- `data/raw_data/CHN_pinnacle_spreads.csv`
- `data/output_data/CHN_upcoming_market_comparison.csv`
- `data/dashboard/csv/upcoming_market_comparison.csv`

Notes:
- Uses The Odds API
- Fetch target is `soccer_china_superleague`
- Bookmaker is fixed to `pinnacle`
- Market is fixed to `spreads`
- Team-name normalization depends on `data/output_data/CHN_team_name_mapping.csv`

### 6. Build GitHub Pages Site
Run:
```bash
./scripts/build_dashboard_site.sh
```

Outputs:
- `site/index.html`
- `site/app.js`
- `site/styles.css`
- `site/assets/`
- `site/data/*.json`

### 7. Rebuild Publish Artifacts
Run:
```bash
./scripts/csl.sh publish
```

This rebuilds:
- dashboard CSV / JSON
- GitHub Pages `site/`

## Automation (GitHub Actions)
Three workflows in `.github/workflows/` (scheduled workflows only run from `main`):
- **`csl-refresh.yml` (`name: CSL Refresh`) — dual-mode.** Mode is resolved from the
  trigger (cron string / `workflow_dispatch` `mode` input):
  - `full` — daily `17 9` Europe/London cron → `./scripts/csl.sh all` (data + model +
    odds + dashboard + site). Runs the model, so it (re)writes `CHN_model_meta.json`.
  - `odds` — every-3h `0 */3` UTC cron → `./scripts/csl.sh odds && ./scripts/csl.sh publish`
    (re-fetch the "Now" line + rebuild the site). Has a pre-spend `/sports` quota guard
    (skips if remaining < 50) and **never writes the history CSV** or the model sidecar.
  Uses a cached conda env (`use-mamba` + `actions/cache` on the pkgs dir); kept
  `conda-incubator/setup-miniconda` because `scripts/common.sh` needs the `conda` command.
- **`capture-odds.yml`** — every-10-min opening-line capture tick; independent concurrency
  group. Two jobs: `capture` (lightweight pandas+requests) appends opening lines to the
  history CSV and exposes an `appended` output; `publish` runs **only when `appended == 'true'`**
  — it sets up the conda env, runs `./scripts/csl.sh republish` (rebuild comparison + site
  from the existing Now-line + updated history, **no `/odds` spend**), commits the dashboard
  artifacts, and deploys Pages itself (job-level `concurrency: pages` to serialize with
  `deploy-pages.yml`). This surfaces a fresh open line on the site within one tick instead of
  waiting up to ~3h for the next `odds` refresh, while idle ticks skip the publish job entirely.
- **`deploy-pages.yml`** — builds + deploys Pages; `push` is path-filtered, and it chains
  off the `CSL Refresh` `workflow_run` (so both `full` and `odds` runs redeploy). The
  capture-driven redeploy above is done inside `capture-odds.yml`, not here.

All writer workflows push with a rebase+retry loop to survive the push race between the
3h refresh, the daily refresh, and the 10-min capture tick.

Free Odds-API budget ≈ 290–310 of 500 requests/month (30 daily + 240 for 3h + ~20–40 capture).

## Key Source Modules
- Fixtures/results ingestion: `src/csl/fixtures/chn_fixture_v5.py`
- xG pipeline: `src/csl/xg/xg_pipeline.py`
- xG merge: `src/csl/xg/chn_merge.py`
- expected-goals-plus calculation: `src/csl/xg/compute_expg.py`
- Dixon-Coles model: `src/csl/models/dc.py`
- dashboard CSV export: `src/csl/dashboard/export_dashboard_csv.py` (emits `updated_at`
  = export time AND `model_updated_at` = last model-fit time, read from the
  `CHN_model_meta.json` sidecar via `paths.model_meta_json()`)
- dashboard JSON export: `src/csl/dashboard/export_dashboard_json.py`
- Pinnacle fetch (single "current" snapshot): `src/csl/odds/fetch_pinnacle_spreads.py`
- market comparison export (now + captured-open, with per-side EV): `src/csl/odds/export_upcoming_market_comparison.py`
- Pinnacle opening-time calendar: `src/csl/odds/opening_calendar.py` (`python -m csl.odds.opening_calendar`; `build_open_windows()` returns tz-aware windows for the scheduler)
- odds-capture history store (append-only): `src/csl/odds/snapshot_store.py`
- single-shot snapshot capture: `src/csl/odds/capture_snapshot.py` (`python -m csl.odds.capture_snapshot`)
- scheduler tick (captures opening lines in-window): `src/csl/odds/capture_scheduler.py` (`python -m csl.odds.capture_scheduler`)
- canonical path helpers: `src/csl/paths.py`

## Important Data Paths

### Raw Inputs
- Main match table: `data/raw_data/CHN_Super League.csv`
- fresh fixture/schedule pull: `data/raw_data/chinese_super_league_data.csv`
- upcoming fixtures for dashboard/export: `data/raw_data/chn_upcoming_fixtures.csv`
- xG data: `data/raw_data/xg_data.csv`
- Pinnacle spreads (single current snapshot, overwritten each run): `data/raw_data/CHN_pinnacle_spreads.csv`
- Pinnacle spreads capture history (append-only, tracked in git so the GitHub capture
  workflow can persist it): `data/raw_data/CHN_pinnacle_spreads_history.csv`
- backups: `data/raw_data/backups/`

### Model / Processed Outputs
- team name mapping: `data/output_data/CHN_team_name_mapping.csv`
- team stats: `data/output_data/CHN_team_stats.csv`
- match simulations: `data/output_data/CHN_team_stats_match_simulations.csv`
- market comparison: `data/output_data/CHN_upcoming_market_comparison.csv`
- opening-time calendar (predicted Pinnacle open windows): `data/output_data/CHN_opening_time_calendar.csv`
- model-fit timestamp sidecar (written by `DC_CHN.py`, read by the dashboard meta
  export; NOT touched by odds-only refreshes so it stays pinned to the last model run):
  `data/output_data/CHN_model_meta.json`

### Dashboard Assets
- CSV directory: `data/dashboard/csv/`
- JSON directory: `data/dashboard/json/`
- static frontend: `dashboard/`

## External Dependencies
- `csl.fixtures.chn_fixture_v5` depends on TheSportsDB
- `csl.xg.xg_pipeline` depends on SofaScore / RapidAPI and requires `RAPIDAPI_KEY`
- `csl.odds.fetch_pinnacle_spreads` depends on The Odds API

## Validation Guidance
- There is no dedicated test suite in the repository root.
- Practical validation is usually done by running the relevant entry point and checking the expected CSV/JSON outputs.
- For model experimentation, use:
  - `DC_CHN.py`
  - `model comparison/`

## Strategy Context & Findings

### What the project is ultimately for
The dashboard/market-comparison output feeds a **CLV-based betting strategy**: find fixtures
where the model diverges from the market and bet +EV lines at aggregator books.
- The thesis is **not** "beat Pinnacle closing" (closing is assumed efficient). It is
  "beat Pinnacle **opening**" — get down early at soft/aggregator books at prices better
  than even Pinnacle, before the market corrects.
- Success metric is long-run **+CLV** (closing line value vs Pinnacle close), not per-bet
  wins. "Bet early ⇒ +CLV" is an *assumption* whose direction depends on model quality.
- **Biggest gap:** opening/closing lines are not captured automatically, so CLV is measured
  manually today (selection-bias risk) and the edge is unvalidated. Closing that loop is the
  roadmap below.

### Model
- `src/csl/models/dc.py` is named "Dixon-Coles" but actually fits
  `ZeroInflatedPoissonGoalsModel` (ZIP) on **xG targets** (`HExpG+`/`AExpG+`), 18-month
  window, `xi=0.001`, Dixon-Coles time-decay weights.
- **Finding (diagnostic `model comparison/zip_zero_inflation_param_test.py`):** the fitted
  zero-inflation parameter sits at its ~1e-6 floor in 100% of refits → ZIP has collapsed to
  Poisson. The ~0.0003 RPS edge of ZIP over Poisson on the backtest is noise. A future
  simplification is to swap production ZIP → plain `PoissonGoalsModel` (same accuracy,
  simpler/faster). Not yet done.
- The model is fit **twice** per full run (STEP 2 model export + STEP 4 market comparison),
  on identical inputs — redundant but cheap (seconds; small single-league data). Left as-is.
  Watch-out: `xi=0.001` is hardcoded in two places (`dc.py`/`DC_CHN.py` and
  `export_upcoming_market_comparison.MODEL_XI`); if they ever diverge the two exports would
  silently use different models.

### Timezone (important data quirk)
- Source CSV `Time` columns (`chinese_super_league_data.csv`, `chn_upcoming_fixtures.csv`)
  are **UTC (GMT / UK time WITHOUT daylight saving)**, *not* UK local wall-clock.
- Always parse as UTC and convert to `Europe/London` so summer (BST) fixtures get +1h.
  Treating raw values as already-local makes summer times 1h early. Handled in
  `export_dashboard_csv.py` and `opening_calendar.py`.

### Pinnacle opening-time pattern (validated 2026-07-03)
- Pinnacle opens a match's line within **~1h after the later of the two teams' most-recent
  (current-round) matches has kicked off** (kickoff start, not full-time).
- `src/csl/odds/opening_calendar.py` predicts these windows from prior-round kickoffs.
  Field-validated: round-17 predicted windows matched the actual Pinnacle open times.
- This lets us catch the true opening (and closing) line on the **free** Odds-API plan
  (no historical-odds endpoint) by scheduling narrow captures.

## Roadmap / Open Tasks
1. **Verify the dashboard TZ fix at runtime** — run `python -m csl.dashboard.export_dashboard_csv`
   on the `csl-workflows` env and confirm a summer `kickoff_at` shows the London offset
   (`+01:00`) and metadata `timezone` reads `Europe/London`. (Fix is logic-checked, not yet
   run end-to-end.)
2. **Scheduled odds-capture pipeline — DONE (open side; close deferred to #3).**
   Delivered as four modules + a GitHub Actions workflow:
   - `snapshot_store.py` — append-only history CSV (`CHN_pinnacle_spreads_history.csv`),
     schema = `fetch_pinnacle_spreads.OUTPUT_COLUMNS` + `snapshot_type`/`target_round`/
     `capture_reason`; dedup key `(event_id, last_update, snapshot_type)`.
   - `capture_snapshot.py` — single-shot capture with a pre-spend quota guard (reads the
     free `/sports` endpoint first) and `--dry-run`.
   - `capture_scheduler.py` — "tick" run every ~10 min: captures a fixture's opening line
     only while it is inside its predicted open window and not yet captured; one `/odds`
     call covers the whole slate, non-in-window fixtures are discarded.
   - `.github/workflows/capture-odds.yml` — runs the tick on GitHub cron (UTC), commits new
     rows back to `main`. Only fires from the default branch; GitHub cron delay is tolerated
     because windows are ~1h and each fixture is captured at most once.
   The dashboard market-comparison now shows an **Open** and a **Now** group per fixture
   (line @ price + model EV each) plus a **Move** arrow; open EV is recomputed at the
   captured opening line. **Close/CLV columns are intentionally NOT built** — see #3.
   Free-plan quota: 500 requests/month; one `/odds` call = 1 request, `/sports` = 0.

   **Intraday extension — DONE (PR #17).** `csl-refresh.yml` is now dual-mode: the daily
   cron rebuilds the model, and a new every-3h `odds` cron refreshes only the "Now" line +
   site (see Automation section). Because odds-only publishes bump the dashboard export time
   every 3h, a persisted `model_updated_at` (from the `CHN_model_meta.json` sidecar) now
   travels through the meta export so the EV-panel footer shows **model-update time vs
   odds-fetch time** separately (`Model … · Odds fetched …`).
3. **Close the CLV loop:** join the user's bet-tracker fills to the captured closing lines →
   automated, auditable, per-segment CLV. Replaces manual CLV computation.
4. **Validation ladder for the edge** (before trusting it): paired Wilcoxon on per-fixture
   RPS (ZIP vs Poisson), and per-segment calibration / reliability diagrams (by handicap
   line, favourite vs underdog) — bet only in well-calibrated segments.
5. **Optional simplification:** swap production ZIP → `PoissonGoalsModel` in `dc.py`.
6. **Capture-loop hardening — DONE (two gaps found 2026-07-04, field-observed on round 18):**
   - **Monitor lag after capture — FIXED.** `capture-odds.yml` used to write the history CSV
     and stop, so a freshly captured opening line only surfaced at the next 3-hourly
     `csl-refresh odds` run (up to ~3h later). Now a gated `publish` job runs only when the
     tick appended rows: it runs `./scripts/csl.sh republish` (new command = rebuild
     `upcoming_market_comparison` + dashboard + site from the existing Now-line and updated
     history, **no `/odds` spend**) and deploys Pages. Idle ticks skip it. See Automation.
   - **1h-window feed-lag miss — FIXED.** The Odds API lists fixtures in waves; a fixture whose
     feed entry (or Pinnacle line) appeared only AFTER its predicted `[anchor, anchor+1h]`
     window closed was never captured (`pending_open_fixtures` requires `now ∈ window`) — on
     round 18, `Shanghai Port vs Dalian Yingbo` was at risk of a permanent miss. The scheduler
     now uses a wider **capture** window `capture_scheduler.DEFAULT_CAPTURE_WINDOW_HOURS` (6h),
     separate from the validated ~1h **display** window (`opening_calendar.DEFAULT_WINDOW_HOURS`,
     unchanged, still shown in the calendar). A still-uncaptured fixture is grabbed on first
     feed availability after its window, bounded so a long-open line isn't mislabeled `open`.

## Agent Tips
- Prefer `./scripts/csl.sh` over direct module execution for local workflow tasks.
- If a task is only "update the data", use `./scripts/csl.sh update`.
- If a task needs a fresh public dashboard bundle, `./scripts/csl.sh all` is the primary end-to-end command.
- If a task touches the dashboard data but not the raw pipeline, `./scripts/csl.sh publish` is the fastest rebuild path.
