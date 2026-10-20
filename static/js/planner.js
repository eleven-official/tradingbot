const form = document.querySelector("#trade-council-form");
const liveForm = document.querySelector("#live-feed-form");
const liveStatus = document.querySelector("#live-feed-status");
const runButton = document.querySelector("#run-council");
const chart = document.querySelector("#market-chart");
const chartEmpty = document.querySelector("#chart-empty");
const strategyBoard = document.querySelector("#strategy-board");
const strategyEmpty = document.querySelector("#strategy-empty");
const botChatForm = document.querySelector("#bot-chat-form");
const botChatLog = document.querySelector("#bot-chat-log");
const botChatStatus = document.querySelector("#bot-chat-status");
const botQuestion = document.querySelector("#bot-question");
const botSend = document.querySelector("#bot-send");
let marketSnapshot = null;
let selectedStrategyKey = "";
const JOURNAL_STORAGE_KEY = "loki.paper-journal.v1";
const DAILY_RISK_STORAGE_KEY = "loki.daily-risk-limit.v1";
const dailyRiskLimitInput = document.querySelector("#daily-risk-limit");
let dailyRiskSummary = null;
let dailyRiskRequestId = 0;
let dailyRiskTimer = null;
let dailyRiskMidnightTimer = null;
let journalEntries = readJournalEntries();
let lastDecision = null;

const number = (value, digits = 2) => new Intl.NumberFormat(undefined, { maximumFractionDigits: digits }).format(Number(value));
const price = (value) => new Intl.NumberFormat(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 6 }).format(Number(value));
const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);

function setPlanField(name, value) {
  form.elements[name].value = value;
}

function emaSeries(values, period) {
  const alpha = 2 / (period + 1);
  let current = values[0];
  return values.map((value, index) => {
    if (index > 0) current = alpha * value + (1 - alpha) * current;
    return current;
  });
}

function renderChart(snapshot) {
  const candles = (snapshot.candles || []).filter((bar) => [bar.open, bar.high, bar.low, bar.close, bar.volume].every(Number.isFinite));
  if (!candles.length) {
    chart.hidden = true;
    chartEmpty.hidden = false;
    return;
  }

  const width = 900, height = 320;
  const plot = { left: 70, right: 858, top: 18, bottom: 225, volumeTop: 247, volumeBottom: 292 };
  const lows = candles.map((bar) => bar.low);
  const highs = candles.map((bar) => bar.high);
  const rawMin = Math.min(...lows, Number(snapshot.current_price)), rawMax = Math.max(...highs, Number(snapshot.current_price));
  const pad = Math.max((rawMax - rawMin) * 0.08, rawMax * 0.001);
  const min = rawMin - pad, max = rawMax + pad;
  const y = (value) => plot.bottom - ((value - min) / (max - min || 1)) * (plot.bottom - plot.top);
  const slot = (plot.right - plot.left) / candles.length;
  const bodyWidth = Math.max(3, Math.min(12, slot * 0.54));
  const maxVolume = Math.max(...candles.map((bar) => bar.volume), 1);
  const closes = candles.map((bar) => bar.close);
  const fast = emaSeries(closes, 8), slow = emaSeries(closes, 20);
  const pathFor = (values) => values.map((value, index) => `${index ? "L" : "M"}${(plot.left + slot * index + slot / 2).toFixed(1)},${y(value).toFixed(1)}`).join(" ");

  const grid = Array.from({ length: 5 }, (_, index) => {
    const gridY = plot.top + index * ((plot.bottom - plot.top) / 4);
    const value = max - index * ((max - min) / 4);
    return `<line class="gridline" x1="${plot.left}" x2="${plot.right}" y1="${gridY}" y2="${gridY}"/><text class="axis-label" x="4" y="${gridY + 3}">${escapeHtml(price(value))}</text>`;
  }).join("");

  const bars = candles.map((bar, index) => {
    const center = plot.left + slot * index + slot / 2;
    const up = bar.close >= bar.open;
    const color = up ? "#54cb98" : "#ff928b";
    const bodyY = Math.min(y(bar.open), y(bar.close));
    const bodyHeight = Math.max(1.5, Math.abs(y(bar.close) - y(bar.open)));
    const volumeHeight = (bar.volume / maxVolume) * (plot.volumeBottom - plot.volumeTop);
    const timeLabel = new Date(Number(bar.time) * 1000).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
    const title = `${timeLabel} · O ${price(bar.open)} · H ${price(bar.high)} · L ${price(bar.low)} · C ${price(bar.close)} · V ${number(bar.volume, 0)}`;
    return `<g><title>${escapeHtml(title)}</title><line class="candle-wick" x1="${center}" x2="${center}" y1="${y(bar.high)}" y2="${y(bar.low)}" stroke="${color}"/><rect class="candle-body" x="${center - bodyWidth / 2}" y="${bodyY}" width="${bodyWidth}" height="${bodyHeight}" fill="${color}"/><rect class="volume-bar" x="${center - bodyWidth / 2}" y="${plot.volumeBottom - volumeHeight}" width="${bodyWidth}" height="${volumeHeight}" fill="${color}"/></g>`;
  }).join("");

  const currentPrice = Number(snapshot.current_price);
  const currentY = y(currentPrice);
  const currentLabelY = Math.max(12, Math.min(plot.bottom - 3, currentY - 5));
  const xLabels = [0, Math.floor((candles.length - 1) / 2), candles.length - 1].filter((value, index, list) => list.indexOf(value) === index).map((index) => {
    const label = new Date(Number(candles[index].time) * 1000).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
    return `<text class="axis-label" x="${plot.left + slot * index + slot / 2}" y="315" text-anchor="middle">${escapeHtml(label)}</text>`;
  }).join("");

  chart.setAttribute("viewBox", `0 0 ${width} ${height}`);
  chart.setAttribute("aria-label", `${escapeHtml(snapshot.symbol)} ${escapeHtml(snapshot.interval)} candlestick chart with EMA 8 and EMA 20`);
  chart.innerHTML = `<title>${escapeHtml(snapshot.symbol)} completed candles</title>
    ${grid}
    <line class="gridline" x1="${plot.left}" x2="${plot.right}" y1="238" y2="238"/>
    ${bars}
    <path class="ema-line" d="${pathFor(slow)}" stroke="#72dbc1"><title>EMA 20</title></path>
    <path class="ema-line" d="${pathFor(fast)}" stroke="#8ccfff"><title>EMA 8</title></path>
    <line class="last-line" x1="${plot.left}" x2="${plot.right}" y1="${currentY}" y2="${currentY}"/>
    <rect x="${plot.right - 62}" y="${currentLabelY - 10}" width="62" height="17" rx="3" fill="#b4f2d2"/>
    <text class="last-label" x="${plot.right - 56}" y="${currentLabelY + 2}">${escapeHtml(price(currentPrice))}</text>
    <text class="axis-label" x="${plot.left}" y="240">VOLUME</text>${xLabels}`;
  chart.hidden = false;
  chartEmpty.hidden = true;
  document.querySelector("#chart-window").textContent = `${candles.length} completed bars · ${snapshot.interval}`;
  document.querySelector("#chart-caption").textContent = `${snapshot.symbol} · current price line · EMA 8 / 20`;
}

