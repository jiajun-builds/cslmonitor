const DATA_BASES = ["./data", "../data/dashboard/json"];

const selectors = {
  signalRounds: document.getElementById("signal-rounds"),
  marketBody: document.getElementById("market-body"),
  marketComparisonBody: document.getElementById("market-comparison-body"),
  strengthBody: document.getElementById("strength-body"),
  tickerTrack: document.getElementById("ticker-track"),
};

function setText(bind, value) {
  document.querySelectorAll(`[data-bind="${bind}"]`).forEach((node) => {
    node.textContent = value;
  });
}

function formatUpdatedAt(value) {
  const date = new Date(value);
  return new Intl.DateTimeFormat("en-GB", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  }).format(date).replace(",", "") + " UTC";
}

function formatClock(date = new Date()) {
  return new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: "Europe/London",
  }).format(date);
}

function formatPercent(value) {
  return `${(value * 100).toFixed(1)}%`;
}

function formatRating(value) {
  return Number(value).toFixed(3);
}

function formatOdds(value) {
  return value == null ? "--" : Number(value).toFixed(2);
}

function formatLine(value) {
  if (value == null || Number.isNaN(Number(value))) {
    return "--";
  }
  const numeric = Number(value);
  if (Object.is(numeric, -0) || numeric === 0) {
    return "0.00";
  }
  return `${numeric > 0 ? "+" : "-"}${Math.abs(numeric).toFixed(2)}`;
}

function formatEv(value) {
  return value == null ? "--" : Number(value).toFixed(3);
}

function formatFeedStamp(value) {
  if (!value) {
    return "--";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return (
    new Intl.DateTimeFormat("en-GB", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
      timeZone: "UTC",
    }).format(date).replace(",", "") + " UTC"
  );
}

function evClass(value) {
  if (value > 0) {
    return "market-comparison__value--positive";
  }
  if (value < 0) {
    return "market-comparison__value--negative";
  }
  return "market-comparison__value--neutral";
}

function getBestBet(rows) {
  return rows.reduce((best, row) => {
    const variants = [
      {
        team: row.home_team,
        side: "H",
        line: row.home_spread,
        ev: Number(row.home_ah_ev),
      },
      {
        team: row.away_team,
        side: "A",
        line: row.away_spread,
        ev: Number(row.away_ah_ev),
      },
    ];

    variants.forEach((variant) => {
      if (Number.isNaN(variant.ev)) {
        return;
      }
      if (!best || variant.ev > best.ev) {
        best = variant;
      }
    });
    return best;
  }, null);
}

function getSignal(row) {
  const variants = [
    { type: "home", label: "Home", value: row.home_win_prob },
    { type: "draw", label: "Draw", value: row.draw_prob },
    { type: "away", label: "Away", value: row.away_win_prob },
  ];
  return variants.reduce((best, current) => (current.value > best.value ? current : best));
}

function buildProbBar(row) {
  return `
    <div class="prob-bar" aria-label="Probability split">
      <span class="prob-bar__home" style="width:${row.home_win_prob * 100}%"></span>
      <span class="prob-bar__draw" style="width:${row.draw_prob * 100}%"></span>
      <span class="prob-bar__away" style="width:${row.away_win_prob * 100}%"></span>
    </div>
  `;
}

function buildFormStrip(form) {
  const tokens = (form || "")
    .split(",")
    .filter(Boolean)
    .map((token) => {
      const value = token.trim();
      const cls =
        value === "W"
          ? "form-token--win"
          : value === "D"
            ? "form-token--draw"
            : "form-token--loss";
      return `<span class="form-token ${cls}">${value}</span>`;
    });
  return `<div class="form-strip">${tokens.join("")}</div>`;
}

function renderSignalBar(meta) {
  const playedCount = Number(meta.matches_played) || 0;
  const currentRound = Number(meta.current_round) || 1;
  const totalRounds = Number(meta.total_rounds) || currentRound;

  setText("signal-played-count", String(playedCount));

  if (!selectors.signalRounds) {
    return;
  }

  selectors.signalRounds.style.gridTemplateColumns = `repeat(${totalRounds}, minmax(0, 1fr))`;
  selectors.signalRounds.innerHTML = Array.from({ length: totalRounds }, (_, index) => {
    const round = index + 1;
    const cls =
      round < currentRound
        ? "signal-round signal-round--done"
        : round === currentRound
          ? "signal-round signal-round--current"
          : "signal-round";
    return `<span class="${cls}">${round}</span>`;
  }).join("");
}

