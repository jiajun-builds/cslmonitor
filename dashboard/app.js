"use strict";

/* ------------------------------------------------------------------ *
 * CSL Terminal — native drop-in dashboard.
 * Reads the same JSON contract as the existing build:
 *   dashboard_meta.json, upcoming_fixtures.json, match_predictions.json,
 *   team_strength_rankings.json, upcoming_market_comparison.json
 * from ./data (built site) or ../data/dashboard/json (repo run).
 * ------------------------------------------------------------------ */

const DATA_BASES = ["./data", "../data/dashboard/json"];
const DISPLAY_TZ = "Europe/London";
const ONEXBET_LEAGUE_URL = "https://1xbet.com/en/line/football";
const SIGNAL_ODDS_CAP = 7;

const el = {
  signalBody: document.getElementById("signal-body"),
  marketBody: document.getElementById("market-body"),
  strengthBody: document.getElementById("strength-body"),
  contextBody: document.getElementById("context-body"),
  roundFill: document.getElementById("round-fill"),
};

/* ---------- helpers ---------- */
function setText(bind, value) {
  document.querySelectorAll(`[data-bind="${bind}"]`).forEach((n) => { n.textContent = value; });
}
function pct(v) { return `${(v * 100).toFixed(1)}%`; }
function rating(v) { return Number(v).toFixed(3); }
function odds(v) { return v == null ? "--" : Number(v).toFixed(2); }
function ev(v) { if (v == null) return "--"; const n = Number(v); return (n >= 0 ? "+" : "") + n.toFixed(3); }
function evClass(v) { if (v == null) return "zero"; return v > 0.0005 ? "pos" : v < -0.0005 ? "neg" : "zero"; }
function sideLetter(k) { return k === "home" ? "H" : k === "away" ? "A" : "D"; }

function fmtStamp(v) {
  if (!v) return "--";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return String(v);
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
    hour12: false, timeZone: DISPLAY_TZ,
  }).format(d).replace(",", "");
}
function fmtDay(v, fb) {
  if (!v) return fb || "--";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return fb || "--";
  return new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit", day: "2-digit", timeZone: DISPLAY_TZ }).format(d);
}
function fmtTime(v, fb) {
  if (!v) return fb || "--";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return fb || "--";
  return new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: DISPLAY_TZ }).format(d);
}
function clock() {
  return new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false, timeZone: DISPLAY_TZ }).format(new Date());
}
function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

/* ---------- EV BET (bet signals) ---------- */
function renderSignals(rows) {
  let openMax = "";
  el.signalBody.innerHTML = rows.map((row) => {
    const outs = [
      { key: "home", label: row.home_team, prob: row.home_win_prob, odds: row.onexbet_open_home_odds, ev: row.onexbet_open_home_ev },
      { key: "draw", label: "Draw", prob: row.draw_prob, odds: row.onexbet_open_draw_odds, ev: row.onexbet_open_draw_ev },
      { key: "away", label: row.away_team, prob: row.away_win_prob, odds: row.onexbet_open_away_odds, ev: row.onexbet_open_away_ev },
    ];
    const maxKey = outs.reduce((a, b) => (b.prob > a.prob ? b : a)).key;
    const isBet = row.signal_state === "bet";
    if (row.onexbet_open_last_update > openMax) openMax = row.onexbet_open_last_update;

    const tr = outs.map((o, i) => {
      const timeCell = i === 0 ? `<td class="sig-time" rowspan="3">${esc(row.match_time)}</td>` : "";
      const nameCls = "sig-name" + (isBet && row.signal_pick === o.key ? " is-pick" : "");
      const probCls = "sig-prob" + (isBet && o.key === maxKey ? " is-max" : "");
      const evStrong = o.ev != null && o.ev >= 0.2 ? " strong" : "";
      let action = "";
      if (row.signal_pick === o.key && row.signal_state === "bet") {
        action = `<span class="sig-action"><span class="badge">● BET</span><a class="sig-link" href="${ONEXBET_LEAGUE_URL}" target="_blank" rel="noopener noreferrer">Link ↗</a></span>`;
      } else if (row.signal_pick === o.key && row.signal_state === "odds_cap") {
        action = `<span class="badge badge--cap">ODDS &gt; ${SIGNAL_ODDS_CAP}</span>`;
      }
      return `<tr>
        ${timeCell}
        <td class="${nameCls}">${esc(o.label)}</td>
        <td class="num ${probCls}">${pct(o.prob)}</td>
        <td class="num c-grp sig-odds">${odds(o.odds)}</td>
        <td class="num sig-ev ${evClass(o.ev)}${evStrong}">${ev(o.ev)}</td>
        <td class="c-grp">${action}</td>
      </tr>`;
    }).join("");

    return `<tbody class="fixture${isBet ? " fixture--bet" : ""}">${tr}</tbody>`;
  }).join("");

  return openMax;
}

