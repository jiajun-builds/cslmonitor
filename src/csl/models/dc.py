import numpy as np
import pandas as pd
import penaltyblog as pb
from penaltyblog.models import FootballProbabilityGrid, dixon_coles_weights
from scipy.optimize import minimize_scalar
import os
from datetime import datetime

from csl.date_utils import parse_date_only_series

# Draw de-bias (backtest/backtest.md §12.4): every goals model in this family
# over-prices the draw (~0.28 predicted vs ~0.24 actual — independent-Poisson mass
# piling up at goal-difference 0). The fix is a market-free calibration: scale the
# scoreline-grid diagonal by a factor delta fit on the training window, then
# renormalize. Validated walk-forward in backtest/backtest_1x2.py before deploying
# here (out-of-sample it repairs roughly half the bias, draw 0.276 -> 0.255).
DRAW_DELTA_BOUNDS = (0.3, 2.0)
DRAW_DELTA_MIN_ROWS = 20  # below this, calibration is noise: fall back to 1.0


def fit_draw_delta(clf, train: pd.DataFrame, weights) -> float:
    """Fit the diagonal scale delta by maximizing the Dixon-Coles-weighted 1X2
    log-likelihood of the training fixtures. Needs no market data.

    With raw (pH, pD, pA) and z = 1 - pD + delta*pD, the adjusted outcome probs
    are (pH/z, delta*pD/z, pA/z) — identical to scaling the grid diagonal by
    delta and renormalizing, so this scalar fit matches what
    ``DrawCalibratedModel.predict`` applies to the full grid.
    """
    hg = pd.to_numeric(train["HG"], errors="coerce")
    ag = pd.to_numeric(train["AG"], errors="coerce")
    outcome = np.where(hg > ag, 0, np.where(hg == ag, 1, 2))
    valid = hg.notna().to_numpy() & ag.notna().to_numpy()

    cache: dict = {}
    P, ks, ws = [], [], []
    w_arr = np.asarray(weights)
    n_grid = None
    for i, r in enumerate(train.itertuples(index=False)):
        if not valid[i]:
            continue
        key = (r.Home, r.Away)
        if key not in cache:
            try:
                grid = np.asarray(clf.predict(r.Home, r.Away).grid)
                n_grid = grid.shape[0]
                diff = np.subtract.outer(np.arange(n_grid), np.arange(n_grid))
                v = np.array([grid[diff > 0].sum(), grid[diff == 0].sum(), grid[diff < 0].sum()])
                cache[key] = v / v.sum()
            except Exception:
                cache[key] = None
        if cache[key] is None:
            continue
        P.append(cache[key])
        ks.append(int(outcome[i]))
        ws.append(w_arr[i])
    if len(P) < DRAW_DELTA_MIN_ROWS:
        return 1.0

    P = np.asarray(P)
    k = np.asarray(ks)
    w = np.asarray(ws)
    d = P[:, 1]
    raw = P[np.arange(len(k)), k]

    def nll(delta):
        z = 1.0 - d + delta * d
        pk = np.where(k == 1, delta * d, raw) / z
        return -(w * np.log(np.clip(pk, 1e-12, None))).sum()

    return float(minimize_scalar(nll, bounds=DRAW_DELTA_BOUNDS, method="bounded").x)


class DrawCalibratedModel:
    """A fitted goals model with the §12.4 draw de-bias applied to every prediction.

    Wraps the underlying penaltyblog model; ``predict`` scales the scoreline-grid
    diagonal by ``draw_delta`` and renormalizes, returning a regular
    ``FootballProbabilityGrid`` so downstream consumers (1X2 aggregation,
    ``asian_handicap_probs``) are unaffected by the wrapping.
    """

    def __init__(self, clf, draw_delta: float):
        self._clf = clf
        self.draw_delta = float(draw_delta)

    @property
    def teams(self):
        return self._clf.teams

    @property
    def _params(self):
        return self._clf._params

    def get_params(self):
        return self._clf.get_params()

    def predict(self, home_team: str, away_team: str) -> FootballProbabilityGrid:
        pred = self._clf.predict(home_team, away_team)
        grid = np.asarray(pred.grid, dtype=float).copy()
        idx = np.arange(grid.shape[0])
        grid[idx, idx] *= self.draw_delta
        grid /= grid.sum()
        return FootballProbabilityGrid(
            grid, pred.home_goal_expectation, pred.away_goal_expectation
        )


