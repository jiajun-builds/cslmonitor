const DATA_BASES = ["./data", "../data/dashboard/json"];

// All wall-clock times on the dashboard (system stamps, live clock, kickoff
// times) are displayed in this single zone. Kickoff timestamps are stored in
// Asia/Shanghai (+08:00) but converted here for a consistent reading.
const DISPLAY_TZ = "Europe/London";

const selectors = {
  signalRounds: document.getElementById("signal-rounds"),
  marketBody: document.getElementById("market-body"),
  marketComparisonBody: document.getElementById("market-comparison-body"),
  strengthBody: document.getElementById("strength-body"),
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
    timeZone: DISPLAY_TZ,
    timeZoneName: "short",
  }).format(date).replace(",", "");
}

function formatClock(date = new Date()) {
  return new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: DISPLAY_TZ,
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
  return new Intl.DateTimeFormat("en-GB", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: DISPLAY_TZ,
    timeZoneName: "short",
  }).format(date).replace(",", "");
}

function formatKickoffDate(kickoffAt, fallback = "--") {
  if (!kickoffAt) {
    return fallback;
  }
  const date = new Date(kickoffAt);
  if (Number.isNaN(date.getTime())) {
    return fallback;
  }
  // en-CA keeps the ISO YYYY-MM-DD style already used for match dates.
  return new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone: DISPLAY_TZ,
  }).format(date);
}

function formatKickoffTime(kickoffAt, fallback = "--") {
  if (!kickoffAt) {
    return fallback;
  }
  const date = new Date(kickoffAt);
  if (Number.isNaN(date.getTime())) {
    return fallback;
  }
  return new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: DISPLAY_TZ,
  }).format(date);
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

// "H -0.25" — side prefix + handicap line (odds shown in a separate column).
function sideLine(side, line) {
  if (line == null || Number.isNaN(Number(line))) {
    return "--";
  }
  return `${side} ${formatLine(line)}`;
}

// Arrow for how a side's handicap moved from open to now, by absolute magnitude:
// ↓ narrowed (|now| < |open|), ↑ widened (|now| > |open|), = unchanged.
function lineMove(openLine, nowLine) {
  if (openLine == null || nowLine == null) {
    return "";
  }
  const o = Number(openLine);
  const n = Number(nowLine);
  if (Number.isNaN(o) || Number.isNaN(n)) {
    return "";
  }
  const delta = Math.abs(n) - Math.abs(o);
  if (delta < 0) {
    return "↓";
  }
  if (delta > 0) {
    return "↑";
  }
  return "=";
}