/* ---------- SCHEDULE ---------- */
function renderMarket(rows) {
  el.marketBody.innerHTML = rows.map((r) => {
    const trio = [
      { k: "home", v: r.home_win_prob, f: r.home_win_fair_odds },
      { k: "draw", v: r.draw_prob, f: r.draw_fair_odds },
      { k: "away", v: r.away_win_prob, f: r.away_win_fair_odds },
    ];
    const maxKey = trio.reduce((a, b) => (b.v > a.v ? b : a)).k;
    const cell = (c) => `<td class="num prob-cell${c.k === maxKey ? " is-max" : ""}"><span class="pv">${pct(c.v)}</span><span class="pf">F ${odds(c.f)}</span></td>`;
    return `<tr>
      <td class="mk-rnd">${esc(r.round)}</td>
      <td class="mk-date">${fmtDay(r.kickoff_at, r.match_date)}</td>
      <td class="mk-time">${fmtTime(r.kickoff_at, r.match_time)}</td>
      <td class="mk-match">${esc(r.home_team)} vs ${esc(r.away_team)}</td>
      ${cell({ ...trio[0], grp: true }).replace('class="num prob-cell', 'class="num c-grp prob-cell')}
      ${cell(trio[1])}
      ${cell(trio[2])}
    </tr>`;
  }).join("");
}

/* ---------- TEAM STRENGTH ---------- */
function renderStrength(rows) {
  el.strengthBody.innerHTML = rows.map((t) => {
    const form = (t.form || "").split(",").filter(Boolean).map((x) => {
      const c = x.trim();
      const cls = c === "W" ? "w" : c === "D" ? "d" : "l";
      return `<span class="${cls}">${c}</span>`;
    }).join("");
    return `<tr>
      <td class="num st-rk${t.rank_overall <= 3 ? " top" : ""}">${t.rank_overall}</td>
      <td class="st-team">${esc(t.team)}</td>
      <td class="num c-grp st-ovr">${rating(t.overall_rating)}</td>
      <td class="num st-r">${rating(t.attack_rating)}</td>
      <td class="num st-r">${rating(t.defense_rating)}</td>
      <td class="c-grp"><div class="form">${form}</div></td>
    </tr>`;
  }).join("");
}

