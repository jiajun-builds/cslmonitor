"""Backtest: bet the model's EV on 1xBet OPENING 1X2, grade CLV vs Pinnacle CLOSE.

Roadmap #8 thesis test. `backtest_1x2.py` bets and grades entirely on Pinnacle
(open price, open->close CLV) and finds the model's edge is real but eaten by
Pinnacle's ~7.55% opening vig (§11.7 / §12). 1xBet's opening 1X2 is much cheaper
(~5% overround), so the same edge might clear the p×R bar there. This script tests
exactly that on the fixtures the user hand-backfilled 1xBet opening + closing lines
for (2024 + 2025 + 2026 — three full seasons; the §11.1 single-season caveat that hung
over the first 2026-only cut is fully discharged — the gap clears the vig wall in all
three independently at thr>0.20. See §13.1 and the per-season split below).

Design:
  * bet price O   = 1xBet opening 1X2 (onexbet_open_h/d/a)
  * CLV reference = Pinnacle CLOSING no-vig probs (pinnacle_close_h/d/a) — the sharp
    fair-value proxy our 1xBet-open bet is measured against.
  * CLV(pp)  = novig(pinnacle_close)[pick] − novig(1xbet_open)[pick]
  * bar(pp)  = novig(1xbet_open)[pick] × R, R = 1xBet's overround (its OWN vig wall,
    ~1.75pp at 5% vs Pinnacle's 2.61pp at 7.55% — the whole point of a cheaper book).
  * exCLV    = CLV − the §11.3 model-free baseline drift for that (season, outcome),
    on the same 1xbet-open->pinnacle-close basis (absorbs any systematic 1xBet-vs-
    Pinnacle pricing offset so exCLV isolates the model).

Two strategies compared (the user's ask):
  * WITH draw  — pick = argmax EV over {home, draw, away}
  * NO draw    — pick = argmax EV over {home, away} only (draw never backed)

Three model variants: raw NegBinom, δ-calibrated (market-free, production), and
λ=0.75 market-anchored on the 1xBet opening no-vig draw (no leakage — the open is
known at bet time). The de-bias is validated in backtest.md §12.

Reproduce (repo root): PYTHONPATH=src python backtest/backtest_1xbet.py
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import penaltyblog as pb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_1x2 import (  # noqa: E402  reuse the validated harness
    MIN_TRAIN,
    PROD_LOOKBACK_MONTHS,
    PROD_XI,
    _t,
    fit_draw_delta,
    fit_model,
    one_x_two,
)
from csl.date_utils import parse_date_only_series  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(REPO_ROOT, "data", "raw_data", "CHN_Super League.csv")

OPEN_COLS = ["onexbet_open_h", "onexbet_open_d", "onexbet_open_a"]   # bet price
CLOSE_COLS = ["pinnacle_close_h", "pinnacle_close_d", "pinnacle_close_a"]  # CLV ref
res_map = {"H": 0, "D": 1, "A": 2}
OUTCOME = ["home", "draw", "away"]
EV_THRESHOLDS = [0.00, 0.10, 0.20]

# (report label, de-bias mode). mode: 0.0 raw; float=market-anchored lam; "delta".
VARIANTS = [
    ("NegBinom raw", 0.00),
    ("NegBinom + delta-cal (market-free, prod)", "delta"),
    ("NegBinom + lam=0.75 (anchored on 1xBet open)", 0.75),
]


def load() -> pd.DataFrame:
    df = pd.read_csv(CSV)
    df["Date"] = parse_date_only_series(df["Date"])
    for c in ["HExpG+", "AExpG+", "HG", "AG", *OPEN_COLS, *CLOSE_COLS]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["Date", "Home", "Away"])
    df["Home"] = df["Home"].astype(str)
    df["Away"] = df["Away"].astype(str)
    df["res"] = df["Res"].map(res_map)
    return df.sort_values("Date").reset_index(drop=True)


def walk_forward(df: pd.DataFrame) -> pd.DataFrame:
    """NegBinom walk-forward over fixtures that carry 1xBet open + Pinnacle close."""
    graded = df[df["res"].notna()
                & df[OPEN_COLS].notna().all(axis=1)
                & df[CLOSE_COLS].notna().all(axis=1)].copy()
    recs = []
    for date in sorted(graded["Date"].unique()):
        date = pd.Timestamp(date)
        test = graded[graded["Date"] == date]
        hist = df[df["Date"] < date].dropna(subset=["HExpG+", "AExpG+"])
        hist = hist[hist["Date"] >= date - pd.DateOffset(months=PROD_LOOKBACK_MONTHS)]
        if len(hist) < MIN_TRAIN or test.empty:
            continue
        weights = pb.models.dixon_coles_weights(hist["Date"], PROD_XI)
        try:
            clf = fit_model(pb.models.NegativeBinomialGoalModel, hist, weights)
            delta = fit_draw_delta(clf, hist, weights)
        except Exception:
            continue
        for r in test.itertuples(index=False):
            try:
                p = one_x_two(np.asarray(clf.predict(r.Home, r.Away).grid))
            except Exception:
                continue
            recs.append({
                "date": date, "Season": int(r.Season), "Round": int(r.Round),
                "Home": r.Home, "Away": r.Away, "res": int(r.res),
                "pH": p[0], "pD": p[1], "pA": p[2], "delta": delta,
                "oH": float(r.onexbet_open_h), "oD": float(r.onexbet_open_d), "oA": float(r.onexbet_open_a),
                "cH": float(r.pinnacle_close_h), "cD": float(r.pinnacle_close_d), "cA": float(r.pinnacle_close_a),
            })
    return pd.DataFrame(recs).sort_values("date").reset_index(drop=True)


def apply_debias(P, novig_o, mode, b):
    if isinstance(mode, str) and mode == "delta":
        delta = b["delta"].values
        d = P[:, 1]
        z = 1.0 - d + delta * d
        return np.column_stack([P[:, 0] / z, delta * d / z, P[:, 2] / z])
    if mode == 0.0:
        return P
    pD = (1.0 - mode) * P[:, 1] + mode * novig_o[:, 1]
    scale = (1.0 - pD) / (1.0 - P[:, 1])
    return np.column_stack([P[:, 0] * scale, pD, P[:, 2] * scale])


def season_drift(b, novig_o, novig_c):
    drift = novig_c - novig_o
    seasons = b["Season"].values
    return {(s, k): drift[seasons == s, k].mean()
            for s in np.unique(seasons) for k in range(3)}


def grade(b, mode, *, allow_draw: bool):
    P_raw = b[["pH", "pD", "pA"]].values
    O = b[["oH", "oD", "oA"]].values
    C = b[["cH", "cD", "cA"]].values
    novig_o = (1 / O) / (1 / O).sum(1, keepdims=True)
    novig_c = (1 / C) / (1 / C).sum(1, keepdims=True)
    P = apply_debias(P_raw, novig_o, mode, b)
    ev = P * O - 1.0
    ev_pick = ev.copy()
    if not allow_draw:
        ev_pick[:, 1] = -np.inf  # never back the draw
    pick = ev_pick.argmax(1)
    best_ev = ev_pick.max(1)
    idx = np.arange(len(b))
    win = pick == b["res"].values
    pl = np.where(win, O[idx, pick] - 1.0, -1.0)
    clv = novig_c[idx, pick] - novig_o[idx, pick]
    drift = season_drift(b, novig_o, novig_c)
    seasons = b["Season"].values
    exclv = clv - np.array([drift[(seasons[i], pick[i])] for i in idx])
    R = (1 / O).sum(1) - 1.0
    bar = novig_o[idx, pick] * R
    return dict(P=P, P_raw=P_raw, novig_o=novig_o, pick=pick, best_ev=best_ev,
                win=win, pl=pl, clv=clv, exclv=exclv, bar=bar)


def print_baselines(b):
    O = b[["oH", "oD", "oA"]].values
    C = b[["cH", "cD", "cA"]].values
    novig_o = (1 / O) / (1 / O).sum(1, keepdims=True)
    novig_c = (1 / C) / (1 / C).sum(1, keepdims=True)
    drift = novig_c - novig_o
    R = (1 / O).sum(1) - 1.0
    print(f"\n{'=' * 74}")
    print(f"1xBet OPEN  ->  Pinnacle CLOSE   |   n={len(b)} fixtures, "
          f"seasons={sorted(b['Season'].unique())}")
    print(f"{'=' * 74}")
    print(f"  1xBet mean overround: {R.mean() * 100:.2f}%  "
          f"(vs Pinnacle open ~7.55%) -> p×R bar ~ {0.35 * R.mean() * 100:.2f}pp")
    print("  model-free CLV baselines (1xBet open -> Pinnacle close, §11.3):")
    for k, lbl in enumerate(["always home", "always draw", "always away"]):
        print(f"    {lbl:<12} {drift[:, k].mean() * 100:>+6.2f}pp (t={_t(drift[:, k]):>+5.2f})")


def report(label, b, mode):
    act = np.array([(b["res"].values == k).mean() for k in range(3)])
    g_any = grade(b, mode, allow_draw=True)
    P, P_raw, novig_o = g_any["P"], g_any["P_raw"], g_any["novig_o"]
    debiased = mode != 0.0
    shrunk = f" -> {P[:, 1].mean():.3f}" if debiased else ""
    print(f"\n{'-' * 74}\n{label}\n{'-' * 74}")
    print(f"  draw prob: model {P_raw[:, 1].mean():.3f}{shrunk} | "
          f"market(1xBet open) {novig_o[:, 1].mean():.3f} | actual {act[1]:.3f}")
    if isinstance(mode, str) and mode == "delta":
        print(f"  training-window delta: mean {b['delta'].mean():.3f}")

    for allow_draw in (True, False):
        g = grade(b, mode, allow_draw=allow_draw)
        pick, best_ev, pl, clv, exclv, bar, win = (
            g["pick"], g["best_ev"], g["pl"], g["clv"], g["exclv"], g["bar"], g["win"])
        tag = "WITH draw" if allow_draw else "NO draw  "
        print(f"\n  [{tag}]  {'thr':>4} {'n':>4} {'draws':>5} {'ROI':>8} {'t':>6} "
              f"{'CLV':>7} {'t':>6} {'exCLV':>7} {'t':>6} {'bar':>6} {'gap':>7} {'win%':>5}")
        for thr in EV_THRESHOLDS:
            m = best_ev > thr
            if m.sum() < 2:
                continue
            ndraw = int((pick[m] == 1).sum())
            gap = (clv[m].mean() - bar[m].mean()) * 100
            print(f"  {'':>11} {thr:>4.2f} {int(m.sum()):>4} {ndraw:>5} "
                  f"{pl[m].mean():>+8.3f} {_t(pl[m]):>+6.2f} "
                  f"{clv[m].mean() * 100:>+7.2f} {_t(clv[m]):>+6.2f} "
                  f"{exclv[m].mean() * 100:>+7.2f} {_t(exclv[m]):>+6.2f} "
                  f"{bar[m].mean() * 100:>6.2f} {gap:>+7.2f} {win[m].mean():>5.0%}")


def report_by_season(b, thr=0.20):
    """Per-season split of the thr>0.20 cell — the §11.1 robustness check that the
    single-2026 first cut could not do. A gap that is positive in EACH season (not
    just pooled) is what promotes a lead to a cross-season result."""
    seasons = sorted(int(s) for s in b["Season"].unique())
    print(f"\n{'=' * 74}\nPER-SEASON split at thr>{thr:.2f} (does the gap hold in every season?)\n{'=' * 74}")
    for label, mode in VARIANTS:
        for allow_draw in (True, False):
            tag = "WITH draw" if allow_draw else "NO draw  "
            print(f"\n  {label}  [{tag}]")
            print(f"  {'season':>7} {'n':>4} {'ROI':>8} {'t':>6} {'exCLV':>7} {'t':>6} {'gap':>7}")
            for scope, sub in [("pooled", b)] + [(str(s), b[b["Season"] == s].reset_index(drop=True))
                                                 for s in seasons]:
                g = grade(sub, mode, allow_draw=allow_draw)
                m = g["best_ev"] > thr
                if m.sum() < 2:
                    print(f"  {scope:>7} {'(n<2)':>4}"); continue
                gap = (g["clv"][m].mean() - g["bar"][m].mean()) * 100
                print(f"  {scope:>7} {int(m.sum()):>4} {g['pl'][m].mean():>+8.3f} {_t(g['pl'][m]):>+6.2f} "
                      f"{g['exclv'][m].mean() * 100:>+7.2f} {_t(g['exclv'][m]):>+6.2f} {gap:>+7.2f}")


def main():
    df = load()
    b = walk_forward(df)
    if b.empty:
        raise SystemExit("No gradeable fixtures (need onexbet_open_* + pinnacle_close_* + result).")
    print_baselines(b)
    for label, mode in VARIANTS:
        report(label, b, mode)
    report_by_season(b)
    print("\nReading guide: gap = CLV − bar (the §11.7 vig wall at 1xBet's overround)."
          "\ngap > 0 means the bet clears 1xBet's vig; exCLV is the model's edge over the"
          "\nhome-drift baseline. THREE seasons now (2024 + 2025 + 2026): at thr>0.20 the gap"
          "\nclears the wall in ALL THREE independently (§13.1). But per-bet ROI stays high-"
          "\nvariance — 2025 realized NEGATIVE ROI on a strongly +gap/+exCLV set — so read"
          "\nexCLV/gap, not ROI. thr>0.10 is thinner: its gap flips negative in 2026. CLV is vs"
          "\nPinnacle's close. (2023 carries no 1xBet lines yet.)")


if __name__ == "__main__":
    main()
