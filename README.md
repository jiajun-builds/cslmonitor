# cslmonitor — archived

This repository has been superseded by **[betmodel](https://github.com/jiajun-builds/betmodel)**,
which runs the Chinese Super League alongside Liga MX from one engine where a
league is configuration rather than a fork.

Nothing here is live. The workflows are disabled and the Cloudflare Worker that
dispatched them has been deleted.

## Where everything went

| here | in betmodel |
|---|---|
| `src/csl/` | `src/betmodel/`, league-agnostic |
| model and signal parameters | `leagues/csl.yml` |
| `data/raw_data/CHN_*.csv` | `data/csl/` |
| `data/raw_data/CHN_pinnacle_spreads_history.csv` | `data/csl/odds_capture_history.csv` |
| `data/dashboard/json/` | `public/legacy/csl/` |
| the GitHub Pages board | [myevbettracker](https://github.com/jiajun-builds/myevbettracker) |

The odds-capture history — the one irreplaceable thing here, since no provider
sells opening lines retroactively — was reconciled into betmodel before this
repository was switched off, and the reconciliation reports a zero delta in both
directions.

The full history of this repository is preserved inside betmodel: both trees were
merged with `--allow-unrelated-histories`, so its commits are reachable there.
