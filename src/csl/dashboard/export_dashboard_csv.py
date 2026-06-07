from __future__ import annotations

import logging
import math
import os
import re
import sys
from dataclasses import dataclass
from typing import Iterable
from zoneinfo import ZoneInfo

import pandas as pd

from csl.date_utils import format_date_only_series, parse_date_only_series
from csl.paths import data_dashboard_csv_dir, data_output_dir, data_raw_dir

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

TZ = ZoneInfo("Asia/Shanghai")
COMPETITION_CODE = "CSL"
COMPETITION_NAME = "Chinese Super League"
MODEL_NAME = "Zero-Inflated Poisson with Dixon-Coles Time Decay"
MODEL_VERSION = "v1"

META_COLUMNS = [
    "competition_code",
    "competition_name",
    "season",
    "updated_at",
    "timezone",
    "last_completed_match_date",
    "next_fixture_date",
    "matches_played",
    "current_round",
    "total_rounds",
    "model_name",
    "model_version",
]

UPCOMING_COLUMNS = [
    "fixture_id",
    "round",
    "match_date",
    "match_time",
    "kickoff_at",
    "home_team",
    "away_team",
]

PREDICTION_COLUMNS = [
    "fixture_id",
    "round",
    "match_date",
    "kickoff_at",
    "home_team",
    "away_team",
    "home_win_prob",
    "draw_prob",
    "away_win_prob",
    "home_win_fair_odds",
    "draw_fair_odds",
    "away_win_fair_odds",
]

STRENGTH_COLUMNS = [
    "rank_overall",
    "team",
    "attack_rating",
    "defense_rating",
    "overall_rating",
    "attack_rank",
    "defense_rank",
    "form",
]


@dataclass(frozen=True)
class ExportPaths:
    matches_csv: str = os.path.join(data_raw_dir(), "CHN_Super League.csv")
    fresh_schedule_csv: str = os.path.join(data_raw_dir(), "chinese_super_league_data.csv")
    fixtures_csv: str = os.path.join(data_raw_dir(), "chn_upcoming_fixtures.csv")
    team_stats_csv: str = os.path.join(data_output_dir(), "CHN_team_stats.csv")
    simulations_csv: str = os.path.join(data_output_dir(), "CHN_team_stats_match_simulations.csv")
    out_dir: str = data_dashboard_csv_dir()

    @property
    def meta_csv(self) -> str:
        return os.path.join(self.out_dir, "dashboard_meta.csv")

    @property
    def upcoming_csv(self) -> str:
        return os.path.join(self.out_dir, "upcoming_fixtures.csv")

    @property
    def predictions_csv(self) -> str:
        return os.path.join(self.out_dir, "match_predictions.csv")

    @property
    def strength_csv(self) -> str:
        return os.path.join(self.out_dir, "team_strength_rankings.csv")


def _require_columns(df: pd.DataFrame, required: Iterable[str], label: str) -> None:
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"{label} missing required columns: {missing}")


def _slugify(value: str) -> str:
    slug = value.strip().lower().replace(" ", "-")
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    slug = re.sub(r"-{2,}", "-", slug)
    return slug.strip("-")


def _fair_odds(probability: float) -> float | None:
    if probability <= 0 or math.isnan(probability):
        return None
    return round(1.0 / probability, 4)


