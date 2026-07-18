"""Push a Telegram alert the moment a NEW 1xBet-open bet signal appears (P0-2).

Closes the terminal-side gap in the execution chain: a signal used to reach the user
only when they happened to open the dashboard, so "signal on site -> human sees it"
had no upper bound. This module runs right after the market-comparison export (inside
``scripts/csl.sh`` publish / republish / all — every path that regenerates signals)
and pushes each newly-fired ``signal_state == "bet"`` fixture to a Telegram chat, so
the full bet instruction lands on the user's lock screen without a page load.

Dedup baseline = the *previously committed* comparison CSV. Each workflow commits
``CHN_upcoming_market_comparison.csv`` every run, so ``git show HEAD:<csv>`` is the last
published signal set; a fixture+pick that was already a "bet" there is NOT re-notified.
A price that merely moved on an already-notified pick is likewise not re-sent (dedup is
keyed on ``(fixture_id, signal_pick)``, not odds) — that's what the terminal's
bottom-line-odds guard is for at execution time.

Fail-open by design: a missing token, an unreachable Telegram, or an unreadable
baseline logs and returns without raising, so the notifier can never fail a publish.
When the baseline CSV is unavailable (first-ever run) nothing is sent, to avoid a
one-off blast of every currently-firing signal.

Env:
    TELEGRAM_BOT_TOKEN   bot token from @BotFather
    TELEGRAM_CHAT_ID     numeric chat id (see the setup notes)

Usage (repo root, PYTHONPATH=src):
    python -m csl.notify.signal_alert
    python -m csl.notify.signal_alert --dry-run   # print what would be sent, send nothing
"""

from __future__ import annotations

import argparse
import csv
import io
import logging
import os
import subprocess
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from csl.paths import data_output_dir

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)

DEFAULT_COMPARISON_CSV = os.path.join(data_output_dir(), "CHN_upcoming_market_comparison.csv")
ONEXBET_URL = "https://1xbet.com/en/line/football"
DISPLAY_TZ = ZoneInfo("Europe/London")

TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
CHAT_ENV = "TELEGRAM_CHAT_ID"

# Dedup identity of a fired signal.
SIGNAL_KEY = ("fixture_id", "signal_pick")


def _bet_rows(rows: list[dict]) -> dict[tuple[str, str], dict]:
    """Map (fixture_id, signal_pick) -> row for every ``signal_state == "bet"`` row."""
    out: dict[tuple[str, str], dict] = {}
    for row in rows:
        if (row.get("signal_state") or "").strip() != "bet":
            continue
        pick = (row.get("signal_pick") or "").strip()
        if pick not in ("home", "draw", "away"):
            continue
        out[(str(row.get("fixture_id", "")), pick)] = row
    return out


