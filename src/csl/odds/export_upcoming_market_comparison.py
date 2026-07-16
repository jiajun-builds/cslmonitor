"""
Export upcoming CSL fixtures with de-biased model 1X2 probabilities and
Pinnacle moneyline odds (opening capture vs current "Now" line), plus model EV
for every outcome at both prices.

Draw de-bias is hybrid (AGENTS.md roadmap #10, validated in backtest.md §12):

  * Fixture WITH a captured opening 1X2 -> market-anchored shrink at
    ``DEBIAS_LAMBDA``: starting from the RAW (un-δ'd) model grid,
    ``p'_D = (1-λ)·p_D + λ·m_D`` where ``m_D`` is the no-vig opening draw
    probability; the freed mass is returned to H/A pro-rata. Anchoring on the
    raw grid (``predict_raw``) avoids stacking λ on top of the δ calibration.
  * Fixture WITHOUT a captured open -> δ-calibrated model (``predict``), the
    same market-free calibration used by the all-pairs prediction surface.

The ``debias_method`` column records which path produced each row's
probabilities ("market_anchor" or "delta"); EV columns are consistent with the
row's probabilities: ``EV_k = p'_k * odds_k - 1``.

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

import numpy as np
import pandas as pd

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

# Market-anchored draw shrink weight. backtest.md §12: λ=0.75 lands the
# walk-forward draw mean on the actual rate (0.245 vs 0.242) and doubles excess
# CLV at thr>0.10; the result holds over the surrounding λ region, not a point.
DEBIAS_LAMBDA = 0.75

# Opening-price columns joined from the capture history (snapshot_type=open).
# Blank for fixtures whose open has not been captured yet.
OPEN_COLUMNS = [
    "open_home_odds",
    "open_draw_odds",
    "open_away_odds",
    "open_home_ev",
    "open_draw_ev",
    "open_away_ev",
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
    "debias_method",
    "home_odds",
    "draw_odds",
    "away_odds",
    "bookmaker",
    "market",
    "regions",
    "last_update",
    "fetched_at",
    "home_ev",
    "draw_ev",
    "away_ev",
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
    "debias_method",
    "home_odds",
    "draw_odds",
    "away_odds",
    "last_update",
    "fetched_at",
    "home_ev",
    "draw_ev",
    "away_ev",
    *OPEN_COLUMNS,
]


@dataclass(frozen=True)
class ExportPaths:
    upcoming_csv: str = os.path.join(data_dashboard_csv_dir(), "upcoming_fixtures.csv")
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


def load_pinnacle(path: str) -> pd.DataFrame:
    df = _read_csv_required(
        path,
        [
            "event_id",
            "commence_time",
            "home_team",
            "away_team",
            "home_odds",
            "draw_odds",
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
    numeric_cols = ["home_odds", "draw_odds", "away_odds"]
    df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors="coerce")

    dupes = df.duplicated(subset=["home_team", "away_team"], keep=False)
    if dupes.any():
        duplicated_pairs = df.loc[dupes, ["home_team", "away_team"]].drop_duplicates().to_dict("records")
        raise ValueError(f"Pinnacle odds table has duplicate home/away pairs: {duplicated_pairs}")

    return df


OPEN_SNAPSHOT_COLUMNS = [
    "home_team",
    "away_team",
    "open_home_odds",
    "open_draw_odds",
    "open_away_odds",
    "open_last_update",
]


def load_open_snapshots(path: str) -> pd.DataFrame:
    """One opening-price row per fixture from the capture history (may be empty).

    Reads the append-only capture history, keeps ``snapshot_type == "open"`` rows,
    and — since a line can in principle be captured more than once — takes the
    earliest ``fetched_at`` per fixture as the true opening prices. Returns a frame
    keyed by (home_team, away_team) with ``open_*`` 1X2 odds columns, or an empty
    (correctly-columned) frame when no opens have been captured yet.
    """
    hist = load_history(path)
    opens = hist[hist["snapshot_type"] == "open"] if not hist.empty else hist
    if opens.empty:
        return pd.DataFrame(columns=OPEN_SNAPSHOT_COLUMNS)

    opens = opens.copy()
    opens["home_team"] = opens["home_team"].astype(str).str.strip()
    opens["away_team"] = opens["away_team"].astype(str).str.strip()
    for col in ("home_odds", "draw_odds", "away_odds"):
        opens[col] = pd.to_numeric(opens[col], errors="coerce")

    opens = opens.sort_values("fetched_at").drop_duplicates(
        subset=["home_team", "away_team"], keep="first"
    )
    opens = opens.rename(
        columns={
            "home_odds": "open_home_odds",
            "draw_odds": "open_draw_odds",
            "away_odds": "open_away_odds",
            "last_update": "open_last_update",
        }
    )
    return opens[OPEN_SNAPSHOT_COLUMNS]


def build_base_frame(
    upcoming: pd.DataFrame,
    pinnacle: pd.DataFrame,
    opens: pd.DataFrame,
    *,
    now: pd.Timestamp | None = None,
) -> pd.DataFrame:
    merged = upcoming.merge(
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
    has_open = merged["open_home_odds"].notna()
    keep = has_now | (has_open & is_upcoming)
    return merged[keep].copy()


def _grid_1x2(pred) -> tuple[float, float, float]:
    """Aggregate a scoreline grid to normalized (home, draw, away) probabilities."""
    grid = np.asarray(pred.grid, dtype=float)
    n = grid.shape[0]
    diff = np.subtract.outer(np.arange(n), np.arange(n))
    v = np.array([grid[diff > 0].sum(), grid[diff == 0].sum(), grid[diff < 0].sum()])
    v = v / v.sum()
    return float(v[0]), float(v[1]), float(v[2])


def anchored_probs(
    raw: tuple[float, float, float],
    open_odds: tuple[float, float, float],
    lam: float,
) -> tuple[float, float, float]:
    """Market-anchored draw shrink (backtest.md §12) on raw model probabilities.

    ``m_D`` is the no-vig draw probability implied by the opening 1X2 prices;
    the draw moves λ of the way to it and the freed mass goes back to H/A
    pro-rata, preserving their relative strength.
    """
    p_h, p_d, p_a = raw
    inv = np.array([1.0 / o for o in open_odds])
    m_d = float(inv[1] / inv.sum())
    p_d_new = (1.0 - lam) * p_d + lam * m_d
    scale = (1.0 - p_d_new) / (1.0 - p_d)
    return p_h * scale, p_d_new, p_a * scale


def attach_model_probabilities(
    frame: pd.DataFrame, matches_csv: str, xi: float, lam: float = DEBIAS_LAMBDA
) -> pd.DataFrame:
    clf = fit_dixon_coles_model_from_csv(matches_csv, xi=xi)
    out = frame.copy()

    nan = float("nan")
    probs_h: list[float] = []
    probs_d: list[float] = []
    probs_a: list[float] = []
    methods: list[str] = []

    for row in out.itertuples(index=False):
        open_odds = (row.open_home_odds, row.open_draw_odds, row.open_away_odds)
        try:
            if all(pd.notna(o) and float(o) > 1.0 for o in open_odds):
                raw = _grid_1x2(clf.predict_raw(row.home_team, row.away_team))
                p = anchored_probs(raw, tuple(float(o) for o in open_odds), lam)
                method = "market_anchor"
            else:
                p = _grid_1x2(clf.predict(row.home_team, row.away_team))
                method = "delta"
        except Exception as exc:
            raise ValueError(
                f"Model prediction failed for {row.home_team} vs {row.away_team}: {exc}"
            ) from exc
        probs_h.append(p[0])
        probs_d.append(p[1])
        probs_a.append(p[2])
        methods.append(method)

    out["home_win_prob"] = probs_h
    out["draw_prob"] = probs_d
    out["away_win_prob"] = probs_a
    out["debias_method"] = methods

    # EV per outcome, consistent with the row's (de-biased) probabilities.
    for side, prob_col in (("home", "home_win_prob"), ("draw", "draw_prob"), ("away", "away_win_prob")):
        now_odds = pd.to_numeric(out[f"{side}_odds"], errors="coerce")
        open_odds_col = pd.to_numeric(out[f"open_{side}_odds"], errors="coerce")
        out[f"{side}_ev"] = np.where(now_odds.notna(), out[prob_col] * now_odds - 1.0, nan)
        out[f"open_{side}_ev"] = np.where(open_odds_col.notna(), out[prob_col] * open_odds_col - 1.0, nan)

    return out


def validate_model_probabilities(frame: pd.DataFrame) -> None:
    prob_cols = ["home_win_prob", "draw_prob", "away_win_prob"]
    if frame[prob_cols].isna().any(axis=1).any():
        bad = frame.loc[frame[prob_cols].isna().any(axis=1), ["fixture_id", "home_team", "away_team"]].to_dict("records")
        raise ValueError(f"Missing model 1X2 probabilities: {bad}")
    total = frame[prob_cols].sum(axis=1)
    if not ((total - 1.0).abs() <= 1e-6).all():
        bad = frame.loc[(total - 1.0).abs() > 1e-6, ["fixture_id", "home_team", "away_team"]].to_dict("records")
        raise ValueError(f"Model 1X2 probabilities do not sum to 1: {bad}")
    if ((frame[prob_cols] <= 0) | (frame[prob_cols] >= 1)).any(axis=1).any():
        bad = frame.loc[
            ((frame[prob_cols] <= 0) | (frame[prob_cols] >= 1)).any(axis=1),
            ["fixture_id", "home_team", "away_team"],
        ].to_dict("records")
        raise ValueError(f"Model 1X2 probabilities out of (0, 1): {bad}")

    # Now-side EVs must exist exactly where a current Now line does; open-side
    # EVs exactly where an opening capture does.
    now_rows = frame[frame["event_id"].notna()]
    for col in ("home_ev", "draw_ev", "away_ev"):
        if now_rows[col].isna().any():
            bad = now_rows.loc[now_rows[col].isna(), ["fixture_id", "home_team", "away_team"]].to_dict("records")
            raise ValueError(f"Missing EV values in {col}: {bad}")
    open_rows = frame[frame["open_home_odds"].notna()]
    for col in ("open_home_ev", "open_draw_ev", "open_away_ev"):
        if open_rows[col].isna().any():
            bad = open_rows.loc[open_rows[col].isna(), ["fixture_id", "home_team", "away_team"]].to_dict("records")
            raise ValueError(f"Missing EV values in {col}: {bad}")


def write_csv(df: pd.DataFrame, path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    df.to_csv(path, index=False)
    log.info("Wrote %s (%d rows)", path, len(df))


def run(
    *,
    upcoming_csv: str,
    pinnacle_csv: str,
    matches_csv: str,
    history_csv: str,
    full_out_csv: str,
    dashboard_out_csv: str,
    xi: float,
    lam: float = DEBIAS_LAMBDA,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    upcoming = load_upcoming(upcoming_csv)
    pinnacle = load_pinnacle(pinnacle_csv)

    opens = load_open_snapshots(history_csv)
    base = build_base_frame(upcoming, pinnacle, opens)
    n_now = int(base["event_id"].notna().sum())
    n_open = int(base["open_home_odds"].notna().sum())
    n_open_only = int((base["event_id"].isna() & base["open_home_odds"].notna()).sum())
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

    enriched = attach_model_probabilities(base, matches_csv, xi, lam)
    validate_model_probabilities(enriched)
    log.info(
        "De-bias split: %d market_anchor (λ=%.2f), %d delta fallback",
        int((enriched["debias_method"] == "market_anchor").sum()),
        lam,
        int((enriched["debias_method"] == "delta").sum()),
    )

    full_df = enriched[FULL_COLUMNS].copy()
    dashboard_df = enriched[DASHBOARD_COLUMNS].copy()

    write_csv(full_df, full_out_csv)
    write_csv(dashboard_df, dashboard_out_csv)
    return full_df, dashboard_df


def main() -> None:
    paths = ExportPaths()
    parser = argparse.ArgumentParser(
        description="Export upcoming CSL fixtures with de-biased model 1X2 probabilities and Pinnacle moneyline comparison"
    )
    parser.add_argument("--upcoming", default=paths.upcoming_csv, help="Path to upcoming_fixtures.csv")
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
    parser.add_argument("--lam", type=float, default=DEBIAS_LAMBDA,
                        help="Market-anchored draw shrink weight λ (default: 0.75, backtest.md §12)")
    args = parser.parse_args()

    try:
        run(
            upcoming_csv=args.upcoming,
            pinnacle_csv=args.pinnacle,
            matches_csv=args.matches,
            history_csv=args.history,
            full_out_csv=args.out,
            dashboard_out_csv=args.dashboard_out,
            xi=args.xi,
            lam=args.lam,
        )
    except Exception as exc:  # pragma: no cover - top-level CLI guard
        log.error("%s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