def _normalize_probabilities(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    cols = ["home_win_prob", "draw_prob", "away_win_prob"]
    total = out[cols].sum(axis=1)
    bad_total = total <= 0
    if bad_total.any():
        bad_rows = out.loc[bad_total, ["home_team", "away_team"]].to_dict("records")
        raise ValueError(f"Found rows with non-positive probability totals: {bad_rows}")

    for col in cols:
        out[col] = (out[col] / total).round(6)

    rounded_total = out[cols].sum(axis=1)
    adjust_idx = out.index[(rounded_total - 1.0).abs() > 1e-6]
    if len(adjust_idx):
        out.loc[adjust_idx, "away_win_prob"] = (
            1.0 - out.loc[adjust_idx, "home_win_prob"] - out.loc[adjust_idx, "draw_prob"]
        ).round(6)
    return out


def _parse_match_dates(series: pd.Series) -> pd.Series:
    return parse_date_only_series(series)


def _parse_fixture_dates(series: pd.Series) -> pd.Series:
    return parse_date_only_series(series)


def _normalize_season_value(value: object) -> str:
    if pd.isna(value):
        raise ValueError("Season value is missing")
    if isinstance(value, str):
        text = value.strip()
        return text[:-2] if text.endswith(".0") else text
    if isinstance(value, (int,)):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(value)
    return str(value).strip()


def _extract_round_number(series: pd.Series) -> pd.Series:
    extracted = series.astype(str).str.extract(r"(\d+)\s*$", expand=False)
    return pd.to_numeric(extracted, errors="coerce").astype("Int64")


def _derive_current_season(matches: pd.DataFrame) -> str:
    played = matches.copy()
    played["parsed_date"] = _parse_match_dates(played["Date"])
    played = played[played["parsed_date"].notna()]
    if played.empty:
        raise ValueError("Cannot derive season from matches: no parseable dates found")
    latest_row = played.sort_values("parsed_date").iloc[-1]
    return _normalize_season_value(latest_row["Season"])


def build_round_progress(schedule_path: str, season: str) -> dict[str, int]:
    schedule = pd.read_csv(schedule_path)
    _require_columns(schedule, ["Season", "Round", "Res"], "chinese_super_league_data.csv")

    season_schedule = schedule.copy()
    season_schedule["Season"] = season_schedule["Season"].astype(str).str.strip()
    season_schedule = season_schedule[season_schedule["Season"] == season].copy()
    if season_schedule.empty:
        raise ValueError(f"No schedule rows found for season {season} in chinese_super_league_data.csv")

    season_schedule["round_num"] = _extract_round_number(season_schedule["Round"])
    season_schedule["Res"] = season_schedule["Res"].astype(str).str.strip()
    season_schedule = season_schedule[season_schedule["round_num"].notna()].copy()
    if season_schedule.empty:
        raise ValueError("No parseable round numbers found in chinese_super_league_data.csv")

    played_mask = season_schedule["Res"].isin(["H", "D", "A"])
    matches_played = int(played_mask.sum())
    total_rounds = int(season_schedule["round_num"].max())

    unplayed_rounds = sorted(
        season_schedule.loc[~played_mask, "round_num"].dropna().astype(int).unique().tolist()
    )
    current_round = unplayed_rounds[0] if unplayed_rounds else total_rounds

    return {
        "matches_played": matches_played,
        "current_round": int(current_round),
        "total_rounds": total_rounds,
    }


def build_upcoming_fixtures(fixtures_path: str, season: str, export_now: pd.Timestamp) -> pd.DataFrame:
    src = pd.read_csv(fixtures_path)
    _require_columns(src, ["Wk", "Date", "Time", "Home", "Away"], "chn_upcoming_fixtures.csv")

    out = src.rename(
        columns={
            "Wk": "round",
            "Date": "match_date",
            "Time": "match_time",
            "Home": "home_team",
            "Away": "away_team",
        }
    ).copy()

    out["round"] = pd.to_numeric(out["round"], errors="coerce").astype("Int64")
    out["match_date_dt"] = _parse_fixture_dates(out["match_date"])
    export_date = export_now.tz_convert(TZ).normalize().tz_localize(None)
    out = out[out["match_date_dt"].notna()].copy()
    out = out[out["match_date_dt"] >= export_date].copy()

    # Off-season short-circuit: with no rows, `out.apply(..., axis=1)` below
    # returns an empty DataFrame instead of a Series, which then fails to
    # assign back into `out["fixture_id"]`. Return the expected schema
    # directly so downstream consumers see a well-formed empty DataFrame.
    if out.empty:
        return pd.DataFrame(columns=UPCOMING_COLUMNS)

    out["match_date"] = format_date_only_series(out["match_date_dt"])
    out["match_time"] = out["match_time"].astype(str).str.strip().str.slice(0, 5)
    kickoff = pd.to_datetime(
        out["match_date"] + " " + out["match_time"],
        format="%Y-%m-%d %H:%M",
        errors="coerce",
    )
    out["kickoff_at"] = kickoff.dt.tz_localize(TZ).dt.strftime("%Y-%m-%dT%H:%M:%S%z")
    out["kickoff_at"] = out["kickoff_at"].str.replace(r"([+-]\d{2})(\d{2})$", r"\1:\2", regex=True)
    out["fixture_id"] = out.apply(
        lambda row: (
            f"{COMPETITION_CODE}-{season}-{int(row['round'])}-{row['match_date']}"
            f"-{_slugify(row['home_team'])}-{_slugify(row['away_team'])}"
        ),
        axis=1,
    )

    out = out[UPCOMING_COLUMNS].sort_values(["match_date", "match_time", "home_team", "away_team"]).reset_index(drop=True)
    return out


def build_match_predictions(simulations_path: str, upcoming: pd.DataFrame) -> pd.DataFrame:
    sims = pd.read_csv(simulations_path)
    _require_columns(
        sims,
        ["Home Team", "Away Team", "Home Win Probability", "Draw Probability", "Away Win Probability"],
        "CHN_team_stats_match_simulations.csv",
    )

    sims = sims.rename(
        columns={
            "Home Team": "home_team",
            "Away Team": "away_team",
            "Home Win Probability": "home_win_prob",
            "Draw Probability": "draw_prob",
            "Away Win Probability": "away_win_prob",
        }
    ).copy()

    sims = sims[["home_team", "away_team", "home_win_prob", "draw_prob", "away_win_prob"]]
    sims["home_team"] = sims["home_team"].astype(str).str.strip()
    sims["away_team"] = sims["away_team"].astype(str).str.strip()
    dupes = sims.duplicated(subset=["home_team", "away_team"], keep=False)
    if dupes.any():
        duplicated_pairs = sims.loc[dupes, ["home_team", "away_team"]].drop_duplicates().to_dict("records")
        raise ValueError(f"Simulation table has duplicate home/away pairs: {duplicated_pairs}")

    merged = upcoming.merge(sims, on=["home_team", "away_team"], how="left", validate="one_to_one")
    if merged[["home_win_prob", "draw_prob", "away_win_prob"]].isna().any(axis=1).any():
        missing = merged.loc[
            merged[["home_win_prob", "draw_prob", "away_win_prob"]].isna().any(axis=1),
            ["fixture_id", "home_team", "away_team"],
        ].to_dict("records")
        raise ValueError(f"Missing simulation probabilities for fixtures: {missing}")

    merged[["home_win_prob", "draw_prob", "away_win_prob"]] = merged[
        ["home_win_prob", "draw_prob", "away_win_prob"]
    ].apply(pd.to_numeric, errors="coerce")
    out = _normalize_probabilities(merged)

    out["home_win_fair_odds"] = out["home_win_prob"].map(_fair_odds)
    out["draw_fair_odds"] = out["draw_prob"].map(_fair_odds)
    out["away_win_fair_odds"] = out["away_win_prob"].map(_fair_odds)
    out = out[PREDICTION_COLUMNS].copy()
    return out


def _form_token(result: str, is_home: bool) -> str | None:
    mapping = {
        ("H", True): "W",
        ("D", True): "D",
        ("A", True): "L",
        ("H", False): "L",
        ("D", False): "D",
        ("A", False): "W",
    }
    return mapping.get((result, is_home))


def _build_team_form_map(matches: pd.DataFrame) -> dict[str, str]:
    _require_columns(matches, ["Date", "Home", "Away", "Res"], "CHN_Super League.csv")
    played = matches.copy()
    played["parsed_date"] = _parse_match_dates(played["Date"])
    played["Res"] = played["Res"].astype(str).str.strip()
    played = played[played["parsed_date"].notna() & played["Res"].isin(["H", "D", "A"])].copy()
    played = played.sort_values(["parsed_date", "Time"], na_position="last")

    team_results: dict[str, list[str]] = {}
    for _, row in played.iterrows():
        home_team = str(row["Home"]).strip()
        away_team = str(row["Away"]).strip()
        result = str(row["Res"]).strip()

        home_token = _form_token(result, True)
        away_token = _form_token(result, False)
        if home_token is not None:
            team_results.setdefault(home_team, []).append(home_token)
        if away_token is not None:
            team_results.setdefault(away_team, []).append(away_token)

    return {team: ",".join(results[-5:][::-1]) for team, results in team_results.items()}


def build_team_strength_rankings(team_stats_path: str, matches_path: str) -> pd.DataFrame:
    stats = pd.read_csv(team_stats_path)
    _require_columns(stats, ["Team", "Attack", "Defense"], "CHN_team_stats.csv")
    matches = pd.read_csv(matches_path)
    form_map = _build_team_form_map(matches)

    out = stats.rename(
        columns={
            "Team": "team",
            "Attack": "attack_rating",
            "Defense": "defense_rating",
        }
    ).copy()

    out["attack_rating"] = pd.to_numeric(out["attack_rating"], errors="coerce")
    out["defense_rating"] = pd.to_numeric(out["defense_rating"], errors="coerce")
    out["overall_rating"] = out["attack_rating"] - out["defense_rating"]
    out["attack_rank"] = out["attack_rating"].rank(method="min", ascending=False).astype(int)
    out["defense_rank"] = out["defense_rating"].rank(method="min", ascending=True).astype(int)
    out = out.sort_values(["overall_rating", "team"], ascending=[False, True]).reset_index(drop=True)
    out["rank_overall"] = out.index + 1
    out["form"] = out["team"].map(form_map).fillna("")
    out = out[STRENGTH_COLUMNS].copy()
    return out


def build_dashboard_meta(
    matches: pd.DataFrame,
    upcoming: pd.DataFrame,
    season: str,
    export_now: pd.Timestamp,
    round_progress: dict[str, int],
) -> pd.DataFrame:
    played = matches.copy()
    played["parsed_date"] = _parse_match_dates(played["Date"])
    played["Res"] = played["Res"].astype(str).str.strip()
    played = played[played["parsed_date"].notna() & played["Res"].isin(["H", "D", "A"])].copy()
    if played.empty:
        raise ValueError("No completed matches found for dashboard_meta.csv")

    # Off-season tolerance: when there are no upcoming fixtures in the next 14 days
    # (e.g. between rounds, mid-season break, end of season), the meta is still
    # valuable — strength rankings and last-completed match info are fresh. Emit
    # the meta with next_fixture_date left blank rather than failing Step 5 and
    # leaving the entire dashboard frozen at the previous run's snapshot.
    next_fixture_date = upcoming["match_date"].min() if not upcoming.empty else None

    meta = pd.DataFrame(
        [
            {
                "competition_code": COMPETITION_CODE,
                "competition_name": COMPETITION_NAME,
                "season": season,
                "updated_at": export_now.tz_convert(TZ).isoformat(timespec="seconds"),
                "timezone": "Asia/Shanghai",
                "last_completed_match_date": played["parsed_date"].max().strftime("%Y-%m-%d"),
                "next_fixture_date": next_fixture_date,
                "matches_played": round_progress["matches_played"],
                "current_round": round_progress["current_round"],
                "total_rounds": round_progress["total_rounds"],
                "model_name": MODEL_NAME,
                "model_version": MODEL_VERSION,
            }
        ],
        columns=META_COLUMNS,
    )
    return meta


def validate_outputs(meta: pd.DataFrame, upcoming: pd.DataFrame, predictions: pd.DataFrame, strength: pd.DataFrame, export_now: pd.Timestamp) -> None:
    if len(meta) != 1:
        raise ValueError("dashboard_meta.csv must contain exactly one row")

    export_date = export_now.tz_convert(TZ).strftime("%Y-%m-%d")
    if not upcoming["fixture_id"].is_unique:
        raise ValueError("upcoming_fixtures.csv fixture_id values must be unique")
    if (upcoming["match_date"] < export_date).any():
        bad = upcoming.loc[upcoming["match_date"] < export_date, ["fixture_id", "match_date"]].to_dict("records")
        raise ValueError(f"upcoming_fixtures.csv contains past matches: {bad}")

    if not predictions["fixture_id"].isin(set(upcoming["fixture_id"])).all():
        raise ValueError("match_predictions.csv contains fixture_id values not found in upcoming_fixtures.csv")

    probs = predictions[["home_win_prob", "draw_prob", "away_win_prob"]]
    if ((probs < 0) | (probs > 1)).any().any():
        raise ValueError("match_predictions.csv contains probabilities outside [0, 1]")
    if not ((probs.sum(axis=1) - 1.0).abs() <= 1e-6).all():
        raise ValueError("match_predictions.csv probability totals are not within tolerance of 1")

    if not strength["team"].is_unique:
        raise ValueError("team_strength_rankings.csv team values must be unique")
    expected_overall = (strength["attack_rating"] - strength["defense_rating"]).round(10)
    if not expected_overall.equals(strength["overall_rating"].round(10)):
        raise ValueError("team_strength_rankings.csv overall_rating does not equal attack_rating - defense_rating")


def write_csv(df: pd.DataFrame, path: str) -> None:
    df.to_csv(path, index=False)
    log.info("Wrote %s (%d rows)", path, len(df))


def run() -> None:
    paths = ExportPaths()
    os.makedirs(paths.out_dir, exist_ok=True)

    export_now = pd.Timestamp.now(tz=TZ)
    matches = pd.read_csv(paths.matches_csv)
    season = _derive_current_season(matches)
    log.info("Exporting dashboard CSV for season %s", season)

    upcoming = build_upcoming_fixtures(paths.fixtures_csv, season, export_now)
    predictions = build_match_predictions(paths.simulations_csv, upcoming)
    strength = build_team_strength_rankings(paths.team_stats_csv, paths.matches_csv)
    round_progress = build_round_progress(paths.fresh_schedule_csv, season)
    meta = build_dashboard_meta(matches, upcoming, season, export_now, round_progress)

    validate_outputs(meta, upcoming, predictions, strength, export_now)

    write_csv(meta, paths.meta_csv)
    write_csv(upcoming, paths.upcoming_csv)
    write_csv(predictions, paths.predictions_csv)
    write_csv(strength, paths.strength_csv)


def main() -> None:
    try:
        run()
    except Exception as exc:  # pragma: no cover - top-level script guard
        log.error("%s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