function renderStrategyBoard(snapshot) {
  const candidates = snapshot.strategy_candidates || [];
  if (!candidates.length) {
    strategyBoard.hidden = true;
    strategyEmpty.hidden = false;
    return;
  }
  if (!candidates.some((candidate) => candidate.key === selectedStrategyKey)) {
    selectedStrategyKey = snapshot.selected_strategy || candidates[0].key;
  }
  strategyBoard.hidden = false;
  strategyEmpty.hidden = true;
  const active = candidates.find((candidate) => candidate.key === selectedStrategyKey) || candidates[0];
  const evidence = (active.evidence || []).map((item) => `<li class="${item.startsWith("PASS") ? "matched" : "missed"}">${escapeHtml(item)}</li>`).join("");
  strategyFocus.innerHTML = `<span>${escapeHtml(active.state.replaceAll("_", " "))}</span><h3>${escapeHtml(active.name)}</h3><p>${escapeHtml(active.summary)}</p><div class="focus-score">${number(active.score, 0)}<small> / 100 rules match</small></div><ul class="focus-evidence">${evidence}</ul>`;
  strategyCandidates.innerHTML = candidates.map((candidate) => `<button type="button" class="strategy-option ${candidate.score < 60 ? "low" : ""}" data-strategy-key="${escapeHtml(candidate.key)}" aria-pressed="${candidate.key === active.key}"><strong>${escapeHtml(candidate.name)}</strong><span>${escapeHtml(candidate.state.replaceAll("_", " "))}</span><b>${number(candidate.score, 0)}</b></button>`).join("");
  setPlanField("setup_name", active.name);
  setPlanField("setup_score", String(active.score));
}

const strategyFocus = document.querySelector("#strategy-focus");
const strategyCandidates = document.querySelector("#strategy-candidates");

strategyCandidates.addEventListener("click", (event) => {
  const button = event.target.closest("[data-strategy-key]");
  if (!button || !marketSnapshot) return;
  selectedStrategyKey = button.dataset.strategyKey;
  renderStrategyBoard(marketSnapshot);
});

function renderLiveSnapshot(snapshot) {
  marketSnapshot = snapshot;
  selectedStrategyKey = snapshot.selected_strategy || "";
  setPlanField("entry_price", snapshot.current_price);
  setPlanField("current_price", snapshot.current_price);
  setPlanField("trend", snapshot.trend);
  setPlanField("volatility_percent", Number(snapshot.volatility_percent).toFixed(3));
  setPlanField("volume_ratio", Number(snapshot.volume_ratio).toFixed(2));
  setPlanField("spread_percent", Number(snapshot.spread_percent).toFixed(4));
  setPlanField("market_data_age_seconds", Math.ceil(snapshot.data_age_seconds));
  setPlanField("market_open", "true");
  setPlanField("stop_price", "");
  setPlanField("target_price", "");

  document.querySelector("#stat-price").textContent = price(snapshot.current_price);
  document.querySelector("#stat-symbol").textContent = `${snapshot.symbol} · ${snapshot.interval}`;
  const change = document.querySelector("#stat-change");
  change.textContent = `${snapshot.change_24h_percent >= 0 ? "+" : ""}${number(snapshot.change_24h_percent)}%`;
  change.className = snapshot.change_24h_percent >= 0 ? "positive" : "negative";
  document.querySelector("#stat-spread").textContent = `${number(snapshot.spread_percent, 4)}%`;
  document.querySelector("#stat-age").textContent = `${number(snapshot.data_age_seconds, 0)}s`;
  document.querySelector("#stat-source").textContent = `${(snapshot.candles || []).length} completed bars`;
  const regime = document.querySelector("#indicator-trend");
  regime.textContent = snapshot.trend;
  regime.className = snapshot.trend === "BULLISH" ? "positive" : snapshot.trend === "BEARISH" ? "negative" : "";
  document.querySelector("#indicator-rsi").textContent = number(snapshot.rsi_14, 1);
  document.querySelector("#indicator-volume").textContent = `${number(snapshot.volume_ratio, 2)}×`;
  const ema = document.querySelector("#indicator-ema");
  ema.textContent = snapshot.ema_fast > snapshot.ema_slow ? "Fast above slow" : snapshot.ema_fast < snapshot.ema_slow ? "Fast below slow" : "Flat";
  ema.className = snapshot.ema_fast > snapshot.ema_slow ? "positive" : snapshot.ema_fast < snapshot.ema_slow ? "negative" : "";
  liveStatus.textContent = `${snapshot.symbol} feed refreshed · ${new Date(Number(snapshot.observed_at) * 1000).toLocaleTimeString()}. Set a stop and target to continue.`;
  liveStatus.className = "live-ok";
  updateBotContextStatus();
  renderChart(snapshot);
  renderStrategyBoard(snapshot);
}

liveForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const values = Object.fromEntries(new FormData(liveForm));
  const refreshButton = liveForm.querySelector("button[type=submit]");
  refreshButton.disabled = true;
  refreshButton.innerHTML = "<span aria-hidden=\"true\">↻</span> Loading…";
  liveStatus.textContent = "Loading read-only Binance Spot data…";
  liveStatus.className = "";
  try {
    const search = new URLSearchParams({ symbol: values.symbol.toUpperCase(), interval: values.interval });
    const response = await fetch(`/api/market-snapshot?${search}`);
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || "Unable to load the public market feed.");
    renderLiveSnapshot(body.snapshot);
  } catch (error) {
    liveStatus.textContent = error.message;
    liveStatus.className = "live-error";
    if (marketSnapshot) {
      const staleAge = Math.max(
        Number(form.elements.market_data_age_seconds.value) || 0,
        (Number(form.elements.max_data_age_seconds.value) || 60) + 1,
      );
      setPlanField("market_data_age_seconds", staleAge);
      setPlanField("setup_name", "");
      setPlanField("setup_score", "");
      selectedStrategyKey = "";
      marketSnapshot = null;
      strategyBoard.hidden = true;
      strategyEmpty.hidden = false;
      strategyEmpty.textContent = "Refresh failed. Previous market data is marked stale and will fail the Scout gate.";
      chart.hidden = true;
      chartEmpty.hidden = false;
      chartEmpty.innerHTML = "<strong>Feed refresh failed</strong><span>Previous candles are hidden and market inputs are marked stale.</span>";
      document.querySelector("#stat-price").textContent = "—";
      document.querySelector("#stat-symbol").textContent = "No active snapshot";
      document.querySelector("#stat-change").textContent = "—";
      document.querySelector("#stat-change").className = "";
      document.querySelector("#stat-spread").textContent = "—";
      document.querySelector("#stat-age").textContent = "STALE";
      document.querySelector("#stat-source").textContent = "Refresh failed";
      ["#indicator-trend", "#indicator-rsi", "#indicator-volume", "#indicator-ema"].forEach((selector) => {
        const indicator = document.querySelector(selector);
        indicator.textContent = "—";
        indicator.className = "";
      });
    }
  } finally {
    refreshButton.disabled = false;
    refreshButton.innerHTML = "<span aria-hidden=\"true\">↻</span> Refresh feed";
  }
});

function planMap(plan, input) {
  const levels = [Number(input.stop_price), Number(input.entry_price), Number(input.target_price)];
  const min = Math.min(...levels), max = Math.max(...levels);
  const padding = Math.max((max - min) * .22, max * .01);
  const scale = (value) => 171 - ((value - min + padding) / (max - min + padding * 2)) * 140;
  const line = (value, color, label) => `<line x1="75" x2="325" y1="${scale(value)}" y2="${scale(value)}" stroke="${color}" stroke-width="2"/><text x="8" y="${scale(value) + 4}" fill="${color}">${label}</text><text x="334" y="${scale(value) + 4}" fill="#ecf2f0">${escapeHtml(price(value))}</text>`;
  return `<svg class="plan-map" viewBox="0 0 410 194" role="img" aria-label="Risk plan map. Stop below entry and target above entry.">
    <rect x="73" y="17" width="254" height="160" rx="7" fill="#0b1116" stroke="rgba(203,218,225,.14)"/>
    ${line(levels[2], "#b4f2d2", "TARGET")}${line(levels[1], "#8ccfff", "ENTRY")}${line(levels[0], "#ff928b", "STOP")}
  </svg>`;
}

function renderDecision(data, input) {
  const placeholder = document.querySelector("#council-placeholder");
  const output = document.querySelector("#council-output");
  lastDecision = { data, input: { ...input }, snapshot: marketSnapshot ? { ...marketSnapshot } : null };
  updateBotContextStatus();
  placeholder.hidden = true;
  output.hidden = false;
  document.querySelector("#decision-journal-actions").hidden = false;
  document.querySelector("#track-paper-position").hidden = data.action !== "BUY";
  document.querySelector("#decision-journal-feedback").textContent = "";
  const state = data.action.toLowerCase();
  const passed = data.reviews.filter((review) => review.verdict === "PASS").length;
  document.querySelector("#council-decision").innerHTML = `<div class="decision-row"><span class="decision-badge ${state}">${escapeHtml(data.action)} · PAPER</span><span class="decision-summary">${escapeHtml(data.rationale)}</span></div>`;
  document.querySelector("#gate-summary").innerHTML = `<span>${passed} of ${data.reviews.length} gates passed · each gate keeps veto authority</span><span class="gate-track">${data.reviews.map((review) => `<i class="${review.verdict.toLowerCase()}" title="${escapeHtml(review.agent)} · ${escapeHtml(review.verdict)}"></i>`).join("")}</span>`;
  document.querySelector("#plan-metrics").innerHTML = [
    ["SIZE · PAPER UNITS", number(data.plan.quantity, 8)],
    ["REWARD / RISK", `${number(data.plan.reward_risk_ratio)}×`],
    ["EST. LOSS", number(data.plan.estimated_loss)],
    ["TARGET PROFIT", number(data.plan.projected_profit)],
  ].map(([label, value]) => `<div><span>${label}</span><strong>${value}</strong></div>`).join("");
  document.querySelector("#plan-map-wrap").innerHTML = planMap(data.plan, input);
  document.querySelector("#review-list").innerHTML = data.reviews.map((review) => `<li class="${review.verdict.toLowerCase()}"><b>${escapeHtml(review.agent)}</b><span>${escapeHtml(review.verdict)}</span><p>${escapeHtml(review.reason)}</p><p class="review-next-step"><b>Next step</b> · ${escapeHtml(review.next_step || "Refresh the inputs and review this gate again.")}</p></li>`).join("");
  document.querySelector("#council-disclaimer").textContent = `${data.disclaimer} A stop is an estimate; gaps and slippage can increase losses.`;
}