def fit_dixon_coles_model_from_csv(input_csv_path, xi=0.001):
    """
    Load league data, apply the standard 18-month filter and fit the project
    model: penaltyblog's NegativeBinomialGoalModel on xG targets with
    Dixon-Coles time-decay weights, wrapped in the §12.4 draw de-bias
    calibration. Returns a DrawCalibratedModel.
    """
    df = pd.read_csv(input_csv_path)
    raw_dates = df["Date"].copy()

    # Accept both legacy slash dates and the canonical YYYY-MM-DD format.
    df["Date"] = parse_date_only_series(df["Date"])
    bad_dates = df["Date"].isna()
    if bad_dates.any():
        bad_values = raw_dates.loc[bad_dates].astype(str).head(10).tolist()
        raise ValueError(f"Found unparseable Date values in {input_csv_path}: {bad_values}")

    # Drop rows where 'Home' or 'Away' teams are missing
    df = df.dropna(subset=["Home", "Away"])

    # Ensure team names are strings
    df["Home"] = df["Home"].astype(str)
    df["Away"] = df["Away"].astype(str)

    # The model is trained on expected-goal targets, so rows without a full
    # HExpG+/AExpG+ pair cannot be used yet (for example, when xG is delayed).
    df["HExpG+"] = pd.to_numeric(df["HExpG+"], errors="coerce")
    df["AExpG+"] = pd.to_numeric(df["AExpG+"], errors="coerce")

    # Filter to most recent 1.5 years of data only
    # Uses the latest match date in the dataset as the reference point
    cutoff_date = df["Date"].max() - pd.DateOffset(months=18)
    df = df[df["Date"] >= cutoff_date]

    df = df.dropna(subset=["HExpG+", "AExpG+"]).copy()
    if df.empty:
        raise ValueError("No training rows remain after dropping missing HExpG+/AExpG+ values")

    # Generate time-decay weights so recent matches matter more
    weights = dixon_coles_weights(df["Date"], xi=xi)

    clf = pb.models.NegativeBinomialGoalModel(
        df["HExpG+"],
        df["AExpG+"],
        df["Home"],
        df["Away"],
        weights,
    )
    clf.fit()
    clf.get_params()

    draw_delta = fit_draw_delta(clf, df, weights)
    print(f"Draw de-bias delta (training-window calibration): {draw_delta:.3f}")
    return DrawCalibratedModel(clf, draw_delta)


def run_dixon_coles_model(input_csv_path, output_csv_path, xi=0.001):
    """
    Automates the model process: reading data, extracting teams, applying weights, fitting the model,
    extracting parameters, and saving results to a CSV file.

    Parameters:
        input_csv_path (str): Path to the input CSV file.
        output_csv_path (str): Path to save the output CSV file.
        xi (float): Decay factor for time weighting. Higher values down-weight older matches more
                    aggressively. Default is 0.001. Typical range: 0.0001 (slow decay) to 0.01 (fast decay).
    """
    # Step 1: Fit the shared model used across exports
    clf = fit_dixon_coles_model_from_csv(input_csv_path, xi=xi)

    # Step 2: Extract Parameters
    # Use clf.teams to guarantee team order matches the internal parameter array
    teams = clf.teams
    params = clf._params
    attack = params[:len(teams)]        # Attack values
    defense = params[len(teams):len(teams)*2]  # Defense values

    # Step 3: Create DataFrame for Team Statistics
    team_stats = pd.DataFrame({
        "Team": teams,
        "Attack": attack,
        "Defense": defense
    })
    team_stats["Date"] = datetime.now().strftime("%Y-%m-%d")

    # Step 4: Simulate Matches Between All Teams
    simulation_results = []
    for home_team in teams:
        for away_team in teams:
            if home_team != away_team:
                probs = clf.predict(home_team, away_team)
                results = {
                    "Home Team": home_team,
                    "Away Team": away_team,
                    "Home Win Probability": probs.asian_handicap("home", 0),
                    "Draw Probability": 1 - probs.asian_handicap("home", 0) - probs.asian_handicap("away", 0),
                    "Away Win Probability": probs.asian_handicap("away", 0),
                    "Home -1 Handicap": probs.asian_handicap("home", -1),
                    "Home -2 Handicap": probs.asian_handicap("home", -2),
                    "Away -1 Handicap": probs.asian_handicap("away", -1),
                    "Away -2 Handicap": probs.asian_handicap("away", -2),
                }
                simulation_results.append(results)

    match_simulations_df = pd.DataFrame(simulation_results)
    match_simulations_df["Date"] = datetime.now().strftime("%Y-%m-%d")

    # Reorder columns
    match_simulations_df = match_simulations_df[["Date", "Home Team", "Away Team", "Home Win Probability",
                                                 "Draw Probability", "Away Win Probability", "Home -1 Handicap",
                                                 "Home -2 Handicap", "Away -1 Handicap", "Away -2 Handicap"]]

    # Step 5: Save DataFrames to CSV
    team_stats.to_csv(output_csv_path, index=False)
    match_simulations_df.to_csv(output_csv_path.replace(".csv", "_match_simulations.csv"), index=False)

    print(f"Team stats and match simulation results successfully saved to: {output_csv_path}")
