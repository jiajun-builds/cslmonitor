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
- Prefer running commands from the repository root: `/Users/jordan/Projects/Chinese Super League Prediction`
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

## Key Source Modules
- Fixtures/results ingestion: `src/csl/fixtures/chn_fixture_v5.py`
- xG pipeline: `src/csl/xg/xg_pipeline.py`
- xG merge: `src/csl/xg/chn_merge.py`
- expected-goals-plus calculation: `src/csl/xg/compute_expg.py`
- Dixon-Coles model: `src/csl/models/dc.py`
- dashboard CSV export: `src/csl/dashboard/export_dashboard_csv.py`
- dashboard JSON export: `src/csl/dashboard/export_dashboard_json.py`
- Pinnacle fetch: `src/csl/odds/fetch_pinnacle_spreads.py`
- market comparison export: `src/csl/odds/export_upcoming_market_comparison.py`
- canonical path helpers: `src/csl/paths.py`

## Important Data Paths

### Raw Inputs
- Main match table: `data/raw_data/CHN_Super League.csv`
- fresh fixture/schedule pull: `data/raw_data/chinese_super_league_data.csv`
- upcoming fixtures for dashboard/export: `data/raw_data/chn_upcoming_fixtures.csv`
- xG data: `data/raw_data/xg_data.csv`
- Pinnacle spreads: `data/raw_data/CHN_pinnacle_spreads.csv`
- backups: `data/raw_data/backups/`

### Model / Processed Outputs
- team name mapping: `data/output_data/CHN_team_name_mapping.csv`
- team stats: `data/output_data/CHN_team_stats.csv`
- match simulations: `data/output_data/CHN_team_stats_match_simulations.csv`
- market comparison: `data/output_data/CHN_upcoming_market_comparison.csv`

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

## Agent Tips
- Prefer `./scripts/csl.sh` over direct module execution for local workflow tasks.
- If a task is only "update the data", use `./scripts/csl.sh update`.
- If a task needs a fresh public dashboard bundle, `./scripts/csl.sh all` is the primary end-to-end command.
- If a task touches the dashboard data but not the raw pipeline, `./scripts/csl.sh publish` is the fastest rebuild path.
