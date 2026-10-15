const form = document.querySelector("#trade-council-form");
const liveForm = document.querySelector("#live-feed-form");
const liveStatus = document.querySelector("#live-feed-status");
const runButton = document.querySelector("#run-council");
const chart = document.querySelector("#market-chart");
const chartEmpty = document.querySelector("#chart-empty");
const strategyBoard = document.querySelector("#strategy-board");
const strategyEmpty = document.querySelector("#strategy-empty");
let marketSnapshot = null;
let selectedStrategyKey = "";

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
  placeholder.hidden = true;
  output.hidden = false;
  const state = data.action.toLowerCase();
  const passed = data.reviews.filter((review) => review.verdict === "PASS").length;
  document.querySelector("#council-decision").innerHTML = `<div class="decision-row"><span class="decision-badge ${state}">${escapeHtml(data.action)} · PAPER</span><span class="decision-summary">${escapeHtml(data.rationale)}</span></div>`;
  document.querySelector("#gate-summary").innerHTML = `<span>${passed} of ${data.reviews.length} gates passed · each gate keeps veto authority</span><span class="gate-track">${data.reviews.map((review) => `<i class="${review.verdict.toLowerCase()}" title="${escapeHtml(review.agent)} · ${escapeHtml(review.verdict)}"></i>`).join("")}</span>`;
  document.querySelector("#plan-metrics").innerHTML = [
    ["SIZE", number(data.plan.quantity, 0)],
    ["REWARD / RISK", `${number(data.plan.reward_risk_ratio)}×`],
    ["EST. LOSS", number(data.plan.estimated_loss)],
    ["TARGET PROFIT", number(data.plan.projected_profit)],
  ].map(([label, value]) => `<div><span>${label}</span><strong>${value}</strong></div>`).join("");
  document.querySelector("#plan-map-wrap").innerHTML = planMap(data.plan, input);
  document.querySelector("#review-list").innerHTML = data.reviews.map((review) => `<li class="${review.verdict.toLowerCase()}"><b>${escapeHtml(review.agent)}</b><span>${escapeHtml(review.verdict)}</span><p>${escapeHtml(review.reason)}</p></li>`).join("");
  document.querySelector("#council-disclaimer").textContent = `${data.disclaimer} A stop is an estimate; gaps and slippage can increase losses.`;
}

function renderError(message) {
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

