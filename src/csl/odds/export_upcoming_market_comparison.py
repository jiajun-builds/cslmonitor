"""
Export upcoming CSL fixtures with model 1X2, Pinnacle spreads/odds, and
model settlement probabilities for the exact market handicap line.

Usage (仓库根目录，PYTHONPATH=src):
    python -m csl.odds.export_upcoming_market_comparison

Outputs:
    data/output_data/CHN_upcoming_market_comparison.csv
    data/dashboard/csv/upcoming_market_comparison.csv
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from csl.dashboard.export_dashboard_csv import _normalize_probabilities
from csl.models.dc import fit_dixon_coles_model_from_csv
from csl.paths import data_dashboard_csv_dir, data_output_dir, data_raw_dir

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

MODEL_XI = 0.001

FULL_COLUMNS = [
    "fixture_id",
    "round",
    "match_date",
    "match_time",
    "kickoff_at",
    "home_team",
    "away_team",
    "home_win_prob",
    "draw_prob",
    "away_win_prob",
    "home_spread",
    "away_spread",
    "home_odds",
    "away_odds",
    "bookmaker",
    "market",
    "regions",
    "last_update",
    "fetched_at",
    "home_ah_win_prob",
    "home_ah_push_prob",
    "home_ah_lose_prob",
    "home_ah_ev",
    "away_ah_win_prob",
    "away_ah_push_prob",
    "away_ah_lose_prob",
    "away_ah_ev",
]

DASHBOARD_COLUMNS = [
    "fixture_id",
    "match_date",
    "match_time",
    "home_team",
    "away_team",
    "home_win_prob",
    "draw_prob",
    "away_win_prob",
    "home_spread",
    "away_spread",
    "home_odds",
    "away_odds",
    "last_update",
    "fetched_at",
    "home_ah_win_prob",
    "home_ah_push_prob",
    "home_ah_lose_prob",
    "home_ah_ev",
    "away_ah_win_prob",
    "away_ah_push_prob",
    "away_ah_lose_prob",
    "away_ah_ev",
]


@dataclass(frozen=True)
class ExportPaths:
    upcoming_csv: str = os.path.join(data_dashboard_csv_dir(), "upcoming_fixtures.csv")
    simulations_csv: str = os.path.join(data_output_dir(), "CHN_team_stats_match_simulations.csv")
    pinnacle_csv: str = os.path.join(data_raw_dir(), "CHN_pinnacle_spreads.csv")
    matches_csv: str = os.path.join(data_raw_dir(), "CHN_Super League.csv")
    full_out_csv: str = os.path.join(data_output_dir(), "CHN_upcoming_market_comparison.csv")
    dashboard_out_csv: str = os.path.join(data_dashboard_csv_dir(), "upcoming_market_comparison.csv")


def _require_columns(df: pd.DataFrame, required: Iterable[str], label: str) -> None:
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"{label} missing required columns: {missing}")


def _read_csv_required(path: str, required: Iterable[str], label: str) -> pd.DataFrame:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"{label} not found: {path}")
    df = pd.read_csv(path)
    _require_columns(df, required, label)
    return df


def load_upcoming(path: str) -> pd.DataFrame:
    df = _read_csv_required(
        path,
        ["fixture_id", "round", "match_date", "match_time", "kickoff_at", "home_team", "away_team"],
        "upcoming_fixtures.csv",
    ).copy()
    df["home_team"] = df["home_team"].astype(str).str.strip()
    df["away_team"] = df["away_team"].astype(str).str.strip()
    return df


def load_simulations(path: str) -> pd.DataFrame:
    df = _read_csv_required(
        path,
        ["Home Team", "Away Team", "Home Win Probability", "Draw Probability", "Away Win Probability"],
        "CHN_team_stats_match_simulations.csv",
    ).rename(
        columns={
            "Home Team": "home_team",
            "Away Team": "away_team",
            "Home Win Probability": "home_win_prob",
            "Draw Probability": "draw_prob",
            "Away Win Probability": "away_win_prob",
        }
    ).copy()
    df["home_team"] = df["home_team"].astype(str).str.strip()
    df["away_team"] = df["away_team"].astype(str).str.strip()
    df = df[["home_team", "away_team", "home_win_prob", "draw_prob", "away_win_prob"]]

    dupes = df.duplicated(subset=["home_team", "away_team"], keep=False)
    if dupes.any():
        duplicated_pairs = df.loc[dupes, ["home_team", "away_team"]].drop_duplicates().to_dict("records")
        raise ValueError(f"Simulation table has duplicate home/away pairs: {duplicated_pairs}")

    df[["home_win_prob", "draw_prob", "away_win_prob"]] = df[
        ["home_win_prob", "draw_prob", "away_win_prob"]
    ].apply(pd.to_numeric, errors="coerce")
    return _normalize_probabilities(df)


def load_pinnacle(path: str) -> pd.DataFrame:
    df = _read_csv_required(
        path,
        [
            "event_id",
            "commence_time",
            "home_team",
            "away_team",
            "home_spread",
            "away_spread",
            "home_odds",
            "away_odds",
            "bookmaker",
            "market",
            "regions",
            "last_update",
            "fetched_at",
        ],
        "CHN_pinnacle_spreads.csv",
    ).copy()
    df["home_team"] = df["home_team"].astype(str).str.strip()
    df["away_team"] = df["away_team"].astype(str).str.strip()
    numeric_cols = ["home_spread", "away_spread", "home_odds", "away_odds"]
    df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors="coerce")

    dupes = df.duplicated(subset=["home_team", "away_team"], keep=False)
    if dupes.any():
        duplicated_pairs = df.loc[dupes, ["home_team", "away_team"]].drop_duplicates().to_dict("records")
        raise ValueError(f"Pinnacle odds table has duplicate home/away pairs: {duplicated_pairs}")

    return df


def build_base_frame(upcoming: pd.DataFrame, simulations: pd.DataFrame, pinnacle: pd.DataFrame) -> pd.DataFrame:
    merged = upcoming.merge(simulations, on=["home_team", "away_team"], how="left", validate="one_to_one")
    missing_sim = merged.loc[
        merged[["home_win_prob", "draw_prob", "away_win_prob"]].isna().any(axis=1),
        ["fixture_id", "home_team", "away_team"],
    ].to_dict("records")
    if missing_sim:
        raise ValueError(f"Missing simulation probabilities for upcoming fixtures: {missing_sim}")

    merged = merged.merge(
        pinnacle,
        on=["home_team", "away_team"],
        how="left",
        validate="one_to_one",
    )
    with_odds = merged[merged["event_id"].notna()].copy()
    return with_odds


def attach_market_probabilities(frame: pd.DataFrame, matches_csv: str, xi: float) -> pd.DataFrame:
    clf = fit_dixon_coles_model_from_csv(matches_csv, xi=xi)
    out = frame.copy()

    home_win_probs: list[float] = []
    home_push_probs: list[float] = []
    home_lose_probs: list[float] = []
    away_win_probs: list[float] = []
    away_push_probs: list[float] = []
    away_lose_probs: list[float] = []

    for row in out.itertuples(index=False):
        pred = clf.predict(row.home_team, row.away_team)
        home_probs = pred.asian_handicap_probs("home", float(row.home_spread))
        away_probs = pred.asian_handicap_probs("away", float(row.away_spread))

        home_win_probs.append(float(home_probs["win"]))
        home_push_probs.append(float(home_probs["push"]))
        home_lose_probs.append(float(home_probs["lose"]))
        away_win_probs.append(float(away_probs["win"]))
        away_push_probs.append(float(away_probs["push"]))
        away_lose_probs.append(float(away_probs["lose"]))

    out["home_ah_win_prob"] = home_win_probs
    out["home_ah_push_prob"] = home_push_probs
    out["home_ah_lose_prob"] = home_lose_probs
    out["away_ah_win_prob"] = away_win_probs
    out["away_ah_push_prob"] = away_push_probs
    out["away_ah_lose_prob"] = away_lose_probs
    out["home_ah_ev"] = (
        out["home_ah_win_prob"] * (out["home_odds"] - 1.0)
        - out["home_ah_lose_prob"]
    )
    out["away_ah_ev"] = (
        out["away_ah_win_prob"] * (out["away_odds"] - 1.0)
        - out["away_ah_lose_prob"]
    )
    return out


def validate_market_probabilities(frame: pd.DataFrame) -> None:
    for prefix in ("home_ah", "away_ah"):
        cols = [f"{prefix}_win_prob", f"{prefix}_push_prob", f"{prefix}_lose_prob"]
        if frame[cols].isna().any(axis=1).any():
            bad = frame.loc[frame[cols].isna().any(axis=1), ["fixture_id", "home_team", "away_team"]].to_dict("records")
            raise ValueError(f"Missing {prefix} settlement probabilities: {bad}")
        total = frame[cols].sum(axis=1)
        if not ((total - 1.0).abs() <= 1e-6).all():
            bad = frame.loc[(total - 1.0).abs() > 1e-6, ["fixture_id", "home_team", "away_team"]].to_dict("records")
            raise ValueError(f"{prefix} settlement probabilities do not sum to 1: {bad}")
    for col in ("home_ah_ev", "away_ah_ev"):
        if frame[col].isna().any():
            bad = frame.loc[frame[col].isna(), ["fixture_id", "home_team", "away_team"]].to_dict("records")
            raise ValueError(f"Missing EV values in {col}: {bad}")


def write_csv(df: pd.DataFrame, path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    df.to_csv(path, index=False)
    log.info("Wrote %s (%d rows)", path, len(df))


def run(
    *,
    upcoming_csv: str,
    simulations_csv: str,
    pinnacle_csv: str,
    matches_csv: str,
    full_out_csv: str,
    dashboard_out_csv: str,
    xi: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    upcoming = load_upcoming(upcoming_csv)
    simulations = load_simulations(simulations_csv)
    pinnacle = load_pinnacle(pinnacle_csv)

    base = build_base_frame(upcoming, simulations, pinnacle)
    log.info("Matched %d upcoming fixtures with Pinnacle odds out of %d total upcoming fixtures", len(base), len(upcoming))
    enriched = attach_market_probabilities(base, matches_csv, xi)
    validate_market_probabilities(enriched)

    full_df = enriched[FULL_COLUMNS].copy()
    dashboard_df = enriched[DASHBOARD_COLUMNS].copy()

    write_csv(full_df, full_out_csv)
    write_csv(dashboard_df, dashboard_out_csv)
    return full_df, dashboard_df


def main() -> None:
    paths = ExportPaths()
    parser = argparse.ArgumentParser(
        description="Export upcoming CSL fixtures with model probabilities and Pinnacle market comparison"
    )
    parser.add_argument("--upcoming", default=paths.upcoming_csv, help="Path to upcoming_fixtures.csv")
    parser.add_argument("--simulations", default=paths.simulations_csv, help="Path to CHN_team_stats_match_simulations.csv")
    parser.add_argument("--pinnacle", default=paths.pinnacle_csv, help="Path to CHN_pinnacle_spreads.csv")
    parser.add_argument("--matches", default=paths.matches_csv, help="Path to CHN_Super League.csv")
    parser.add_argument("--out", default=paths.full_out_csv, help="Path to full comparison CSV output")
    parser.add_argument(
        "--dashboard-out",
        default=paths.dashboard_out_csv,
        help="Path to dashboard comparison CSV output",
    )
    parser.add_argument("--xi", type=float, default=MODEL_XI, help="Dixon-Coles time-decay factor")
    args = parser.parse_args()

    try:
        run(
            upcoming_csv=args.upcoming,
            simulations_csv=args.simulations,
            pinnacle_csv=args.pinnacle,
            matches_csv=args.matches,
            full_out_csv=args.out,
            dashboard_out_csv=args.dashboard_out,
            xi=args.xi,
        )
    except Exception as exc:  # pragma: no cover - top-level CLI guard
        log.error("%s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
