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
from csl.odds.snapshot_store import HISTORY_CSV, load_history
from csl.paths import data_dashboard_csv_dir, data_output_dir, data_raw_dir

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

MODEL_XI = 0.001

# Opening-line columns joined from the capture history (snapshot_type=open). These
# are blank for fixtures whose open line has not been captured yet.
OPEN_COLUMNS = [
    "open_home_spread",
    "open_away_spread",
    "open_home_odds",
    "open_away_odds",
    "open_home_ah_ev",
    "open_away_ah_ev",
    "open_last_update",
]

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
    *OPEN_COLUMNS,
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
    *OPEN_COLUMNS,
]


@dataclass(frozen=True)
class ExportPaths:
    upcoming_csv: str = os.path.join(data_dashboard_csv_dir(), "upcoming_fixtures.csv")
    simulations_csv: str = os.path.join(data_output_dir(), "CHN_team_stats_match_simulations.csv")
    pinnacle_csv: str = os.path.join(data_raw_dir(), "CHN_pinnacle_spreads.csv")
    matches_csv: str = os.path.join(data_raw_dir(), "CHN_Super League.csv")
    history_csv: str = HISTORY_CSV
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


OPEN_SNAPSHOT_COLUMNS = [
    "home_team",
    "away_team",
    "open_home_spread",
    "open_away_spread",
    "open_home_odds",
    "open_away_odds",
    "open_last_update",
]


def load_open_snapshots(path: str) -> pd.DataFrame:
    """One opening-line row per fixture from the capture history (may be empty).

    Reads the append-only capture history, keeps ``snapshot_type == "open"`` rows,
    and — since a line can in principle be captured more than once — takes the
    earliest ``fetched_at`` per fixture as the true opening line. Returns a frame
    keyed by (home_team, away_team) with ``open_*`` spread/odds columns, or an
    empty (correctly-columned) frame when no opens have been captured yet.
    """
    hist = load_history(path)
    opens = hist[hist["snapshot_type"] == "open"] if not hist.empty else hist
    if opens.empty:
        return pd.DataFrame(columns=OPEN_SNAPSHOT_COLUMNS)

    opens = opens.copy()
    opens["home_team"] = opens["home_team"].astype(str).str.strip()
    opens["away_team"] = opens["away_team"].astype(str).str.strip()
    for col in ("home_spread", "away_spread", "home_odds", "away_odds"):
        opens[col] = pd.to_numeric(opens[col], errors="coerce")

    opens = opens.sort_values("fetched_at").drop_duplicates(
        subset=["home_team", "away_team"], keep="first"
    )
    opens = opens.rename(
        columns={
            "home_spread": "open_home_spread",
            "away_spread": "open_away_spread",
            "home_odds": "open_home_odds",
            "away_odds": "open_away_odds",
            "last_update": "open_last_update",
        }
    )
    return opens[OPEN_SNAPSHOT_COLUMNS]


def build_base_frame(
    upcoming: pd.DataFrame,
    simulations: pd.DataFrame,
    pinnacle: pd.DataFrame,
    opens: pd.DataFrame,
    *,
    now: pd.Timestamp | None = None,
) -> pd.DataFrame:
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
    merged = merged.merge(opens, on=["home_team", "away_team"], how="left", validate="one_to_one")
    # Keep a fixture if it has a current Now line (Pinnacle event_id) OR a captured
    # opening line. Open-only fixtures — captured before they appeared in a Now-line
    # fetch — are shown with blank Now columns rather than dropped, so a freshly
    # captured open line surfaces immediately instead of waiting for the next Now fetch.
    # Now-line fixtures come from the live feed and are inherently upcoming; an open-only
    # fixture is gated to a future kickoff so already-kicked-off matches don't linger on
    # the board until the daily upcoming CSV trims them (the feed drops them at kickoff,
    # which used to self-clean the comparison before open-only rows were surfaced).
    now = now or pd.Timestamp.now(tz="UTC")
    kickoff = pd.to_datetime(merged["kickoff_at"], utc=True, errors="coerce")
    is_upcoming = kickoff.isna() | (kickoff >= now)
    has_now = merged["event_id"].notna()
    has_open = merged["open_home_spread"].notna()
    keep = has_now | (has_open & is_upcoming)
    return merged[keep].copy()


def _ah_ev(pred, side: str, spread: float, odds: float) -> float:
    """Model expected value of one unit staked on an Asian-handicap side.

    EV = P(win) * (odds - 1) - P(lose); a half-win/half-lose quarter line is
    already reflected in the win/lose split returned by ``asian_handicap_probs``.
    """
    probs = pred.asian_handicap_probs(side, float(spread))
    return float(probs["win"]) * (float(odds) - 1.0) - float(probs["lose"])


