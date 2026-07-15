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
  - `THE_ODDS_API_KEY`  (xG uses the official SofaScore API — no key needed)
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

### Dashboard refresh behaviour (two independent update streams)
The page updates via **two streams** with different cadences/triggers — reason about them
separately. The **Now** stream is independent of opening windows (always runs on schedule);
the **Open** stream only writes when a fixture is inside its capture window, not yet captured,
and present in the Odds API feed.

| Stream   | Page columns it drives                         | Driven by      | Cadence / trigger                                   | Spends `/odds`?          |
| -------- | ---------------------------------------------- | -------------- | --------------------------------------------------- | ------------------------ |
| **Now**  | "Now" line/odds, model EV, Move-arrow baseline | `CSL Refresh`  | odds every 3h (UTC `0 */3`) + daily `full` 09:17 LDN | 1 per run                |
| **Open** | "Open" line/odds (the opening line)            | `capture-odds` | 10-min tick; in-window + uncaptured + present-in-feed | 1 only when it captures |

Scenario matrix (behaviour reflects the gated `publish` job + 6h capture window, roadmap #6):

| Situation                          | `capture-odds` tick                                   | `CSL Refresh`             | What the page shows                                      |
| ---------------------------------- | ----------------------------------------------------- | ------------------------- | ------------------------------------------------------- |
| **Outside any capture window**     | idle (0 req, no commit, no rebuild)                   | Now refresh every 3h      | Now cols update 3-hourly; Open cols static              |
| **In window, feed has the fixture**| captures → append → gated `publish` rebuild + deploy  | 3h refresh continues      | Open cols appear within ~1 tick; Now every 3h           |
| **In window, feed lacks it yet**   | nothing this tick; retries each tick (6h window)      | 3h refresh continues      | Open cols blank until the feed lists it (arrives in waves) |
| **Fixture already captured**       | skipped (an `open` row exists)                        | 3h refresh continues      | Open locked to the true opening line; Move tracks Now vs Open |
| **Quota < 50 remaining**           | capture aborts (`min-remaining` guard)                | odds refresh skips fetch  | Both streams pause until the monthly quota reset        |
| **Manual dispatch**                | `Capture Odds` (optional `dry_run`)                   | `CSL Refresh` `mode=full`/`odds` | Forces the corresponding refresh                 |

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
- `csl.xg.xg_pipeline` depends on the official SofaScore API via `curl_cffi` browser impersonation (no key); the merge lets fresh values win (xG tracks SofaScore's latest) but a blank scrape never erases an xG already in the cache
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
- **IMPORTANT UPDATE (2026-07-13, extended 2026-07-15):** the "model finds +EV vs Pinnacle's
  opening line" half of this thesis has been tested at length. **Asian handicap: falsified
  outright** (2026-07-13, winner's curse). **1X2: the strategy as specified is dead — 61% of its
  stake sits on a draw-probability bug — but the direction survives** (2026-07-15; drop the draw
  and a baseline-adjusted +CLV holds in all three seasons, though it is still short of the vig
  bar). Read "Betting-edge investigation — conclusions" below and `backtest/backtest.md`
  §11.3 + §11.7 **before quoting any CLV number** — an "always bet home" coin beats this model on
  raw CLV, and breakeven needs CLV > 2.61pp. **The draw de-bias was then built and tested
  (2026-07-15, `backtest.md` §12): it fixes the model (excess CLV doubles) but the strategy still
  fails the vig bar in 2024/2025 — betting Pinnacle's open is closed.** The one live direction is
  the *earliest/cheapest-opening book* (roadmap #8): the de-biased model's +1.2–2.5pp excess CLV
  would clear breakeven at a ≤5%-overround book.

### Model
- `src/csl/models/dc.py` is named "Dixon-Coles" and since **v2.5 (2026-07-15)** fits
  `NegativeBinomialGoalModel` on **xG targets** (`HExpG+`/`AExpG+`), 18-month window,
  `xi=0.001`, Dixon-Coles time-decay weights, **wrapped in a draw de-bias**
  (`DrawCalibratedModel`): a scale δ for the scoreline-grid diagonal is fit on the
  training window by weighted 1X2 log-likelihood (`fit_draw_delta`) and applied to every
  predicted grid. Rationale + walk-forward validation: `backtest/backtest.md` §12.4
  (NegBinom = best RPS/log-loss, §9.4; the de-bias repairs ~half of the structural ~4pp
  draw over-pricing, out-of-sample draw 0.276 → 0.255 vs actual 0.242; current
  production fit δ ≈ 0.91).
- **History:** production previously fit `ZeroInflatedPoissonGoalsModel` (ZIP), whose
  zero-inflation parameter sat at its ~1e-6 floor in 100% of refits (diagnostic
  `model comparison/zip_zero_inflation_param_test.py`) — ZIP had collapsed to Poisson,
  so the swap changed accuracy only via NegBinom's over-dispersion.
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

### Betting-edge investigation — conclusions (2026-07-13)
A full test of whether the model produces a tradeable edge at the opening line.
**Bottom line: it does not, and calibration/distribution changes do not create one.**
The only surviving hypothesis is line *timing* (bet the earliest, softest line before
Pinnacle forms it). Full detail + numbers in `backtest/backtest.md` §9–§10; analysis
scripts in `backtest/` and `model comparison/distribution_comparison.py`.

- **Opening-line AH backtest (826 bets, 4 seasons):** no EV threshold beats zero; realized
  ROI −4% to −8% and *worse* the more selective; model overstates its own EV by ~20%/unit at
  **t=6**, replicated in all four seasons; highest-EV bets are the worst.
- **The overstatement is winner's curse (selection bias), NOT a distribution defect.**
  Symmetric home-cover calibration is ~0 (unbiased); the overconfidence appears *only* once
  you condition on "the side the model likes most". Proven by simulation: an unbiased model +
  efficient market + "bet the +EV side" reproduces ~+14% overstatement from pure noise. So
  only a model genuinely *more accurate than the market* removes it — reshaping a distribution
  cannot.
- **Calibration doesn't fix it.** Walk-forward temperature scaling (T≈1.5) barely dents the
  overstatement (+19.3%→+18.4%). 1X2 is well-calibrated (ECE 0.032); handicap-cover is not
  (ECE 0.086, worst on big lines) because Poisson/ZIP under-disperses the goal-difference
  (margin) distribution.
- **No distribution helps the betting.** NegBinom is the most accurate 1X2 predictor (best RPS,
  ~1.5% better log-loss than ZIP — over-dispersion genuinely helps prediction) but bets
  *slightly worse*; all six distributions overstate EV +17–23%. **A `ZIP→NegBinom` swap in
  `dc.py` is justified for accuracy only, not betting edge.** (ZIP == Poisson exactly; still
  collapsed — see prior finding above.)
- **Line-magnitude filter doesn't rescue it.** Big lines (>2) catastrophic (−29% ROI); small
  lines (≤0.5) less bad (−3.6%) but still overstate EV +17% (t=3.66). Only takeaway: avoid
  big-favourite lines.
- **CLV (open→close, 2023–24 only — 2025 close lines empty):** overround compresses open 6.1%
  → close 4.0% (~1pp/side vig headwind); no naive rule gets significant +CLV; model picks
  +0.69pp (t=1.9) but weakens with EV threshold (noise-like) and is net-negative after vig.

#### 1X2 opening line — strategy dead, direction alive (2026-07-15, `backtest/backtest.md` §11)
The AH result prompted a switch to Pinnacle **1X2** open+close. The user backfilled 2024–25
(611 gradeable matches, 2024 R1–2026 R18; 2023 unusable — no training history). Betting the
highest-EV outcome **loses** (EV>0.10: ROI −4.8%, t=−0.57; 2024 alone −23.8%, t=−1.98; full
Kelly → 0). But unlike AH the failure is **one fixable defect**, not the whole idea:
- **THE DRAW BUG (the defect).** Model draw prob pinned at ~0.279 vs market 0.234 ≈ actual
  0.242 — high by ~4pp in *every* season and *every* match type (structural: independent-Poisson
  piles mass at goal-diff 0). Lethal interaction with the EV rule: at draw prob 0.28, EV>0.10
  fires whenever the draw is priced > 1.10/0.28 = **3.93**, and the CSL median opening draw
  price is **3.79** — so every above-median draw becomes a bet. **61% of all stake sits on the
  bug, carrying ZERO CLV** (+0.03pp, t=0.22). Worst bucket: draws priced 4.5–6, model says 28%,
  reality 8% (n=40, ROI −62%). **Drop the draw → CLV triples (+0.66 → +2.15pp), survives the
  baseline adjustment (+1.73pp, t=2.51), positive in all 3 seasons.** Still not profitable
  (ROI doesn't replicate: 2024 −5.5% / 2025 −16.9% / 2026 +53.9%).
- **METHODOLOGY — two rules that must be applied to any future CLV claim:**
  1. **Always compute the model-free baseline (§11.3).** This market drifts toward the home team
     every season (+0.91pp overall). **"Always bet home" scores +0.91pp CLV (t=2.84) — better
     than the model's +0.42pp.** The model bets home 165/away 71 and inherits that drift free.
     Report **excess CLV** (model − same-outcome/same-season drift), never raw. The 2026-only
     "signal" that motivated the whole 1X2 thread was largely this artifact.
  2. **The vig wall (§11.7): EV > 0 ⟺ CLV > p × R.** With p≈0.344 and Pinnacle's **opening
     overround 7.55%**, breakeven needs **CLV > 2.61pp**. This is why `always home` earns +0.91pp
     CLV and still returns −4.8%. Everything the model knows is worth ~2–3pp; the vig costs 2.61.
- **Data quality:** an overround<0 sweep found exactly 1 bad cell in 611 (a `368.00` typo for
  `3.68`, fixed). Opening overround median 7.56%, closing 4.72% — the odds data is sound.
- **NegBinom** changes none of this and does **not** fix the draw (0.276 vs ZIP 0.279).

**Reframe / where the edge could still be:** AH is dead outright; 1X2 as-specified is dead but
its *direction* survives a draw fix (above). Either way the user bets via **Sportmarket** (a
sharp-book aggregator/brokerage) on *newly-opened* CSL lines, and the strongest remaining play is
**catching the earliest-opening book before Pinnacle** — the earliest line is softest, and if it
converges toward Pinnacle's close you capture +CLV *without* model edge and *without* winner's
curse. Line-timing/microstructure, not prediction. **The vig wall makes this more valuable, not
less:** everything the model knows is worth ~2–3pp of CLV while Pinnacle's opening vig alone
costs 2.61pp, so the same +2.15pp CLV loses into a 7.55% open and wins into a 4% book. **Paying
less beats predicting better.** See roadmap #8.

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
   **Update (2026-07-13):** an open→close CLV analysis was run on the manually-entered lines
   (2023–24 only; 2025 close lines empty) — **no rule beats the close** once the ~1pp/side
   open-vs-close vig headwind is counted; model picks +0.69pp CLV but net-negative. See the
   2026-07-13 findings above and `backtest/backtest.md` §9.6. Superseded in priority by #8.
4. **Validation ladder for the edge** (before trusting it): paired Wilcoxon on per-fixture
   RPS (ZIP vs Poisson), and per-segment calibration / reliability diagrams (by handicap
   line, favourite vs underdog) — bet only in well-calibrated segments.
   **Update (2026-07-13) — DONE, negative.** The reliability diagrams were built
   (`backtest/calibration_diagnostic.py`) and calibration was attempted (temperature scaling,
   `backtest/backtest_open_ah_calibrated.py`). Calibration does **not** create an edge: the EV
   overstatement is winner's curse, not a fixable miscalibration (see the 2026-07-13 findings).
   Do not re-attempt "calibrate then bet the opening line" — it is a closed dead end.
5. **Optional simplification: swap production ZIP → `PoissonGoalsModel` — SUPERSEDED.**
   Production moved ZIP → `NegBinomialGoalModel` + draw de-bias instead (v2.5, roadmap #9).
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
   - **Open-only fixtures now shown — FIXED.** The comparison used to keep only fixtures with a
     current **Now** line (`build_base_frame` filtered on `event_id.notna()`), so a fixture
     captured *before* it appeared in a Now-line fetch (e.g. round-18 `Shenzhen vs Qingdao West
     Coast`, captured at 12:45 while the 12:04 Now line lacked it) stayed invisible until the
     next `odds` refresh — even though its opening line was in the history. `build_base_frame`
     now keeps a fixture with a Now line **or** a captured open line (open-only rows render Now
     columns as `--`), gated to a **future kickoff** so already-kicked-off matches don't linger
     once the feed drops them. Now-side probs/EV are left NaN for open-only rows and
     `validate_market_probabilities` skips them; `getBestBet` in `app.js` treats a null Now EV
     as NaN so an open-only fixture is never chosen as the best bet.

7. **Date-parse bug in `model comparison/` scripts — FIXED (2026-07-12).** A naive
   `pd.to_datetime(df["Date"], errors="coerce")` is correct on ISO `YYYY-MM-DD` but on
   `DD/MM/YYYY` it coerces every day>12 row to `NaT` and month/day-swaps the rest, corrupting
   the walk-forward training windows. The bug was **dormant** (the committed CSV was ISO) until
   a manual spreadsheet re-save — made while adding the Pinnacle opening lines — rewrote the
   working-tree CSV to `DD/MM/YYYY` and activated it. Production was never affected:
   `src/csl/models/dc.py` already uses `csl.date_utils.parse_date_only_series` (handles both
   formats). Fix: (a) the three active scripts (`xi_lookback_grid_test.py`,
   `zip_zero_inflation_param_test.py`, `poisson_vs_zip_18mo_test.py`) now use
   `parse_date_only_series`; the re-run reproduces the original correct grid, so those findings
   STAND (production `xi=0.001`/18mo ranks within noise of the optimum). (b) `chn_merge.py` now
   **canonicalizes the `Date` column to ISO on write** via `format_date_only_series` (defensive:
   only overwrites cleanly-parsed rows), so any future manual `DD/MM/YYYY` re-save self-heals on
   the next pipeline run instead of silently reactivating locale-dependent parsing downstream.
   The opening-line AH backtest built on this data lives in `backtest/` (see `backtest/backtest.md`).

8. **Earliest-opening-line edge — the strongest live direction (NEW 2026-07-13, promoted
   2026-07-15).** AH is closed outright; 1X2 as-specified is closed too (though a draw fix may
   revive it — see #9). The untested, winner's-curse-free hypothesis: the user bets via
   **Sportmarket** (sharp-book aggregator) on newly-opened lines; if some book opens a CSL line
   *before* Pinnacle, that earliest line is the softest and may be exploitable before the market
   sharpens.
   - **Why this got MORE valuable (the vig wall, `backtest/backtest.md` §11.7):** EV > 0 ⟺
     CLV > p × R. Everything the model knows is worth ~2–3pp of CLV, but Pinnacle's **7.55%
     opening overround alone costs 2.61pp** — so the model's best strategy (+2.15pp CLV) *loses*
     into Pinnacle's open and would *win* into a 4% book. **Paying less beats predicting
     better.** This is now a stronger lever than any model work.
   - **Blocked on reconnaissance (user in progress):** identify which book opens CSL lines
     earlier than Pinnacle, by how much, whether it is exposed by name in The Odds API /
     Sportmarket, and how its early line compares to Pinnacle's open→close.
   - **Then:** if The Odds API carries that book, widen `fetch_pinnacle_spreads` beyond the
     hardcoded `pinnacle`/`spreads` to capture its opening line + timestamp; measure whether
     the earliest line moves toward Pinnacle's close (→ +CLV, exploitable) using the CLV logic
     from `backtest/backtest.md` §9.6. If it already ≈ close, this door is closed too.
   - **Measure it correctly:** any candidate book must be scored with **excess CLV over the
     model-free baseline** (§11.3 — this market drifts +0.91pp/season toward the home team, so
     raw CLV lies) and against the **p × R** bar (§11.7). Its overround matters as much as its
     line.
   - **Data gaps:** no soft-book odds anywhere (the blocker — every line on file is Pinnacle);
     close AH only 2023–24. Pinnacle 1X2 open+close is now complete for 2024–26 (2023 has only
     56 opens and no usable training history) — useful here as the *benchmark* an earlier book's
     line gets measured against.

9. **Draw de-bias (+ ZIP→NegBinom) — TESTED, bar not cleared (2026-07-15, backtest phase
   DONE).** The backtest verdict is in `backtest/backtest.md` §12; `backtest/backtest_1x2.py`
   now carries the full variant grid. Background: the model's draw probability is pinned at
   ~0.279 vs the market's 0.234 and an actual 0.242 — structural (independent-Poisson mass at
   goal-diff 0), 61% of the §11 strategy's stake sat on it.
   - **Mechanism (user-chosen): market-anchored shrink**, per match, no leakage —
     `p'_D = (1−λ)·p_D + λ·m_D` with `m_D` = no-vig *opening* draw prob, freed mass returned
     to home/away pro-rata. λ grid {0.25, 0.5, 0.75, 1.0}, not walk-forward-optimised.
   - **As a model fix it works:** draw prob repaired (0.245 at λ=0.75 vs actual 0.242), stake
     migrates off the bug (draw picks 63%→0%), **excess CLV roughly doubles** (+0.60 →
     +1.42pp at thr>0.10, t=3.2; +2.0–2.5pp at thr>0.20), 0.25-Kelly goes from −59% to +20%.
   - **As a betting strategy it still fails the success bar:** per-season gap (CLV − p×R) is
     **negative in 2024 and 2025 at every λ** (2024 λ=1: exCLV −0.10pp — no signal there at
     all); only 2026 clears, the same one-season shape as the §11.1 false signal. ZIP+λ=1 ≈
     NegBinom+λ=1: the distribution swap contributes ~nothing to CLV, it's all the de-bias.
   - **Consequences:** (a) do NOT build a 1X2 betting pipeline against Pinnacle's open;
     (b) strongest quantified case yet for roadmap #8 — the surviving +1.2–2.5pp excess CLV
     clears the breakeven bar at a ≤5%-overround book (bar ≈ 1.4–1.75pp) while losing into
     Pinnacle's 7.55% open.
   - **Production deployment (v2.5, 2026-07-15, user-approved):** the market-anchored λ
     needs a 1X2 anchor production doesn't have (adding h2h would double /odds quota cost),
     so the deployed mechanism is the **market-free δ calibration** (`backtest.md` §12.4):
     fit walk-forward-validated first (no degradation; repairs ~half the bias, draw
     0.276 → 0.255), then shipped in `dc.py` as `NegativeBinomialGoalModel` +
     `DrawCalibratedModel` (δ ≈ 0.91 on the current fit). Dashboard bumped to **v2.5**
     with model name "Negative Binomial with Dixon-Coles Time Decay". For *accuracy*,
     not betting — the betting verdict above stands.


## Agent Tips
- Prefer `./scripts/csl.sh` over direct module execution for local workflow tasks.
- If a task is only "update the data", use `./scripts/csl.sh update`.
- If a task needs a fresh public dashboard bundle, `./scripts/csl.sh all` is the primary end-to-end command.
- If a task touches the dashboard data but not the raw pipeline, `./scripts/csl.sh publish` is the fastest rebuild path.