function renderError(message) {
  lastDecision = null;
  document.querySelector("#decision-journal-actions").hidden = true;
  document.querySelector("#council-placeholder").hidden = true;
  document.querySelector("#council-output").hidden = false;
  document.querySelector("#council-decision").innerHTML = `<div class="decision-row"><span class="decision-badge error">CHECK INPUTS</span><span class="decision-summary">${escapeHtml(message)}</span></div>`;
  document.querySelector("#gate-summary").innerHTML = "";
  document.querySelector("#plan-metrics").innerHTML = "";
  document.querySelector("#plan-map-wrap").innerHTML = "";
  document.querySelector("#review-list").innerHTML = "";
  document.querySelector("#council-disclaimer").textContent = "Correct the highlighted levels or market inputs, then run the review again.";
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  lastDecision = null;
  document.querySelector("#decision-journal-actions").hidden = true;
  const values = Object.fromEntries(new FormData(form));
  Object.keys(values).forEach((key) => {
    if (!["side", "trend", "market_open", "setup_name"].includes(key) && values[key] !== "") values[key] = Number(values[key]);
  });
  values.setup_score = values.setup_score === "" ? null : Number(values.setup_score);
  values.market_open = values.market_open === "true";
  runButton.disabled = true;
  runButton.innerHTML = "Council is reviewing… <span aria-hidden=\"true\">⋯</span>";
  try {
    const response = await fetch("/api/trade-council", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(values),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || "Unable to build the paper plan.");
    renderDecision(body, values);
  } catch (error) {
    renderError(error.message);
  } finally {
    runButton.disabled = false;
    runButton.innerHTML = "Run the Defence Council <span aria-hidden=\"true\">↗</span>";
  }
});

function readJournalEntries() {
  try {
    const saved = JSON.parse(localStorage.getItem(JOURNAL_STORAGE_KEY) || "[]");
    return Array.isArray(saved) ? saved.filter((entry) => entry && typeof entry.id === "string") : [];
  } catch {
    return [];
  }
}

function journalAmount(value) {
  return number(Number(value) || 0, 2);
}

function journalTime(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Date unavailable" : date.toLocaleString();
}

function readDailyRiskLimit() {
  try {
    const saved = Number(localStorage.getItem(DAILY_RISK_STORAGE_KEY));
    return Number.isFinite(saved) && saved > 0 && saved <= 100 ? saved : 2;
  } catch {
    return 2;
  }
}

function localDayKey(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return [date.getFullYear(), String(date.getMonth() + 1).padStart(2, "0"), String(date.getDate()).padStart(2, "0")].join("-");
}

function renderDailyRisk(summary) {
  const panel = document.querySelector(".daily-risk-panel");
  const status = document.querySelector("#daily-risk-status");
  const meter = document.querySelector("#daily-risk-meter");
  const validStatus = ["WITHIN_LIMIT", "WATCH", "PAUSE"].includes(summary.status) ? summary.status : "WITHIN_LIMIT";
  const statusClass = validStatus.toLowerCase();
  panel.dataset.riskStatus = validStatus;
  status.textContent = validStatus.replace("_", " ");
  status.className = "daily-risk-status " + statusClass;
  document.querySelector("#daily-risk-limit-amount").textContent = journalAmount(summary.limit_amount);
  const pnl = document.querySelector("#daily-risk-realized");
  pnl.textContent = (Number(summary.realized_pnl) > 0 ? "+" : "") + journalAmount(summary.realized_pnl);
  pnl.className = Number(summary.realized_pnl) > 0 ? "positive" : Number(summary.realized_pnl) < 0 ? "negative" : "";
  document.querySelector("#daily-risk-open").textContent = journalAmount(summary.open_planned_risk);
  const remaining = document.querySelector("#daily-risk-remaining");
  remaining.textContent = journalAmount(summary.remaining_amount);
  remaining.className = statusClass === "pause" ? "pause" : statusClass === "watch" ? "watch" : "safe";
  document.querySelector("#daily-risk-committed").textContent = "Committed: " + journalAmount(summary.committed_loss);
  const utilization = Math.max(0, Number(summary.utilization_percent) || 0);
  meter.className = "daily-risk-meter " + statusClass;
  meter.setAttribute("aria-valuenow", String(Math.min(100, utilization)));
  document.querySelector("#daily-risk-progress").style.width = Math.min(100, utilization) + "%";
  document.querySelector("#daily-risk-utilization").textContent = number(utilization, 1) + "% used";
  document.querySelector("#daily-risk-day").textContent =
    new Date().toLocaleDateString() + " · " + summary.closed_today + " closed exits · " + summary.open_positions + " open paper entries";
}