def attach_market_probabilities(frame: pd.DataFrame, matches_csv: str, xi: float) -> pd.DataFrame:
    clf = fit_dixon_coles_model_from_csv(matches_csv, xi=xi)
    out = frame.copy()

    has_open = "open_home_spread" in out.columns

    home_win_probs: list[float] = []
    home_push_probs: list[float] = []
    home_lose_probs: list[float] = []
    away_win_probs: list[float] = []
    away_push_probs: list[float] = []
    away_lose_probs: list[float] = []
    open_home_evs: list[float] = []
    open_away_evs: list[float] = []

    nan = float("nan")
    for row in out.itertuples(index=False):
        pred = clf.predict(row.home_team, row.away_team)

        # Now-side settlement probs only exist where a current Now line does; an
        # open-only fixture has no Now handicap yet, so leave these NaN (rendered "--").
        if pd.notna(row.home_spread) and pd.notna(row.away_spread):
            home_probs = pred.asian_handicap_probs("home", float(row.home_spread))
            away_probs = pred.asian_handicap_probs("away", float(row.away_spread))
            home_win_probs.append(float(home_probs["win"]))
            home_push_probs.append(float(home_probs["push"]))
            home_lose_probs.append(float(home_probs["lose"]))
            away_win_probs.append(float(away_probs["win"]))
            away_push_probs.append(float(away_probs["push"]))
            away_lose_probs.append(float(away_probs["lose"]))
        else:
            home_win_probs.append(nan)
            home_push_probs.append(nan)
            home_lose_probs.append(nan)
            away_win_probs.append(nan)
            away_push_probs.append(nan)
            away_lose_probs.append(nan)

        # Open EV at the captured opening line, reusing the same fitted model.
        # Left as NaN for fixtures whose open line hasn't been captured.
        if has_open:
            oh_spread = getattr(row, "open_home_spread", None)
            oh_odds = getattr(row, "open_home_odds", None)
            oa_spread = getattr(row, "open_away_spread", None)
            oa_odds = getattr(row, "open_away_odds", None)
            open_home_evs.append(
                _ah_ev(pred, "home", oh_spread, oh_odds)
                if pd.notna(oh_spread) and pd.notna(oh_odds) else float("nan")
            )
            open_away_evs.append(
                _ah_ev(pred, "away", oa_spread, oa_odds)
                if pd.notna(oa_spread) and pd.notna(oa_odds) else float("nan")
            )

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
    if has_open:
        out["open_home_ah_ev"] = open_home_evs
        out["open_away_ah_ev"] = open_away_evs
    return out


def validate_market_probabilities(frame: pd.DataFrame) -> None:
    # Now-side settlement probs/EV only exist for fixtures with a current Now line;
    # open-only rows legitimately carry NaN there, so restrict these checks to Now rows.
    now = frame[frame["event_id"].notna()]
    for prefix in ("home_ah", "away_ah"):
        cols = [f"{prefix}_win_prob", f"{prefix}_push_prob", f"{prefix}_lose_prob"]
        if now[cols].isna().any(axis=1).any():
            bad = now.loc[now[cols].isna().any(axis=1), ["fixture_id", "home_team", "away_team"]].to_dict("records")
            raise ValueError(f"Missing {prefix} settlement probabilities: {bad}")
        total = now[cols].sum(axis=1)
        if not ((total - 1.0).abs() <= 1e-6).all():
            bad = now.loc[(total - 1.0).abs() > 1e-6, ["fixture_id", "home_team", "away_team"]].to_dict("records")
            raise ValueError(f"{prefix} settlement probabilities do not sum to 1: {bad}")
    for col in ("home_ah_ev", "away_ah_ev"):
        if now[col].isna().any():
            bad = now.loc[now[col].isna(), ["fixture_id", "home_team", "away_team"]].to_dict("records")
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
    history_csv: str,
    full_out_csv: str,
    dashboard_out_csv: str,
    xi: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    upcoming = load_upcoming(upcoming_csv)
    simulations = load_simulations(simulations_csv)
    pinnacle = load_pinnacle(pinnacle_csv)

    opens = load_open_snapshots(history_csv)
    base = build_base_frame(upcoming, simulations, pinnacle, opens)
    n_now = int(base["event_id"].notna().sum())
    n_open = int(base["open_home_spread"].notna().sum())
    n_open_only = int((base["event_id"].isna() & base["open_home_spread"].notna()).sum())
    log.info(
        "Comparison fixtures: %d of %d upcoming (%d with Now line, %d with open line, %d open-only)",
        len(base), len(upcoming), n_now, n_open, n_open_only,
    )

    if base.empty:
        log.info("No fixtures matched with Pinnacle odds; writing empty outputs and skipping model fit")
        full_df = pd.DataFrame(columns=FULL_COLUMNS)
        dashboard_df = pd.DataFrame(columns=DASHBOARD_COLUMNS)
        write_csv(full_df, full_out_csv)
        write_csv(dashboard_df, dashboard_out_csv)
        return full_df, dashboard_df

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
    parser.add_argument("--history", default=paths.history_csv, help="Path to CHN_pinnacle_spreads_history.csv")
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
            history_csv=args.history,
            full_out_csv=args.out,
            dashboard_out_csv=args.dashboard_out,
            xi=args.xi,
        )
    except Exception as exc:  # pragma: no cover - top-level CLI guard
        log.error("%s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
