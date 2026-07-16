"""
Fetch Chinese Super League Pinnacle 1X2 (moneyline) odds from The Odds API.

Roadmap #10: the Asian-handicap route was falsified in backtest (winner's curse,
backtest.md §9), so this fetch requests the ``h2h`` market — home/draw/away prices
— instead of ``spreads``. The stored ``market`` label is "moneyline". Module and
output filenames keep their historical "spreads" names so workflows and downstream
paths stay stable.

This fetch is restricted to pre-match upcoming fixtures only. Live matches are
excluded by requesting odds for the league sport key and applying
`commenceTimeFrom` at the current UTC timestamp.

Usage (仓库根目录，PYTHONPATH=src):
    export THE_ODDS_API_KEY=...
    python -m csl.odds.fetch_pinnacle_spreads

Default output:
    data/raw_data/CHN_pinnacle_spreads.csv
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import requests

from csl.paths import data_output_dir, data_raw_dir

THE_ODDS_API_BASE_URL = "https://api.the-odds-api.com/v4"
ODDS_SPORT_KEY = "soccer_china_superleague"
BOOKMAKER = "pinnacle"
# The Odds API market key for 1X2 prices; stored rows use MARKET_LABEL instead
# so the history CSV reads naturally ("moneyline") regardless of API naming.
MARKET = "h2h"
MARKET_LABEL = "moneyline"
DEFAULT_REGIONS = "us"
API_KEY_ENV = "THE_ODDS_API_KEY"

DEFAULT_OUTPUT_CSV = os.path.join(data_raw_dir(), "CHN_pinnacle_spreads.csv")
TEAM_MAPPING_CSV = os.path.join(data_output_dir(), "CHN_team_name_mapping.csv")

OUTPUT_COLUMNS = [
    "event_id",
    "commence_time",
    "api_home_team",
    "api_away_team",
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
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


@dataclass(frozen=True)
class TeamMapping:
    odds_to_standard: dict[str, str]
    standard_to_standard: dict[str, str]
    match_to_standard: dict[str, str]


def _clean_name(value: Any) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _build_mapping_column(df: pd.DataFrame, source_col: str, target_col: str) -> dict[str, str]:
    if source_col not in df.columns or target_col not in df.columns:
        raise ValueError(f"Mapping file missing required columns: {source_col}, {target_col}")

    sub = df[[source_col, target_col]].copy()
    sub[source_col] = sub[source_col].map(_clean_name)
    sub[target_col] = sub[target_col].map(_clean_name)
    sub = sub.dropna(subset=[source_col, target_col])

    dupes = sub[source_col].duplicated(keep=False)
    if dupes.any():
        names = sorted(sub.loc[dupes, source_col].unique().tolist())
        log.warning("Duplicate %s values in mapping file; using last row: %s", source_col, names)

    sub = sub.drop_duplicates(subset=[source_col], keep="last")
    return dict(zip(sub[source_col], sub[target_col]))


def load_team_mapping(path: str = TEAM_MAPPING_CSV) -> TeamMapping:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Team mapping file not found: {path}")

    df = pd.read_csv(path)
    for col in ("odds_team", "standard_team", "match_team"):
        if col not in df.columns:
            raise ValueError(f"Mapping file missing required column: {col}")

    mapping = TeamMapping(
        odds_to_standard=_build_mapping_column(df, "odds_team", "standard_team"),
        standard_to_standard=_build_mapping_column(df, "standard_team", "standard_team"),
        match_to_standard=_build_mapping_column(df, "match_team", "standard_team"),
    )
    log.info("Loaded team mapping from %s", path)
    return mapping


def normalize_team_name(api_name: str, mapping: TeamMapping) -> str | None:
    name = _clean_name(api_name)
    if not name:
        return None
    if name in mapping.odds_to_standard:
        return mapping.odds_to_standard[name]
    if name in mapping.standard_to_standard:
        return mapping.standard_to_standard[name]
    if name in mapping.match_to_standard:
        return mapping.match_to_standard[name]
    return None


def get_api_key() -> str:
    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        raise RuntimeError(f"Missing required environment variable: {API_KEY_ENV}")
    return api_key


def fetch_odds_response(api_key: str, regions: str) -> requests.Response:
    """Request pre-match Pinnacle 1X2 odds and return the raw HTTP response.

    Kept separate from ``fetch_odds_payload`` so callers that need the quota
    headers (``x-requests-remaining`` etc.) can read them off the response.
    """
    url = f"{THE_ODDS_API_BASE_URL}/sports/{ODDS_SPORT_KEY}/odds"
    commence_time_from = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    params = {
        "apiKey": api_key,
        "regions": regions,
        "markets": MARKET,
        "oddsFormat": "decimal",
        "bookmakers": BOOKMAKER,
        "commenceTimeFrom": commence_time_from,
    }
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    log.info("Requested %s odds with commenceTimeFrom=%s", ODDS_SPORT_KEY, commence_time_from)
    return response


def fetch_odds_payload(api_key: str, regions: str) -> list[dict[str, Any]]:
    response = fetch_odds_response(api_key, regions)
    data = response.json()
    if not isinstance(data, list):
        raise ValueError(f"Expected list response from The Odds API, got: {type(data)}")
    return data


def _find_bookmaker(event: dict[str, Any]) -> dict[str, Any] | None:
    bookmakers = event.get("bookmakers")
    if not isinstance(bookmakers, list):
        return None
    for bookmaker in bookmakers:
        if isinstance(bookmaker, dict) and bookmaker.get("key") == BOOKMAKER:
            return bookmaker
    return None


def _find_market(bookmaker: dict[str, Any]) -> dict[str, Any] | None:
    markets = bookmaker.get("markets")
    if not isinstance(markets, list):
        return None
    for market in markets:
        if isinstance(market, dict) and market.get("key") == MARKET:
            return market
    return None


def _coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_rows(
    events: list[dict[str, Any]],
    mapping: TeamMapping,
    *,
    regions: str,
    fetched_at: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    unmapped_names: set[str] = set()

    for event in events:
        if not isinstance(event, dict):
            log.warning("Skipping malformed event payload: %r", event)
            continue

        api_home_team = _clean_name(event.get("home_team"))
        api_away_team = _clean_name(event.get("away_team"))
        if not api_home_team or not api_away_team:
            log.warning("Skipping event with missing home/away team: %r", event.get("id"))
            continue

        home_team = normalize_team_name(api_home_team, mapping)
        away_team = normalize_team_name(api_away_team, mapping)
        if home_team is None:
            unmapped_names.add(api_home_team)
        if away_team is None:
            unmapped_names.add(api_away_team)
        if home_team is None or away_team is None:
            continue

        bookmaker = _find_bookmaker(event)
        if bookmaker is None:
            log.warning("Skipping event %s: bookmaker %r not found", event.get("id"), BOOKMAKER)
            continue

        market = _find_market(bookmaker)
        if market is None:
            log.warning("Skipping event %s: market %r not found", event.get("id"), MARKET)
            continue

        outcomes = market.get("outcomes")
        if not isinstance(outcomes, list):
            log.warning("Skipping event %s: outcomes missing or malformed", event.get("id"))
            continue

        home_outcome = None
        draw_outcome = None
        away_outcome = None
        for outcome in outcomes:
            if not isinstance(outcome, dict):
                continue
            name = _clean_name(outcome.get("name"))
            if name == api_home_team:
                home_outcome = outcome
            elif name == api_away_team:
                away_outcome = outcome
            elif name and name.casefold() == "draw":
                draw_outcome = outcome

        if home_outcome is None or draw_outcome is None or away_outcome is None:
            log.warning("Skipping event %s: missing home/draw/away outcomes in h2h market", event.get("id"))
            continue

        home_odds = _coerce_float(home_outcome.get("price"))
        draw_odds = _coerce_float(draw_outcome.get("price"))
        away_odds = _coerce_float(away_outcome.get("price"))
        if home_odds is None or draw_odds is None or away_odds is None:
            log.warning("Skipping event %s: incomplete h2h price fields", event.get("id"))
            continue

        rows.append(
            {
                "event_id": event.get("id"),
                "commence_time": event.get("commence_time"),
                "api_home_team": api_home_team,
                "api_away_team": api_away_team,
                "home_team": home_team,
                "away_team": away_team,
                "home_odds": home_odds,
                "draw_odds": draw_odds,
                "away_odds": away_odds,
                "bookmaker": bookmaker.get("key", BOOKMAKER),
                "market": MARKET_LABEL,
                "regions": regions,
                "last_update": market.get("last_update") or bookmaker.get("last_update"),
                "fetched_at": fetched_at,
            }
        )

    if unmapped_names:
        names = ", ".join(sorted(unmapped_names))
        raise ValueError(
            "Unmapped The Odds API team names found in response. "
            f"Please populate odds_team or existing standard/match mappings first: {names}"
        )

    return rows


def rows_to_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS)


def run(*, out_path: str, regions: str) -> pd.DataFrame:
    api_key = get_api_key()
    mapping = load_team_mapping()
    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    events = fetch_odds_payload(api_key, regions)
    log.info("Fetched %d events from The Odds API", len(events))
    rows = extract_rows(events, mapping, regions=regions, fetched_at=fetched_at)
    frame = rows_to_frame(rows)

    out_dir = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(out_dir, exist_ok=True)
    frame.to_csv(out_path, index=False, encoding="utf-8")
    log.info("Wrote %s (%d rows)", out_path, len(frame))
    if frame.empty:
        log.info("API fetch succeeded but returned zero valid Pinnacle 1X2 rows.")
    return frame


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch CSL Pinnacle 1X2 (moneyline) odds from The Odds API and export CSV"
    )
    parser.add_argument(
        "--out",
        default=DEFAULT_OUTPUT_CSV,
        help="Output CSV path",
    )
    parser.add_argument(
        "--regions",
        default=DEFAULT_REGIONS,
        help="Regions parameter for The Odds API (default: us)",
    )
    args = parser.parse_args()

    try:
        run(out_path=args.out, regions=args.regions)
    except requests.HTTPError as exc:
        log.error("The Odds API HTTP error: %s", exc)
        sys.exit(1)
    except requests.RequestException as exc:
        log.error("The Odds API request failed: %s", exc)
        sys.exit(1)
    except Exception as exc:  # pragma: no cover - top-level CLI guard
        log.error("%s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