function showDailyRiskUnavailable(message, className = "unavailable") {
  dailyRiskSummary = null;
  const status = document.querySelector("#daily-risk-status");
  status.textContent = message;
  status.className = "daily-risk-status " + className;
  document.querySelector(".daily-risk-panel").dataset.riskStatus = className.toUpperCase();
  document.querySelector("#daily-risk-day").textContent = className === "loading"
    ? "Updating from today's browser-local journal entries…"
    : "Enter a valid capital amount and daily cap, and make sure the local risk service is available.";
  updateBotContextStatus();
}

async function updateDailyRisk() {
  const requestId = ++dailyRiskRequestId;
  const capital = Number(form.elements.capital.value);
  const lossLimitPercent = Number(dailyRiskLimitInput.value);
  if (!(capital > 0) || !(lossLimitPercent > 0) || lossLimitPercent > 100) {
    showDailyRiskUnavailable("SET CAP & CAPITAL");
    return;
  }

  const today = localDayKey(new Date());
  const closedToday = journalEntries.filter((entry) =>
    entry.status === "closed" &&
    localDayKey(entry.closedAt) === today &&
    Number.isFinite(Number(entry.pnl))
  );
  const open = journalEntries.filter((entry) => entry.status === "open");
  const realizedPnl = closedToday.reduce((sum, entry) => sum + Number(entry.pnl), 0);
  const realizedLoss = closedToday.reduce((sum, entry) => sum + Math.max(0, -Number(entry.pnl)), 0);
  const openPlannedRisk = open.reduce((sum, entry) => {
    const risk = Number(entry.estimatedLoss);
    return sum + (Number.isFinite(risk) && risk > 0 ? risk : 0);
  }, 0);
  showDailyRiskUnavailable("UPDATING", "loading");

  try {
    const response = await fetch("/api/daily-risk", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        capital,
        loss_limit_percent: lossLimitPercent,
        realized_pnl: realizedPnl,
        realized_loss: realizedLoss,
        open_planned_risk: openPlannedRisk,
        closed_today: closedToday.length,
        open_positions: open.length,
      }),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || "Daily risk summary unavailable.");
    if (requestId !== dailyRiskRequestId) return;
    dailyRiskSummary = body;
    renderDailyRisk(body);
    updateBotContextStatus();
  } catch {
    if (requestId === dailyRiskRequestId) showDailyRiskUnavailable("MONITOR UNAVAILABLE");
  }
}

function scheduleDailyRiskUpdate() {
  window.clearTimeout(dailyRiskTimer);
  dailyRiskTimer = window.setTimeout(updateDailyRisk, 180);
}

function scheduleDailyRiskMidnightRefresh() {
  window.clearTimeout(dailyRiskMidnightTimer);
  const nextMidnight = new Date();
  nextMidnight.setHours(24, 0, 1, 0);
  dailyRiskMidnightTimer = window.setTimeout(() => {
    updateDailyRisk();
    scheduleDailyRiskMidnightRefresh();
  }, Math.max(1000, nextMidnight.getTime() - Date.now()));
}

function persistJournal(nextEntries) {
  try {
    localStorage.setItem(JOURNAL_STORAGE_KEY, JSON.stringify(nextEntries));
    journalEntries = nextEntries;
    if (Array.isArray(nextEntries) && nextEntries.length) {
      try { localStorage.setItem("loki_steps_journal", JSON.stringify({ at: Date.now() })); } catch { /* marker is best-effort */ }
    }
    renderJournal();
    updateDailyRisk();
    return true;
  } catch {
    return false;
  }
}

function saveDecisionToJournal(trackPosition) {
  const feedback = document.querySelector("#decision-journal-feedback");
  if (!lastDecision) {
    feedback.textContent = "Run the Defence Council first — there is no decision to save yet.";
    return;
  }
  if (trackPosition && lastDecision.tracked) return;
  if (!trackPosition && lastDecision.reviewSaved) return;

  const { data, input, snapshot } = lastDecision;
  const quantity = Number(data.plan.quantity);
  const estimatedLoss = Number(data.plan.estimated_loss);
  if (trackPosition && (data.action !== "BUY" || !(quantity > 0) || !(estimatedLoss > 0))) {
    feedback.textContent = "This plan cannot be tracked as a paper position because its size or planned risk is invalid.";
    return;
  }
  const setupCandidate = snapshot?.strategy_candidates?.find((candidate) => candidate.name === input.setup_name);

  const record = {
    id: globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    createdAt: new Date().toISOString(),
    status: trackPosition ? "open" : "review",
    symbol: snapshot?.symbol || liveForm.elements.symbol.value.trim().toUpperCase() || "UNKNOWN",
    interval: snapshot?.interval || liveForm.elements.interval.value,
    setupName: input.setup_name || "Unselected setup",
    setupScore: Number(input.setup_score) || 0,
    action: data.action,
    rationale: data.rationale,
    passedGates: (data.reviews || []).filter((review) => review.verdict === "PASS").length,
    gateCount: (data.reviews || []).length,
    councilReviews: (data.reviews || []).map((review) => ({ agent: String(review.agent), verdict: String(review.verdict), reason: String(review.reason), next_step: String(review.next_step || "") })),
    setupEvidence: (setupCandidate?.evidence || []).map(String),
    entryPrice: Number(input.entry_price),
    stopPrice: Number(input.stop_price),
    targetPrice: Number(input.target_price),
    quantity,
    estimatedLoss,
    projectedProfit: Number(data.plan.projected_profit),
    note: document.querySelector("#council-note").value.trim(),
  };
  const nextEntries = [record, ...journalEntries].slice(0, 250);
  if (!persistJournal(nextEntries)) {
    feedback.textContent = "Could not save to this browser. Check available local storage and try again.";
    return;
  }

  if (trackPosition) {
    lastDecision.tracked = true;
    document.querySelector("#track-paper-position").disabled = true;
    document.querySelector("#track-paper-position").textContent = "Paper entry tracked";
    feedback.textContent = "Added to the local journal as an open paper entry. No order was sent.";
  } else {
    lastDecision.reviewSaved = true;
    document.querySelector("#save-review").disabled = true;
    document.querySelector("#save-review").textContent = "Review saved";
    feedback.textContent = "Council review saved to this browser.";
  }
}