def _read_csv_rows(path: str) -> list[dict]:
    if not os.path.isfile(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _previous_committed_rows(path: str) -> list[dict] | None:
    """Rows of the last-committed version of ``path`` via ``git show HEAD:<relpath>``.

    Returns None when git or the committed blob is unavailable (e.g. the first run
    that introduces the file), which the caller treats as "no baseline -> send nothing".
    """
    try:
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        rel = os.path.relpath(os.path.abspath(path), root)
        blob = subprocess.run(
            ["git", "show", f"HEAD:{rel}"],
            capture_output=True, text=True, check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
        log.warning("No committed baseline for %s (%s); sending nothing this run.", path, exc)
        return None
    return list(csv.DictReader(io.StringIO(blob)))


def _fmt_kickoff(kickoff_at: str, match_time: str) -> str:
    if kickoff_at:
        try:
            dt = datetime.fromisoformat(kickoff_at.replace("Z", "+00:00"))
            return dt.astimezone(DISPLAY_TZ).strftime("%a %d %b %H:%M") + " (London)"
        except ValueError:
            pass
    return match_time or "TBD"


def _pick_cn(row: dict) -> str:
    pick = (row.get("signal_pick") or "").strip()
    if pick == "home":
        return f"主胜 {row.get('home_team', '')}".strip()
    if pick == "away":
        return f"客胜 {row.get('away_team', '')}".strip()
    return "平局 Draw"


def _f(value, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _esc(text) -> str:
    s = "" if text is None else str(text)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_message(row: dict) -> str:
    """One-glance bet instruction: match, side, price, EV, bottom-line odds, kickoff."""
    pick = (row.get("signal_pick") or "").strip()
    odds = _f(row.get(f"onexbet_open_{pick}_odds"))
    evv = _f(row.get(f"onexbet_open_{pick}_ev"))
    prob = _f(row.get({"home": "home_win_prob", "draw": "draw_prob", "away": "away_win_prob"}[pick]))
    bottom = (1.0 / prob) if prob and prob > 0 else None

    match = f"{row.get('home_team', '')} vs {row.get('away_team', '')}".strip()
    kickoff = _fmt_kickoff(row.get("kickoff_at", ""), row.get("match_time", ""))

    lines = [
        "🟢 <b>BET 信号</b>",
        f"<b>{_esc(match)}</b>",
        f"方向: <b>{_esc(_pick_cn(row))}</b>",
        f"1xBet 开盘价: <b>{odds:.2f}</b>" if odds is not None else "1xBet 开盘价: --",
        f"EV: <b>{evv:+.3f}</b>" if evv is not None else "EV: --",
        f"底线赔率 (≥ 才下注): <b>{bottom:.2f}</b>" if bottom is not None else "底线赔率: --",
        f"开赛: {_esc(kickoff)}",
        f'下注: <a href="{ONEXBET_URL}">1xBet 足球</a>',
    ]
    return "\n".join(lines)


def send_telegram(token: str, chat_id: str, text: str, *, timeout: int = 15) -> bool:
    """POST one message; return True on success, False (logged) on any failure."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.error("Telegram send failed: %s", exc)
        return False
    return True


def new_signals(current_rows: list[dict], previous_rows: list[dict]) -> list[dict]:
    """Bet rows in ``current`` whose (fixture_id, pick) was not a bet in ``previous``."""
    prev = _bet_rows(previous_rows)
    return [row for key, row in _bet_rows(current_rows).items() if key not in prev]


def run(*, comparison_csv: str = DEFAULT_COMPARISON_CSV, dry_run: bool = False) -> int:
    """Send Telegram alerts for newly-fired bet signals. Returns the number sent."""
    current = _read_csv_rows(comparison_csv)
    if not current:
        log.info("No comparison rows at %s; nothing to alert.", comparison_csv)
        return 0

    previous = _previous_committed_rows(comparison_csv)
    if previous is None:
        return 0  # no baseline -> stay silent rather than blast every open signal

    fresh = new_signals(current, previous)
    if not fresh:
        log.info("No new bet signals since the last published comparison.")
        return 0

    log.info("New bet signal(s): %d", len(fresh))
    if dry_run:
        for row in fresh:
            log.info("Would send:\n%s", format_message(row))
        return 0

    token = os.environ.get(TOKEN_ENV, "").strip()
    chat_id = os.environ.get(CHAT_ENV, "").strip()
    if not token or not chat_id:
        log.warning("%s / %s not set; %d new signal(s) not sent.", TOKEN_ENV, CHAT_ENV, len(fresh))
        return 0

    sent = 0
    for row in fresh:
        if send_telegram(token, chat_id, format_message(row)):
            sent += 1
    log.info("Sent %d/%d Telegram signal alert(s).", sent, len(fresh))
    return sent


def main() -> None:
    parser = argparse.ArgumentParser(description="Telegram alerts for newly-fired 1xBet bet signals.")
    parser.add_argument("--comparison", default=DEFAULT_COMPARISON_CSV,
                        help="Full market-comparison CSV (with signal_state/signal_pick).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be sent; send nothing.")
    args = parser.parse_args()

    # Fail-open: a notifier must never fail a publish. Log and exit 0 on any error.
    try:
        run(comparison_csv=args.comparison, dry_run=args.dry_run)
    except Exception as exc:  # noqa: BLE001 - top-level guard, must not break the pipeline
        log.error("signal_alert failed (ignored): %s", exc)
    sys.exit(0)


if __name__ == "__main__":
    main()