function renderMarketRows(rows) {
  selectors.marketBody.innerHTML = rows
    .map((row) => {
      return `
        <tr>
          <td class="numeric">${row.round}</td>
          <td>${row.match_date}</td>
          <td>${row.match_time}</td>
          <td>
            <div class="match-cell">
              <span class="match-cell__home">
                <span class="market-match">${row.home_team} vs ${row.away_team}</span>
              </span>
            </div>
          </td>
          <td class="numeric prob-cell--home">
            <div class="prob-stack">
              <span class="prob-stack__value">${formatPercent(row.home_win_prob)}</span>
              <span class="prob-stack__meta">F ${formatOdds(row.home_win_fair_odds)}</span>
            </div>
          </td>
          <td class="numeric prob-cell--draw">
            <div class="prob-stack">
              <span class="prob-stack__value">${formatPercent(row.draw_prob)}</span>
              <span class="prob-stack__meta">F ${formatOdds(row.draw_fair_odds)}</span>
            </div>
          </td>
          <td class="numeric prob-cell--away">
            <div class="prob-stack">
              <span class="prob-stack__value">${formatPercent(row.away_win_prob)}</span>
              <span class="prob-stack__meta">F ${formatOdds(row.away_win_fair_odds)}</span>
            </div>
          </td>
        </tr>
      `;
    })
    .join("");
}

function renderStrength(rows) {
  selectors.strengthBody.innerHTML = rows
    .map(
      (row) => `
        <tr>
          <td class="numeric">${row.rank_overall}</td>
          <td>
            <div class="team-cell">
              <span class="team-cell__name">${row.team}</span>
              <span class="team-cell__profile">ATT ${formatRating(row.attack_rating)} · DEF ${formatRating(row.defense_rating)}</span>
            </div>
          </td>
          <td class="numeric">${formatRating(row.overall_rating)}</td>
          <td>${buildFormStrip(row.form)}</td>
        </tr>
      `,
    )
    .join("");
}

function renderMarketComparison(rows) {
  selectors.marketComparisonBody.innerHTML = rows
    .map(
      (row) => `
        <tr class="market-comparison__row market-comparison__row--home">
          <td class="numeric market-comparison__time" rowspan="2">${row.match_time}</td>
          <td class="market-comparison__match">${row.home_team}</td>
          <td class="numeric market-comparison__value market-comparison__value--line">H ${formatLine(row.home_spread)}</td>
          <td class="numeric market-comparison__value">${formatOdds(row.home_odds)}</td>
          <td class="numeric market-comparison__value ${evClass(row.home_ah_ev)}">${formatEv(row.home_ah_ev)}</td>
        </tr>
        <tr class="market-comparison__row market-comparison__row--away">
          <td class="market-comparison__match">${row.away_team}</td>
          <td class="numeric market-comparison__value market-comparison__value--line">A ${formatLine(row.away_spread)}</td>
          <td class="numeric market-comparison__value">${formatOdds(row.away_odds)}</td>
          <td class="numeric market-comparison__value ${evClass(row.away_ah_ev)}">${formatEv(row.away_ah_ev)}</td>
        </tr>
      `,
    )
    .join("");

  const latestUpdate = rows.reduce(
    (best, row) => (!best || (row.last_update && row.last_update > best) ? row.last_update : best),
    "",
  );
  const latestFetch = rows.reduce(
    (best, row) => (!best || (row.fetched_at && row.fetched_at > best) ? row.fetched_at : best),
    "",
  );
  setText(
    "panel-market-comparison-meta",
    `Updated ${formatFeedStamp(latestUpdate)} · Fetched ${formatFeedStamp(latestFetch)}`,
  );
}

function renderHeader(meta, fixtures, predictions, strength, marketComparison) {
  const nextFixture = fixtures[0];
  const strongest = strength[0];
  const topFavorite = [...predictions]
    .map((row) => ({ row, signal: getSignal(row) }))
    .sort((a, b) => b.signal.value - a.signal.value)[0];
  const bestBet = getBestBet(marketComparison);

  setText("masthead-trail", `${meta.competition_name} · Season ${meta.season} · ${meta.model_name}`);
  setText("masthead-next-date", meta.next_fixture_date);
  setText("masthead-updated", formatUpdatedAt(meta.updated_at));

  if (nextFixture) {
    setText("metric-next-fixture", `${nextFixture.home_team} vs ${nextFixture.away_team}`);
    setText("metric-next-fixture-note", `${nextFixture.match_date} ${nextFixture.match_time}`);
  }

  if (strongest) {
    setText("metric-strongest-team", strongest.team);
    setText("metric-strongest-team-note", `OVR ${formatRating(strongest.overall_rating)}`);
    setText("spotlight-team", strongest.team);
    setText("spotlight-subtitle", `Best overall rating across ${strength.length} clubs`);
    setText("spotlight-ovr", formatRating(strongest.overall_rating));
    setText("spotlight-att", formatRating(strongest.attack_rating));
    setText("spotlight-def", formatRating(strongest.defense_rating));
  }

  if (bestBet) {
    setText("metric-best-bet", bestBet.team);
    setText("metric-best-bet-note", `${bestBet.side} ${formatLine(bestBet.line)} · EV ${formatEv(bestBet.ev)}`);
  }

  if (topFavorite) {
    const fair =
      topFavorite.signal.type === "home"
        ? topFavorite.row.home_win_fair_odds
        : topFavorite.signal.type === "draw"
          ? topFavorite.row.draw_fair_odds
          : topFavorite.row.away_win_fair_odds;

    setText("metric-best-fair-odds", formatOdds(fair));
    setText("metric-best-fair-odds-note", `${topFavorite.row.home_team} vs ${topFavorite.row.away_team}`);
  }

  setText("metric-last-completed", meta.last_completed_match_date);
  setText("metric-season-window", `Season ${meta.season} · ${meta.timezone}`);
  setText("panel-market-stamp", `Last Updated on ${formatUpdatedAt(meta.updated_at)}`);
  setText("panel-market-meta", `${fixtures.length} matches · ${meta.model_name}`);
  setText("panel-strength-meta", `${strength.length} clubs · recent 5 form`);
}