function setupReviewRows() {
  const closed = journalEntries.filter((entry) => entry.status === "closed" && Number.isFinite(Number(entry.pnl)));
  const groups = new Map();
  closed.forEach((entry) => {
    const name = entry.setupName || "Unselected setup";
    const stats = groups.get(name) || { count: 0, wins: 0, totalR: 0, pnl: 0 };
    stats.count += 1;
    stats.wins += Number(entry.pnl) > 0 ? 1 : 0;
    stats.totalR += Number(entry.rMultiple) || 0;
    stats.pnl += Number(entry.pnl) || 0;
    groups.set(name, stats);
  });
  return [...groups.entries()].sort(([left], [right]) => left.localeCompare(right));
}


function updateBotContextStatus() {
  const status = document.querySelector("#bot-context-status");
  if (!status) return;
  const parts = [];
  if (marketSnapshot) parts.push(marketSnapshot.symbol + " " + marketSnapshot.interval + " snapshot");
  if (lastDecision) parts.push(lastDecision.data.action + " council review");
  parts.push(journalEntries.filter((entry) => entry.status === "closed").length + " closed journal outcomes");
  if (dailyRiskSummary) parts.push("daily risk " + dailyRiskSummary.status.replace("_", " ").toLowerCase());
  status.textContent = "Each message can use: " + parts.join(" · ") + ". Journal data stays in this browser.";
}

function botContextPayload() {
  const closed = journalEntries.filter((entry) => entry.status === "closed" && Number.isFinite(Number(entry.pnl)));
  const wins = closed.filter((entry) => Number(entry.pnl) > 0).length;
  const averageR = closed.length
    ? closed.reduce((sum, entry) => sum + (Number(entry.rMultiple) || 0), 0) / closed.length
    : null;
  return {
    market: marketSnapshot ? {
      symbol: marketSnapshot.symbol,
      interval: marketSnapshot.interval,
      current_price: marketSnapshot.current_price,
      change_24h_percent: marketSnapshot.change_24h_percent,
      trend: marketSnapshot.trend,
      rsi_14: marketSnapshot.rsi_14,
      volume_ratio: marketSnapshot.volume_ratio,
      spread_percent: marketSnapshot.spread_percent,
      data_age_seconds: marketSnapshot.data_age_seconds,
    } : null,
    decision: lastDecision ? {
      action: lastDecision.data.action,
      rationale: lastDecision.data.rationale,
      setup_name: lastDecision.input.setup_name,
      setup_score: lastDecision.input.setup_score,
      reviews: lastDecision.data.reviews,
      plan: lastDecision.data.plan,
    } : null,
    journal: {
      closed_trades: closed.length,
      wins: wins,
      win_rate_percent: closed.length ? wins / closed.length * 100 : null,
      average_r: averageR,
      pnl: closed.reduce((sum, entry) => sum + (Number(entry.pnl) || 0), 0),
      setups: setupReviewRows().map(([name, stats]) => ({
        name: name,
        closed: stats.count,
        wins: stats.wins,
        win_rate_percent: stats.count ? stats.wins / stats.count * 100 : null,
        average_r: stats.count ? stats.totalR / stats.count : null,
        pnl: stats.pnl,
      })),
    },
    daily_risk: dailyRiskSummary ? {
      status: dailyRiskSummary.status,
      limit_amount: dailyRiskSummary.limit_amount,
      realized_pnl: dailyRiskSummary.realized_pnl,
      realized_loss: dailyRiskSummary.realized_loss,
      open_planned_risk: dailyRiskSummary.open_planned_risk,
      committed_loss: dailyRiskSummary.committed_loss,
      remaining_amount: dailyRiskSummary.remaining_amount,
      utilization_percent: dailyRiskSummary.utilization_percent,
      closed_today: dailyRiskSummary.closed_today,
      open_positions: dailyRiskSummary.open_positions,
    } : null,
  };
}

function appendBotMessage(role, content) {
  const article = document.createElement("article");
  article.className = "bot-message " + role;
  const label = document.createElement("span");
  label.className = "bot-message-label";
  label.textContent = role === "user" ? "YOU" : "LOKI COACH";
  const paragraph = document.createElement("p");
  paragraph.textContent = content;
  article.append(label, paragraph);
  botChatLog.append(article);
  botChatLog.scrollTop = botChatLog.scrollHeight;
}

botChatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = botQuestion.value.trim();
  if (!question || botSend.disabled) return;
  appendBotMessage("user", question);
  botQuestion.value = "";
  botSend.disabled = true;
  botSend.innerHTML = "Thinking… <span aria-hidden=\"true\">⋯</span>";
  botChatStatus.textContent = "Reading the market, council and journal context attached to this message…";
  try {
    const response = await fetch("/api/bot-chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: question, ...botContextPayload() }),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || "The coach could not answer that question.");
    appendBotMessage("assistant", body.answer);
    botChatStatus.textContent = "Answered from the context on this page. No order was sent.";
  } catch (error) {
    appendBotMessage("assistant", error.message || "The coach is unavailable. Please try again.");
    botChatStatus.textContent = "Question was not answered; check the connection and try again.";
  } finally {
    botSend.disabled = false;
    botSend.innerHTML = "Ask Loki <span aria-hidden=\"true\">↑</span>";
    botQuestion.focus();
  }
});

document.querySelectorAll("[data-bot-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    botQuestion.value = button.dataset.botPrompt;
    botChatForm.requestSubmit();
  });
});

botQuestion.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    botChatForm.requestSubmit();
  }
});

function renderJournal() {
  const closed = journalEntries.filter((entry) => entry.status === "closed");
  const open = journalEntries.filter((entry) => entry.status === "open");
  const winners = closed.filter((entry) => Number(entry.pnl) > 0).length;
  const pnlTotal = closed.reduce((sum, entry) => sum + (Number(entry.pnl) || 0), 0);
  const averageR = closed.length ? closed.reduce((sum, entry) => sum + (Number(entry.rMultiple) || 0), 0) / closed.length : null;

  document.querySelector("#journal-open-count").textContent = String(open.length);
  document.querySelector("#journal-closed-count").textContent = String(closed.length);
  document.querySelector("#journal-win-rate").textContent = closed.length ? `${number(winners / closed.length * 100, 1)}%` : "—";
  document.querySelector("#journal-average-r").textContent = averageR === null ? "—" : `${averageR > 0 ? "+" : ""}${number(averageR)}R`;
  const pnlValue = document.querySelector("#journal-pnl");
  pnlValue.textContent = closed.length ? journalAmount(pnlTotal) : "—";
  pnlValue.className = pnlTotal > 0 ? "positive" : pnlTotal < 0 ? "negative" : "";

  const playbookRows = setupReviewRows();
  updateBotContextStatus();
  document.querySelector("#playbook-review-empty").hidden = playbookRows.length > 0;
  document.querySelector("#playbook-review-body").innerHTML = playbookRows.map(([name, stats]) => {
    let sample;
    if (stats.count < 5) sample = { label: "Too small", className: "sample-small", note: "Fewer than 5 closed outcomes; do not use this sample to change rules." };
    else if (stats.count < 20) sample = { label: "Early read", className: "sample-early", note: "5–19 outcomes; continue logging before treating this as repeatable." };
    else sample = { label: "Reviewable", className: "sample-reviewable", note: "20+ outcomes; review with holdout and costs, not as proof of future edge." };
    return "<tr><td>" + escapeHtml(name) + "</td><td>" + stats.count + "</td><td>" + number(stats.wins / stats.count * 100, 1) + "%</td><td>" + (stats.totalR > 0 ? "+" : "") + number(stats.totalR / stats.count) + "R</td><td class=\"" + (stats.pnl > 0 ? "positive" : stats.pnl < 0 ? "negative" : "") + "\">" + journalAmount(stats.pnl) + "</td><td><span class=\"sample-read " + sample.className + "\" title=\"" + sample.note + "\">" + sample.label + "</span></td></tr>";
  }).join("");

  const filter = document.querySelector("#journal-filter").value;
  const visible = filter === "all" ? journalEntries : journalEntries.filter((entry) => entry.status === filter);
  document.querySelector("#journal-entry-count").textContent = `${visible.length} shown · ${journalEntries.length} total`;
  const empty = document.querySelector("#journal-empty");
  empty.hidden = visible.length > 0;
  empty.innerHTML = journalEntries.length === 0
    ? "<strong>Your learning loop starts with a record.</strong><span>Save a council review or track a BUY as a paper entry. Later, record its exit and compare setups.</span>"
    : "<strong>No entries match this filter.</strong><span>Choose another journal view to see your saved reviews and paper outcomes.</span>";
  document.querySelector("#export-journal").disabled = journalEntries.length === 0;
  document.querySelector("#clear-journal").disabled = journalEntries.length === 0;
  document.querySelector("#journal-list").innerHTML = visible.map((entry) => {
    const stateLabel = entry.status === "open" ? "OPEN PAPER POSITION" : entry.status === "closed" ? "CLOSED PAPER POSITION" : "COUNCIL REVIEW";
    const outcome = entry.status === "open"
      ? `<div class="paper-close-controls"><label>Manual exit price<input type="number" min="0.000001" step="any" data-exit-price value="" aria-label="Manual exit price for ${escapeHtml(entry.symbol)}" /></label><button class="secondary-button" type="button" data-close-paper>Mark paper position closed</button><span class="close-feedback" role="status"></span></div>`
      : entry.status === "closed"
        ? `<div class="journal-outcome"><strong class="${Number(entry.pnl) > 0 ? "positive" : Number(entry.pnl) < 0 ? "negative" : ""}">${journalAmount(entry.pnl)} quote units gross · ${Number(entry.rMultiple) > 0 ? "+" : ""}${number(entry.rMultiple)}R</strong><span>Manual exit ${price(entry.exitPrice)} · ${escapeHtml(journalTime(entry.closedAt))}</span></div>`
        : `<p class="review-only-note">Saved decision review · no simulated position was tracked</p>`;
    const note = entry.note ? `<p class="journal-note">${escapeHtml(entry.note)}</p>` : "";
    const setupDetails = (entry.setupEvidence || []).length ? `<details class="journal-details"><summary>Setup checklist · ${entry.setupEvidence.length} conditions</summary><ul class="focus-evidence">${entry.setupEvidence.map((item) => `<li class="${String(item).startsWith("PASS") ? "matched" : "missed"}">${escapeHtml(item)}</li>`).join("")}</ul></details>` : "";
    const councilDetails = (entry.councilReviews || []).length ? `<details class="journal-details"><summary>Council review · ${entry.councilReviews.length} gates</summary><ol class="review-list">${entry.councilReviews.map((review) => `<li class="${escapeHtml(String(review.verdict).toLowerCase())}"><b>${escapeHtml(review.agent)}</b><span>${escapeHtml(review.verdict)}</span><p>${escapeHtml(review.reason)}</p><p class="review-next-step"><b>Next step</b> · ${escapeHtml(review.next_step || "Review the flagged input.")}</p></li>`).join("")}</ol></details>` : "";
    return `<article class="journal-entry-card" data-journal-id="${escapeHtml(entry.id)}">
      <div class="journal-entry-head"><div><span class="journal-status ${entry.status}">${stateLabel}</span><h3>${escapeHtml(entry.symbol)} <small>${escapeHtml(entry.interval)}</small></h3></div><time>${escapeHtml(journalTime(entry.createdAt))}</time></div>
      <div class="journal-entry-summary"><div><span>SETUP</span><strong>${escapeHtml(entry.setupName)}</strong></div><div><span>RULES MATCHED</span><strong>${number(entry.setupScore, 0)} / 100</strong></div><div><span>COUNCIL</span><strong>${escapeHtml(entry.action)} · ${entry.passedGates} / ${entry.gateCount} passed</strong></div><div><span>ENTRY / SIZE</span><strong>${price(entry.entryPrice)} · ${number(entry.quantity, 8)}</strong></div></div>
      <p class="journal-rationale">${escapeHtml(entry.rationale || "No council rationale recorded.")}</p>
      ${note}${setupDetails}${councilDetails}${outcome}
    </article>`;
  }).join("");
}