/* ---------- MODEL CONTEXT ---------- */
function renderContext(m) {
  const rows = [
    ["Competition", m.competition_name], ["Season", m.season],
    ["Last Update", m.updated_at], ["Model Update", m.model_updated_at],
    ["Timezone", DISPLAY_TZ], ["Last Completed", m.last_completed_match_date],
    ["Next Fixture", m.next_fixture_date], ["Model Name", m.model_name],
    ["Version", m.model_version], ["Matches Played", m.matches_played],
  ];
  el.contextBody.innerHTML = rows.map(([k, v]) => `<div class="meta__row"><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join("");
}

/* ---------- HEADER + KPI ---------- */
function renderHeader(meta, fixtures, predictions, strength, market, openMax) {
  setText("masthead-trail", `${meta.competition_name} · Season ${meta.season} · ${meta.model_name} · ${meta.model_version}`);
  setText("masthead-next-date", meta.next_fixture_date);
  setText("masthead-updated", fmtStamp(meta.updated_at));
  setText("played", String(meta.matches_played));
  setText("round-label", `${meta.current_round}/${meta.total_rounds}`);
  if (el.roundFill) el.roundFill.style.width = `${Math.round((meta.current_round / meta.total_rounds) * 100)}%`;

  setText("panel-signal-meta", `Model ${fmtStamp(meta.model_updated_at)} · 1XBET OPEN ${fmtStamp(openMax)}`);
  setText("panel-market-meta", `${predictions.length} matches · ${meta.model_name}`);
  setText("panel-strength-meta", `${strength.length} clubs · recent 5 form`);

  const nf = predictions[0] || fixtures[0];
  if (nf) {
    setText("next-fixture", `${nf.home_team} vs ${nf.away_team}`);
    setText("next-note", `${fmtDay(nf.kickoff_at, nf.match_date)} · ${fmtTime(nf.kickoff_at, nf.match_time)}`);
  }
  const sc = strength[0];
  if (sc) {
    setText("strong-team", sc.team);
    setText("strong-note", `OVR ${rating(sc.overall_rating)} · ATT ${rating(sc.attack_rating)} · DEF ${rating(sc.defense_rating)}`);
  }

  // Best bet / signals
  const bets = market
    .filter((r) => r.signal_state === "bet")
    .map((r) => ({ r, ev: r[`onexbet_open_${r.signal_pick}_ev`], odds: r[`onexbet_open_${r.signal_pick}_odds`], team: r.signal_pick === "home" ? r.home_team : r.signal_pick === "away" ? r.away_team : "Draw", key: r.signal_pick }))
    .sort((a, b) => b.ev - a.ev);
  setText("signals-count", String(bets.length));
  setText("signals-fixtures", String(market.length));

  if (bets.length) {
    const b = bets[0];
    setText("best-bet-team", b.team);
    setText("best-bet-note", `${sideLetter(b.key)} @ ${odds(b.odds)} · EV ${ev(b.ev)} · FIRES`);
    const more = bets.length > 1 ? ` · +${bets.length - 1} more` : "";
    setText("signals-note", `${b.team} (${sideLetter(b.key)}) @ ${odds(b.odds)}${more}`);
  } else {
    // surface top available edge
    let top = null;
    market.forEach((r) => {
      ["home", "draw", "away"].forEach((k) => {
        const e = r[`onexbet_open_${k}_ev`];
        if (e != null && (!top || e > top.ev)) top = { ev: e, odds: r[`onexbet_open_${k}_odds`], key: k, team: k === "home" ? r.home_team : k === "away" ? r.away_team : "Draw" };
      });
    });
    if (top) {
      setText("best-bet-team", top.team);
      setText("best-bet-note", `${sideLetter(top.key)} @ ${odds(top.odds)} · EV ${ev(top.ev)} · below thr`);
    }
    setText("signals-note", "— no signal");
  }
}

/* ---------- nav + clock + boot ---------- */
function initNav() {
  const links = Array.from(document.querySelectorAll("[data-view-target]"));
  const views = Array.from(document.querySelectorAll("[data-view]"));
  links.forEach((link) => {
    link.addEventListener("click", () => {
      const target = link.dataset.viewTarget;
      views.forEach((v) => v.classList.toggle("view--active", v.dataset.view === target));
      links.forEach((l) => {
        const active = l.dataset.viewTarget === target;
        l.classList.toggle("tab--active", active);
        l.setAttribute("aria-current", active ? "page" : "false");
      });
    });
  });
}
function startClock() { const tick = () => setText("masthead-clock", clock()); tick(); setInterval(tick, 1000); }

async function loadJson(name) {
  const errs = [];
  for (const base of DATA_BASES) {
    try {
      const res = await fetch(`${base}/${name}`);
      if (res.ok) return res.json();
      errs.push(`${base}/${name} -> ${res.status}`);
    } catch (e) { errs.push(`${base}/${name} -> ${e}`); }
  }
  throw new Error(`Failed to load ${name}. Tried: ${errs.join(", ")}`);
}

async function bootstrap() {
  try {
    const [meta, fixturesP, predictionsP, strengthP, marketP] = await Promise.all([
      loadJson("dashboard_meta.json"),
      loadJson("upcoming_fixtures.json"),
      loadJson("match_predictions.json"),
      loadJson("team_strength_rankings.json"),
      loadJson("upcoming_market_comparison.json"),
    ]);
    const fixtures = fixturesP.rows;
    const predictions = predictionsP.rows;
    const strength = strengthP.rows;
    const kickoffByTeams = new Map(fixtures.map((f) => [`${f.home_team}|${f.away_team}`, f.kickoff_at]));
    const market = marketP.rows.map((row) => ({
      ...row,
      kickoff_at: row.kickoff_at ?? kickoffByTeams.get(`${row.home_team}|${row.away_team}`),
    }));

    const openMax = renderSignals(market);
    renderMarket(predictions);
    renderStrength(strength);
    renderContext(meta);
    renderHeader(meta, fixtures, predictions, strength, market, openMax);
    startClock();
  } catch (error) {
    console.error(error);
    const banner = document.createElement("div");
    banner.className = "state-banner";
    banner.textContent = "Terminal data load failed. Ensure dashboard JSON files exist in ./data or ../data/dashboard/json.";
    document.querySelector(".term").prepend(banner);
  }
}

initNav();
bootstrap();