function getBestBet(rows) {
  return rows.reduce((best, row) => {
    const variants = [
      {
        team: row.home_team,
        side: "H",
        line: row.home_spread,
        // null (open-only fixture, no Now line) -> NaN so it's skipped below;
        // Number(null) is 0, which would otherwise look like a real 0-EV bet.
        ev: row.home_ah_ev == null ? NaN : Number(row.home_ah_ev),
      },
      {
        team: row.away_team,
        side: "A",
        line: row.away_spread,
        ev: row.away_ah_ev == null ? NaN : Number(row.away_ah_ev),
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
          <td>${formatKickoffDate(row.kickoff_at, row.match_date)}</td>
          <td>${formatKickoffTime(row.kickoff_at, row.match_time)}</td>
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

function renderMarketComparison(rows, meta) {
  selectors.marketComparisonBody.innerHTML = rows
    .map(
      (row) => `
        <tr class="market-comparison__row market-comparison__row--home">
          <td class="numeric market-comparison__time" rowspan="2">${formatKickoffTime(row.kickoff_at, row.match_time)}</td>
          <td class="market-comparison__match">${row.home_team}</td>
          <td class="numeric market-comparison__value market-comparison__value--line market-comparison__group-start market-comparison__line-cell" data-tip-time="${row.open_last_update ?? ""}" data-tip-line="${row.open_home_spread ?? ""}" data-tip-hodds="${row.open_home_odds ?? ""}" data-tip-aodds="${row.open_away_odds ?? ""}">${sideLine("H", row.open_home_spread)}</td>
          <td class="numeric market-comparison__value">${formatOdds(row.open_home_odds)}</td>
          <td class="numeric market-comparison__value ${evClass(row.open_home_ah_ev)}">${formatEv(row.open_home_ah_ev)}</td>
          <td class="numeric market-comparison__value market-comparison__value--line market-comparison__group-start market-comparison__line-cell" data-tip-time="${row.last_update ?? ""}" data-tip-line="${row.home_spread ?? ""}" data-tip-hodds="${row.home_odds ?? ""}" data-tip-aodds="${row.away_odds ?? ""}">${sideLine("H", row.home_spread)}</td>
          <td class="numeric market-comparison__value">${formatOdds(row.home_odds)}</td>
          <td class="numeric market-comparison__value ${evClass(row.home_ah_ev)}">${formatEv(row.home_ah_ev)}</td>
          <td class="numeric market-comparison__value market-comparison__move">${lineMove(row.open_home_spread, row.home_spread)}</td>
        </tr>
        <tr class="market-comparison__row market-comparison__row--away">
          <td class="market-comparison__match">${row.away_team}</td>
          <td class="numeric market-comparison__value market-comparison__value--line market-comparison__group-start market-comparison__line-cell" data-tip-time="${row.open_last_update ?? ""}" data-tip-line="${row.open_away_spread ?? ""}" data-tip-hodds="${row.open_home_odds ?? ""}" data-tip-aodds="${row.open_away_odds ?? ""}">${sideLine("A", row.open_away_spread)}</td>
          <td class="numeric market-comparison__value">${formatOdds(row.open_away_odds)}</td>
          <td class="numeric market-comparison__value ${evClass(row.open_away_ah_ev)}">${formatEv(row.open_away_ah_ev)}</td>
          <td class="numeric market-comparison__value market-comparison__value--line market-comparison__group-start market-comparison__line-cell" data-tip-time="${row.last_update ?? ""}" data-tip-line="${row.away_spread ?? ""}" data-tip-hodds="${row.home_odds ?? ""}" data-tip-aodds="${row.away_odds ?? ""}">${sideLine("A", row.away_spread)}</td>
          <td class="numeric market-comparison__value">${formatOdds(row.away_odds)}</td>
          <td class="numeric market-comparison__value ${evClass(row.away_ah_ev)}">${formatEv(row.away_ah_ev)}</td>
          <td class="numeric market-comparison__value market-comparison__move">${lineMove(row.open_away_spread, row.away_spread)}</td>
        </tr>
      `,
    )
    .join("");

  // The model is rebuilt daily; the Now line refreshes every few hours. Label the two
  // times distinctly so a stale/fresh feed is never mistaken for a stale/fresh model.
  const latestFetch = rows.reduce(
    (best, row) => (!best || (row.fetched_at && row.fetched_at > best) ? row.fetched_at : best),
    "",
  );
  const modelUpdated = meta?.model_updated_at ?? meta?.updated_at ?? "";
  setText(
    "panel-market-comparison-meta",
    `Model ${formatFeedStamp(modelUpdated)} · Odds fetched ${formatFeedStamp(latestFetch)}`,
  );
}

function renderHeader(meta, fixtures, predictions, strength, marketComparison) {
  const nextFixture = fixtures[0];
  const strongest = strength[0];
  const topFavorite = [...predictions]
    .map((row) => ({ row, signal: getSignal(row) }))
    .sort((a, b) => b.signal.value - a.signal.value)[0];
  const bestBet = getBestBet(marketComparison);

  setText("masthead-trail", `${meta.competition_name} · Season ${meta.season} · ${meta.model_name} · ${meta.model_version}`);
  setText("masthead-next-date", meta.next_fixture_date);
  setText("masthead-updated", formatUpdatedAt(meta.updated_at));

  if (nextFixture) {
    setText("metric-next-fixture", `${nextFixture.home_team} vs ${nextFixture.away_team}`);
    setText(
      "metric-next-fixture-note",
      `${formatKickoffDate(nextFixture.kickoff_at, nextFixture.match_date)} ${formatKickoffTime(nextFixture.kickoff_at, nextFixture.match_time)}`,
    );
  }

  if (strongest) {
    setText("metric-strongest-team", strongest.team);
    setText(
      "metric-strongest-team-note",
      `OVR ${formatRating(strongest.overall_rating)} · ATT ${formatRating(strongest.attack_rating)} · DEF ${formatRating(strongest.defense_rating)}`,
    );
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
  setText("metric-season-window", `Season ${meta.season} · ${DISPLAY_TZ}`);
  setText("panel-market-stamp", `Last Updated on ${formatUpdatedAt(meta.updated_at)}`);
  setText("panel-market-meta", `${fixtures.length} matches · ${meta.model_name}`);
  setText("panel-strength-meta", `${strength.length} clubs · recent 5 form`);
}

function renderMeta(meta) {
  setText("meta-competition", meta.competition_name);
  setText("meta-season", meta.season);
  setText("meta-updated-at", meta.updated_at);
  setText("meta-timezone", DISPLAY_TZ);
  setText("meta-last-completed", meta.last_completed_match_date);
  setText("meta-next-fixture-date", meta.next_fixture_date);
  setText("meta-model-name", meta.model_name);
  setText("meta-model-version", meta.model_version);
}

function startClock() {
  const tick = () => setText("masthead-clock", formatClock(new Date()));
  tick();
  window.setInterval(tick, 1000);
}

function initNav() {
  const links = Array.from(document.querySelectorAll("[data-view-target]"));
  const views = Array.from(document.querySelectorAll("[data-view]"));
  if (!links.length || !views.length) {
    return;
  }

  function activate(target) {
    views.forEach((view) => {
      view.classList.toggle("terminal-view--active", view.dataset.view === target);
    });
    links.forEach((link) => {
      const isActive = link.dataset.viewTarget === target;
      link.classList.toggle("sidebar__link--active", isActive);
      link.setAttribute("aria-current", isActive ? "page" : "false");
    });
  }

  links.forEach((link) => {
    link.addEventListener("click", () => activate(link.dataset.viewTarget));
  });
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
    // Market comparison rows carry only match_time (no kickoff_at), so borrow
    // the full kickoff timestamp from fixtures by team pairing for TZ display.
    const kickoffByTeams = new Map(
      fixtures.map((f) => [`${f.home_team}|${f.away_team}`, f.kickoff_at]),
    );
    const marketComparison = marketComparisonPayload.rows.map((row) => ({
      ...row,
      kickoff_at: row.kickoff_at ?? kickoffByTeams.get(`${row.home_team}|${row.away_team}`),
    }));
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
    renderMarketComparison(marketComparison, meta);
    renderStrength(strength);
    startClock();
  } catch (error) {
    console.error(error);
    showError("Terminal data load failed. Ensure dashboard JSON files exist in ./data for a built site or ../data/dashboard/json when running from the repo.");
  }
}

// Hover tooltip for Open Line cells: shows the captured opening snapshot
// (opening timestamp, the line, and both sides' odds).
function formatOpenStamp(iso) {
  if (!iso) {
    return "";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return String(iso);
  }
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: DISPLAY_TZ,
  })
    .format(date)
    .toUpperCase();
}

function ensureOddsTooltip() {
  let el = document.getElementById("odds-tooltip");
  if (!el) {
    el = document.createElement("div");
    el.id = "odds-tooltip";
    el.className = "odds-tooltip";
    el.hidden = true;
    document.body.appendChild(el);
  }
  return el;
}

function showOddsTooltip(cell) {
  const { tipTime, tipLine, tipHodds, tipAodds } = cell.dataset;
  if (!tipTime && !tipLine && !tipHodds && !tipAodds) {
    return; // no captured line for this side
  }
  const tip = ensureOddsTooltip();
  tip.innerHTML = `
    <div class="odds-tooltip__time">${formatOpenStamp(tipTime)}</div>
    <div class="odds-tooltip__grid">
      <span class="odds-tooltip__key">Line</span><span class="odds-tooltip__val">${tipLine === "" ? "--" : formatLine(tipLine)}</span>
      <span class="odds-tooltip__key">home_odds</span><span class="odds-tooltip__val">${formatOdds(tipHodds || null)}</span>
      <span class="odds-tooltip__key">away_odds</span><span class="odds-tooltip__val">${formatOdds(tipAodds || null)}</span>
    </div>`;
  tip.hidden = false;
}

function positionOddsTooltip(event) {
  const tip = document.getElementById("odds-tooltip");
  if (!tip || tip.hidden) {
    return;
  }
  const pad = 14;
  const rect = tip.getBoundingClientRect();
  let x = event.clientX + pad;
  let y = event.clientY + pad;
  if (x + rect.width > window.innerWidth) {
    x = event.clientX - rect.width - pad;
  }
  if (y + rect.height > window.innerHeight) {
    y = event.clientY - rect.height - pad;
  }
  tip.style.left = `${Math.max(4, x)}px`;
  tip.style.top = `${Math.max(4, y)}px`;
}

function hideOddsTooltip() {
  const tip = document.getElementById("odds-tooltip");
  if (tip) {
    tip.hidden = true;
  }
}

function initOddsTooltip() {
  // Delegation on document so it keeps working after the table re-renders.
  document.addEventListener("mouseover", (event) => {
    const cell = event.target.closest(".market-comparison__line-cell");
    if (cell) {
      showOddsTooltip(cell);
      positionOddsTooltip(event);
    }
  });
  document.addEventListener("mousemove", (event) => {
    if (event.target.closest(".market-comparison__line-cell")) {
      positionOddsTooltip(event);
    }
  });
  document.addEventListener("mouseout", (event) => {
    const from = event.target.closest(".market-comparison__line-cell");
    const to = event.relatedTarget && event.relatedTarget.closest
      ? event.relatedTarget.closest(".market-comparison__line-cell")
      : null;
    if (from && !to) {
      hideOddsTooltip();
    }
  });
}

initNav();
initOddsTooltip();
bootstrap();