function closePaperPosition(button) {
  const card = button.closest(".journal-entry-card");
  const entry = journalEntries.find((item) => item.id === card?.dataset.journalId && item.status === "open");
  const feedback = card?.querySelector(".close-feedback");
  const exitPrice = Number(card?.querySelector("[data-exit-price]")?.value);
  if (!entry || !(exitPrice > 0) || !Number.isFinite(exitPrice)) {
    if (feedback) feedback.textContent = "Enter a valid manual exit price.";
    return;
  }
  if (!(Number(entry.estimatedLoss) > 0) || !(Number(entry.quantity) > 0)) {
    if (feedback) feedback.textContent = "This entry has no usable planned risk or size and cannot be measured.";
    return;
  }
  const pnl = Number(entry.quantity) * (exitPrice - Number(entry.entryPrice));
  const nextEntries = journalEntries.map((item) => item.id === entry.id ? {
    ...item,
    status: "closed",
    exitPrice,
    closedAt: new Date().toISOString(),
    pnl,
    rMultiple: pnl / Number(entry.estimatedLoss),
  } : item);
  if (!persistJournal(nextEntries) && feedback) feedback.textContent = "Could not update local storage. Check available space and try again.";
}

function exportJournalCsv() {
  const fields = ["createdAt", "closedAt", "symbol", "interval", "setupName", "setupScore", "action", "status", "entryPrice", "stopPrice", "targetPrice", "quantity", "estimatedLoss", "exitPrice", "pnl", "rMultiple", "passedGates", "gateCount", "rationale", "note"];
  const cell = (value) => {
    let text = String(value ?? "");
    if (/^\s*[=+@-]/.test(text)) text = `'${text}`;
    return `"${text.replaceAll('"', '""')}"`;
  };
  const csv = [fields, ...journalEntries.map((entry) => fields.map((field) => entry[field]))].map((row) => row.map(cell).join(",")).join("\r\n");
  const url = URL.createObjectURL(new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `loki-paper-journal-${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

document.querySelector("#save-review").addEventListener("click", () => saveDecisionToJournal(false));
document.querySelector("#track-paper-position").addEventListener("click", () => saveDecisionToJournal(true));
document.querySelector("#journal-filter").addEventListener("change", renderJournal);
document.querySelector("#journal-list").addEventListener("click", (event) => {
  const button = event.target.closest("[data-close-paper]");
  if (button) closePaperPosition(button);
});
document.querySelector("#export-journal").addEventListener("click", exportJournalCsv);
document.querySelector("#clear-journal").addEventListener("click", () => {
  if (journalEntries.length && window.confirm("Clear all paper journal entries saved in this browser?")) {
    if (!persistJournal([])) window.alert("Could not clear the local journal. Check browser storage permissions.");
  }
});
window.addEventListener("storage", (event) => {
  if (event.key === JOURNAL_STORAGE_KEY) {
    journalEntries = readJournalEntries();
    renderJournal();
    updateDailyRisk();
  } else if (event.key === DAILY_RISK_STORAGE_KEY) {
    dailyRiskLimitInput.value = String(readDailyRiskLimit());
    updateDailyRisk();
  }
});
dailyRiskLimitInput.value = String(readDailyRiskLimit());
dailyRiskLimitInput.addEventListener("input", () => {
  const value = Number(dailyRiskLimitInput.value);
  if (Number.isFinite(value) && value > 0 && value <= 100) {
    try { localStorage.setItem(DAILY_RISK_STORAGE_KEY, String(value)); } catch { /* Keep the setting for this page session. */ }
  }
  scheduleDailyRiskUpdate();
});
form.elements.capital.addEventListener("input", scheduleDailyRiskUpdate);
renderJournal();
updateDailyRisk();
scheduleDailyRiskMidnightRefresh();