function renderMeta(meta) {
  setText("meta-competition", meta.competition_name);
  setText("meta-season", meta.season);
  setText("meta-updated-at", meta.updated_at);
  setText("meta-timezone", meta.timezone);
  setText("meta-last-completed", meta.last_completed_match_date);
  setText("meta-next-fixture-date", meta.next_fixture_date);
  setText("meta-model-name", meta.model_name);
  setText("meta-model-version", meta.model_version);
}

function renderTicker(meta, fixtures, predictions, strength) {
  const strongest = strength[0];
  const nextFixture = fixtures[0];
  const topTwo = [...predictions]
    .map((row) => ({ row, signal: getSignal(row) }))
    .sort((a, b) => b.signal.value - a.signal.value)
    .slice(0, 2);

  const items = [
    `Season ${meta.season} terminal live at ${formatUpdatedAt(meta.updated_at)}`,
    strongest ? `Strongest club ${strongest.team} OVR ${formatRating(strongest.overall_rating)}` : null,
    nextFixture ? `Next fixture ${nextFixture.home_team} vs ${nextFixture.away_team} ${nextFixture.match_date} ${nextFixture.match_time}` : null,
    ...topTwo.map(({ row, signal }) => `${row.home_team} vs ${row.away_team} · ${signal.label} ${formatPercent(signal.value)}`),
  ].filter(Boolean);

  selectors.tickerTrack.textContent = items.join("  •  ");
}

function startClock() {
  const tick = () => setText("masthead-clock", formatClock(new Date()));
  tick();
  window.setInterval(tick, 1000);
}

function showError(message) {
  const banner = document.createElement("div");
  banner.className = "state-banner";
  banner.textContent = message;
  document.querySelector(".terminal-shell").prepend(banner);
}

async function loadJson(name) {
  const errors = [];

  for (const base of DATA_BASES) {
    const response = await fetch(`${base}/${name}`);
    if (response.ok) {
      return response.json();
    }
    errors.push(`${base}/${name} -> ${response.status}`);
  }

  throw new Error(`Failed to load ${name}. Tried: ${errors.join(", ")}`);
}

async function bootstrap() {
  try {
    const [meta, fixturesPayload, predictionsPayload, strengthPayload, marketComparisonPayload] = await Promise.all([
      loadJson("dashboard_meta.json"),
      loadJson("upcoming_fixtures.json"),
      loadJson("match_predictions.json"),
      loadJson("team_strength_rankings.json"),
      loadJson("upcoming_market_comparison.json"),
    ]);

    const fixtures = fixturesPayload.rows;
    const predictions = predictionsPayload.rows;
    const strength = strengthPayload.rows;
    const marketComparison = marketComparisonPayload.rows;
    const predictionById = new Map(predictions.map((row) => [row.fixture_id, row]));
    const mergedMarketRows = fixtures
      .map((fixture) => {
        const prediction = predictionById.get(fixture.fixture_id);
        return prediction ? { ...fixture, ...prediction } : null;
      })
      .filter(Boolean);

    renderHeader(meta, fixtures, predictions, strength, marketComparison);
    renderSignalBar(meta);
    renderMeta(meta);
    renderMarketRows(mergedMarketRows);
    renderMarketComparison(marketComparison);
    renderStrength(strength);
    renderTicker(meta, fixtures, predictions, strength);
    startClock();
  } catch (error) {
    console.error(error);
    showError("Terminal data load failed. Ensure dashboard JSON files exist in ./data for a built site or ../data/dashboard/json when running from the repo.");
  }
}

bootstrap();
