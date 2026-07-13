# Opening-Line Asian-Handicap Backtest

The first unbiased, full-slate test of the project's CLV thesis — *can the model
beat Pinnacle's **opening** Asian-handicap line?* Everything here settles bets
against real results at the real opening prices, so the output is realized ROI
at open (the ground truth that CLV is only a proxy for), not a simulated edge.

Files in this folder:

| File | What it is |
| --- | --- |
| `backtest_open_ah.py` | The walk-forward backtest (self-contained, no API spend). |
| `backtest_open_ah_bets.csv` | Per-bet detail (one row per gradeable match). |
| `backtest_open_ah_summary.csv` | Per-threshold ROI / SE / t / profit / win-rate. |
| `backtest.md` | This document. |

## 1. Data

- **Source:** `data/raw_data/CHN_Super League.csv`, columns
  `pinnacle_open_ah` (home handicap; negative = home favoured),
  `pinnacle_open_ah_h`, `pinnacle_open_ah_a` (decimal prices).
- These opening lines are **maintained manually** and are *not* part of the
  automation-refreshed production schema. A fresh checkout will have those
  columns empty/absent until they are filled in, and the backtest will have
  nothing to grade until then.
- Current run: **2026 season, rounds 1–17**, 136 gradeable matches
  (open line + result), 107 bettable after the walk-forward warm-up.
- The opening prices embed an average overround of **~5.3%** — the hurdle any
  edge has to clear.

## 2. Strategy under test

The production betting recipe, applied honestly out-of-sample:

1. **Refit the production model per round**, walk-forward, on data strictly
   *before* that round — `ZeroInflatedPoissonGoalsModel` on xG targets
   (`HExpG+`/`AExpG+`), 18-month trailing window, `xi=0.001`, Dixon-Coles
   time-decay weights. (Mirrors `src/csl/models/dc.py`.)
2. For each match, turn the model's 15×15 scoreline grid into an **exact
   expected return** for backing the home side and for backing the away side at
   that match's opening line and prices.
3. **Back the higher-EV side** if its model EV per unit stake clears a
   threshold. Thresholds tested: `0.00, 0.02, 0.05, 0.10`.
4. Flat 1-unit stakes; P/L accumulated across the season.

## 3. Backtest logic (why it is trustworthy)

- **No leakage.** The training window is strictly `Date < match_date` and
  trimmed to the trailing 18 months; a team unseen in that window (e.g. a
  promoted side) is skipped rather than guessed.
- **Exact handicap settlement from the raw grid**, not
  `FootballProbabilityGrid.asian_handicap()`. penaltyblog's helper mishandles
  quarter-line push mass (returns identical values for `0.0 / -0.25 / -0.5`), so
  we collapse the 15×15 grid to `P(goal difference)` and settle every line
  ourselves: **quarter lines** (`4·line` odd, e.g. `-0.25`, `-0.75`) split the
  stake half/half across the two neighbouring half-lines; **integer lines** push
  and refund the stake; otherwise win pays `odds−1`, loss pays `−1`.
- **Away side** is the home computation with the goal difference and the line
  both flipped, priced at the away odds.
- **Dates** are parsed with `csl.date_utils.parse_date_only_series` (handles both
  ISO and legacy `DD/MM/YYYY`); a naive `to_datetime()` would drop every day>12
  row and month/day-swap the rest, corrupting the walk-forward ordering.

## 4. Metrics reported

- **Baselines** — always-home and always-away ROI at the opening line, so the
  strategy is judged against naïve flat betting, not against zero.
- **Threshold table** — for each EV threshold: `n_bets`, ROI (mean per-bet P/L),
  `SE = sd/√n`, `t = ROI/SE`, total profit, win-rate, and mean predicted EV.
  Because per-bet P/L has sd ≈ 1, SE ≈ 0.1 at n ≈ 100, so **any |ROI| within ~1
  SE of zero is indistinguishable from zero; |t| > ~2 is the bar for a real
  edge.**
- **Model-EV honesty check** — mean *predicted* EV vs *realized* ROI on the same
  bets. A large positive gap means the model's handicap-cover probabilities are
  overconfident, not merely unlucky.
- **EV calibration buckets** — `+EV` bets split into quartiles by predicted EV;
  if the model is useful for staking, higher predicted EV should map to higher
  realized ROI (monotonic).
- **Per-round P/L** — to eyeball variance across the season.

## 5. Results (current run)

| EV threshold | n_bets | ROI | SE | t | win% |
| ---: | ---: | ---: | ---: | ---: | ---: |
| ≥ 0.00 | 107 | **−6.26%** | 0.085 | −0.74 | 46.7% |
| ≥ 0.02 | 94 | −2.01% | 0.090 | −0.22 | 47.9% |
| ≥ 0.05 | 80 | **+4.41%** | 0.100 | +0.44 | 52.5% |
| ≥ 0.10 | 64 | −3.66% | 0.112 | −0.33 | 48.4% |

**How to read it:**

- **No threshold beats zero.** Every |t| < 1 — all four ROIs are within one
  standard error of zero. There is no measured edge here.
- The **+4.4% at the 5% threshold is noise**, not a signal: it is inside 1 SE of
  zero and it *disappears* at the 10% threshold. Predicted EV does **not** sort
  realized ROI monotonically, which is the calibration a staking rule needs.
- **Model-EV honesty check:** on the 107 `+EV` bets the model predicted a mean
  EV of **+16.9%/unit** but realized **−6.3%/unit** — it **overstates its own
  edge by ~23%/unit.** The problem is not variance; the model's cover
  probabilities are systematically overconfident.

## 6. Interpretation

- At opening lines, the model as-is has **no tradeable edge**, and its EV is
  badly miscalibrated. Betting on raw model EV would lose to the overround.
- This measures **realized ROI at open, not CLV** — no closing lines are
  captured yet. But ROI at open is exactly what +CLV is supposed to predict, so
  a model with no ROI-at-open signal has no demonstrated CLV edge either.
- The companion grid search (`model comparison/xi_lookback_grid_test.py`)
  independently shows production `xi=0.001` / 18-month is within sampling noise
  of the grid optimum — so **the lever is not `xi`/lookback tuning, it is
  probability calibration.**

## 7. Recommendations

1. **Do not stake on raw model EV at opening lines yet.** There is no measured
   edge and the EV is inflated ~23%/unit.
2. **Calibrate before betting (roadmap #4).** Build per-segment reliability
   diagrams (by handicap line, favourite vs underdog) and shrink the model's
   probabilities (e.g. temperature scaling) until predicted EV ≈ realized ROI.
   Then bet only in segments that are actually well-calibrated.
3. **Stop tuning `xi`/lookback for this** — the grid already rules that out as
   the lever. Spend the effort on calibration/shrinkage instead.
4. **Capture closing lines (roadmap #3)** to measure true CLV; the opening-only
   test cannot see it.
5. **Treat these numbers as directional.** n ≈ 100 over a single season; SE ≈ 0.1
   means even a real ±5% edge would be hard to confirm here. Re-run as more
   rounds complete.

## 8. Reproducing

```bash
# From the repo root, in the csl-workflows env (or any env with penaltyblog).
# Requires the pinnacle_open_ah* columns to be present in the main CSV.
PYTHONPATH=src python backtest/backtest_open_ah.py
```

Outputs `backtest_open_ah_bets.csv` and `backtest_open_ah_summary.csv` next to
the script.
