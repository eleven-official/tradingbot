(() => {
  "use strict";
  const LAB = window.LokiLab;
  const $ = (id) => document.getElementById(id);
  const JOURNAL_KEY = "loki-paper-journal-v1";
  let bars = LAB.makeScenario("mixed");
  let dataSource = "synthetic demo";
  let dataName = "Mixed regimes · demo";
  let evaluation = null;
  let latestPaper = null;

  const money = (value, digits = 2) => new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
  const percent = (value) => `${value >= 0 ? "+" : "−"}${Math.abs(value * 100).toFixed(2)}%`;
  const dateLabel = (value) => {
    const parsed = new Date(`${value}T00:00:00Z`);
    return Number.isNaN(parsed.valueOf()) ? value : new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }).format(parsed);
  };
  const setText = (id, value) => { const element = $(id); if (element) element.textContent = value; };

  function profile() {
    try { return JSON.parse(localStorage.getItem("zack-profile-v1") || "null"); } catch (_) { return null; }
  }

  function updateProfile() {
    const saved = profile();
    if (!saved || !saved.nickname) return;
    const name = saved.nickname.trim();
    const initial = [...name][0]?.toUpperCase() || "L";
    setText("sidebarNickname", name);
    setText("topNickname", name);
    setText("profileAvatar", initial);
    setText("topAvatar", initial);
    setText("welcomeGreeting", `Good to have you here, ${name}. Ready to research?`);
    setText("overviewTitle", `Stay curious, ${name}.`);
  }

  function openWorkspace() {
    if (!profile()) return;
    $("profileWall").hidden = true;
    $("workspaceApp").hidden = false;
    updateProfile();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function editProfile() {
    $("workspaceApp").hidden = true;
    $("profileWall").hidden = false;
    $("profileEdit").click();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function goTo(view) {
    const pages = ["overview", "strategy", "paper", "journal", "council"];
    if (!pages.includes(view)) return;
    document.querySelectorAll(".view").forEach((element) => element.classList.toggle("active", element.id === `view-${view}`));
    document.querySelectorAll("[data-view]").forEach((element) => element.classList.toggle("active", element.dataset.view === view));
    setText("pageCrumb", view.replace("-", " ").toUpperCase());
    if (view === "journal") renderJournal();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function costOptions() {
    const feeBps = Number($("feeBps").value);
    const spreadBps = Number($("spreadBps").value);
    const slippageBps = Number($("slippageBps").value);
    const values = { feeBps, spreadBps, slippageBps, splitPercent: Number($("splitPercent").value), source: dataSource };
    return values;
  }

  function updateCostSummary() {
    const inputs = [$("feeBps"), $("spreadBps"), $("slippageBps")];
    const values = inputs.map((input) => Number(input.value));
    if (values.some((value) => !Number.isFinite(value) || value < 0)) {
      setText("roundTripCost", "Check inputs");
      return;
    }
    setText("roundTripCost", `${((values[0] + values[1] + values[2]) * 2).toFixed(1)} bps`);
  }

  function showDataSource() {
    setText("datasetTitle", dataName);
    const demo = dataSource === "synthetic demo";
    const tag = $("dataSourceTag");
    tag.textContent = demo ? "SYNTHETIC DEMO" : "USER CSV · LOCAL";
    tag.classList.toggle("uploaded", !demo);
    setText("datasetDescription", demo ? "Deterministic synthetic prices for interface and logic checks. Not real market history." : `${bars.length.toLocaleString()} uploaded OHLC bars · kept in this browser session only.`);
    setText("dataStatus", demo ? "Demo data is locally generated and is not live market data." : `${dataName} loaded into memory for this session. File is not uploaded or saved.`);
  }

  function chooseScenario(name) {
    try {
      bars = LAB.makeScenario(name);
      dataSource = "synthetic demo";
      dataName = `${name[0].toUpperCase()}${name.slice(1)} regimes · demo`;
      evaluation = null;
      document.querySelectorAll(".scenarioButton").forEach((button) => button.classList.toggle("active", button.dataset.scenario === name));
      showDataSource();
      clearResultView();
    } catch (error) { setText("dataStatus", error.message); }
  }

  function handleCsv(file) {
    if (!file) return;
    const reader = new FileReader();
    setText("dataStatus", `Reading ${file.name} locally…`);
    reader.onload = () => {
      try {
        bars = LAB.parseCsv(String(reader.result || ""));
        dataSource = "uploaded CSV";
        dataName = file.name;
        evaluation = null;
        document.querySelectorAll(".scenarioButton").forEach((button) => button.classList.remove("active"));
        showDataSource();
        clearResultView();
      } catch (error) {
        setText("dataStatus", error.message || "Could not read this CSV. Check the format and try again.");
      }
    };
    reader.onerror = () => setText("dataStatus", "The CSV could not be read. Try another file.");
    reader.readAsText(file);
  }

  function clearResultView() {
    evaluation = null;
    $("resultsPanel").hidden = true;
    $("equityChart").replaceChildren();
    const empty = document.createElement("div");
    empty.className = "chartEmpty";
    empty.innerHTML = "<span>↗</span><b>Your first replay starts here</b><small>Choose a market scenario or upload historical OHLC data.</small>";
    $("equityChart").append(empty);
    setText("chartStart", "WAITING FOR A REPLAY");
    setText("chartEnd", "");
    setText("metricReturn", "—");
    setText("metricDrawdown", "—");
    setText("metricTrades", "—");
    setText("metricCosts", "—");
    setText("metricReturnNote", "Run a replay to calculate");
    setText("metricWinRate", "No test-period trades yet");
    updateCouncil(null);
    showDataSource();
  }

  function drawChart(result) {
    const chart = $("equityChart");
    chart.replaceChildren();
    const width = 800;
    const height = 170;
    const points = result.holdout.equityCurve.map((point) => point.equity);
    const baseStart = result.holdout.startingEquity;
    const baseEnd = baseStart * (1 + result.holdout.benchmark.returnPct);
    const all = points.concat(points.map((_, i) => baseStart + (baseEnd - baseStart) * i / Math.max(1, points.length - 1)));
    const low = Math.min(...all);
    const high = Math.max(...all);
    const range = Math.max(1, high - low);
    const x = (i, count) => i / Math.max(1, count - 1) * width;
    const y = (value) => height - 12 - (value - low) / range * (height - 24);
    const pathFor = (values) => values.map((value, i) => `${i ? "L" : "M"}${x(i, values.length).toFixed(1)},${y(value).toFixed(1)}`).join(" ");
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.setAttribute("preserveAspectRatio", "none");
    svg.setAttribute("class", "equitySvg");
    const base = document.createElementNS(ns, "path");
    base.setAttribute("class", "baselineLine");
    base.setAttribute("d", pathFor(points.map((_, i) => baseStart + (baseEnd - baseStart) * i / Math.max(1, points.length - 1))));
    const strat = document.createElementNS(ns, "path");
    strat.setAttribute("class", "strategyLine");
    strat.setAttribute("d", pathFor(points));
    const area = document.createElementNS(ns, "path");
    area.setAttribute("class", "strategyArea");
    area.setAttribute("d", `${pathFor(points)} L${width},${height} L0,${height} Z`);
    svg.append(area, base, strat);
    chart.append(svg);
    setText("chartStart", dateLabel(result.splitDate));
    setText("chartEnd", dateLabel(result.endDate));
  }

  function updateOverview(result) {
    const holdout = result.holdout;
    const returnEl = $("metricReturn");
    returnEl.textContent = percent(holdout.returnPct);
    returnEl.classList.toggle("positive", holdout.returnPct > 0);
    returnEl.classList.toggle("negative", holdout.returnPct < 0);
    setText("metricDrawdown", percent(-holdout.maxDrawdown));
    setText("metricTrades", String(holdout.tradeCount));
    setText("metricWinRate", holdout.tradeCount ? `${(holdout.winRate * 100).toFixed(1)}% profitable trades` : "No trades in untouched period");
    setText("metricCosts", money(holdout.totalCosts));
    setText("metricReturnNote", `Buy & hold: ${percent(holdout.benchmark.returnPct)} · after costs`);
    setText("strategyStatus", `Frozen rules · ${holdout.tradeCount} test trades`);
    $("resultsPanel").hidden = false;
    setText("resultReturn", percent(holdout.returnPct));
    setText("resultBaseline", percent(holdout.benchmark.returnPct));
    setText("resultExpectancy", holdout.tradeCount ? money(holdout.expectancy) : "No trades");
    setText("resultDrawdown", percent(-holdout.maxDrawdown));
    setText("resultWinRate", holdout.tradeCount ? `${(holdout.winRate * 100).toFixed(1)}%` : "—");
    setText("resultTrades", String(holdout.tradeCount));
    const returnWord = holdout.returnPct > holdout.benchmark.returnPct ? "above" : holdout.returnPct < holdout.benchmark.returnPct ? "below" : "in line with";
    const sourceNote = dataSource === "synthetic demo" ? "This is synthetic scenario data, not evidence of market profitability." : "One uploaded historical series is still not proof of future profitability.";
    const sampleNote = holdout.tradeCount < 10 ? " The holdout trade count is small, so the estimate is especially uncertain." : "";
    setText("resultMessage", `After modeled costs, the strategy returned ${percent(holdout.returnPct)} versus ${percent(holdout.benchmark.returnPct)} for matched-allocation buy and hold (${returnWord} baseline). Training: ${percent(result.training.returnPct)} across ${result.training.tradeCount} trades. ${sourceNote}${sampleNote}`);
    drawChart(result);
  }

  function runReplay() {
    updateCostSummary();
    try {
      const started = performance.now();
      evaluation = LAB.evaluate(bars, costOptions());
      updateOverview(evaluation);
      updateCouncil(evaluation);
      setText("runStatus", `Replay complete · ${bars.length} bars · ${Math.round(performance.now() - started)} ms`);
      goTo("strategy");
    } catch (error) {
      setText("runStatus", error.message || "Replay failed. Check the inputs and try again.");
    }
  }

  function readJournal() {
    try {
      const value = JSON.parse(localStorage.getItem(JOURNAL_KEY) || "[]");
      return Array.isArray(value) ? value.slice(-1000) : [];
    } catch (_) { return []; }
  }

  function saveJournal(items) {
    try { localStorage.setItem(JOURNAL_KEY, JSON.stringify(items.slice(-1000))); return true; }
    catch (_) { setText("journalSource", "Browser storage is full; journal could not be saved."); return false; }
  }

  function runPaper() {
    try {
      evaluation = LAB.evaluate(bars, costOptions());
      const holdout = evaluation.holdout;
      const runId = `${Date.now()}-${Math.floor(Math.random() * 100000)}`;
      const rows = holdout.trades.map((trade) => ({ ...trade, runId, runAt: new Date().toISOString(), source: dataSource, dataset: dataName }));
      const next = readJournal().concat(rows);
      if (!saveJournal(next)) return;
      latestPaper = { equity: holdout.finalEquity, pnl: holdout.totalNetPnl, count: rows.length, source: dataName, at: new Date().toISOString() };
      try { localStorage.setItem("loki-paper-state-v1", JSON.stringify(latestPaper)); } catch (_) { /* Journal is the primary record. */ }
      updatePaper(latestPaper);
      updateOverview(evaluation);
      updateCouncil(evaluation);
      setText("journalSource", `${dataName} · ${dateLabel(evaluation.splitDate)} to ${dateLabel(evaluation.endDate)}`);
      goTo("journal");
    } catch (error) { setText("journalSource", error.message || "Paper replay could not run."); }
  }

  function updatePaper(state) {
    if (!state) return;
    setText("paperEquity", money(state.equity));
    setText("paperPnl", money(state.pnl));
    $("paperPnl").classList.toggle("positive", state.pnl > 0);
    $("paperPnl").classList.toggle("negative", state.pnl < 0);
    setText("paperTrades", String(state.count));
  }

  function renderJournal() {
    const rows = readJournal();
    const body = $("journalBody");
    body.replaceChildren();
    if (!rows.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 6;
      td.className = "emptyTable";
      td.textContent = "No paper trades yet. Run a replay to create your first journal entry.";
      tr.append(td);
      body.append(tr);
    }
    for (const trade of [...rows].reverse()) {
      const tr = document.createElement("tr");
      const dates = document.createElement("td");
      dates.textContent = `${dateLabel(trade.entryDate)} → ${dateLabel(trade.exitDate)}`;
      const side = document.createElement("td");
      const pill = document.createElement("span"); pill.className = "sidePill"; pill.textContent = "LONG"; side.append(pill);
      const prices = document.createElement("td");
      prices.textContent = `${money(trade.entryPrice, 3)} → ${money(trade.exitPrice, 3)}`;
      const reason = document.createElement("td"); reason.textContent = trade.exitReason;
      const costs = document.createElement("td"); costs.textContent = money(trade.costs);
      const pnl = document.createElement("td"); pnl.textContent = money(trade.netPnl); pnl.className = trade.netPnl > 0 ? "pnlPositive" : trade.netPnl < 0 ? "pnlNegative" : "";
      tr.append(dates, side, prices, reason, costs, pnl);
      body.append(tr);
    }
    const net = rows.reduce((sum, row) => sum + Number(row.netPnl || 0), 0);
    const costs = rows.reduce((sum, row) => sum + Number(row.costs || 0), 0);
    setText("journalCount", String(rows.length));
    setText("journalExpectancy", rows.length ? money(net / rows.length) : "—");
    setText("journalCosts", money(costs));
    if (rows.length) {
      const latest = rows[rows.length - 1];
      setText("journalSource", `${latest.dataset} · ${dateLabel(latest.runAt.slice(0, 10))}`);
    }
  }

  function updateCouncil(result) {
    const regime = LAB.describeRegime(bars);
    setText("councilTape", `${bars.length} bars from ${dateLabel(bars[0].date)} to ${dateLabel(bars[bars.length - 1].date)}. The series is ${regime.label}, changing ${percent(regime.change)} overall, with approximately ${(regime.annualizedVolatility * 100).toFixed(1)}% annualized daily-return volatility. Source: ${dataSource}.`);
    if (!result) {
      setText("councilRisk", "No replay results yet. Once run, the watcher checks holdout drawdown, trade count and whether modeled costs overwhelm gross trade results.");
      setText("councilSkeptic", dataSource === "synthetic demo" ? "The current path is generated data. Its results test the software and rules, not real market profitability." : "A single historical series is a narrow sample. Confirm data quality, costs and performance across rising, falling and sideways holdout periods.");
      setText("councilChair", "The chair waits for a full replay, notes disagreement, and recommends the next evidence check. No broker orders or live-market decisions are made here.");
      setText("chairVerdict", "Not enough evidence yet");
      setText("chairNext", "Run the replay, then compare holdout expectancy, drawdown, costs, trade count and baseline.");
      return;
    }
    const h = result.holdout;
    const gross = h.totalNetPnl + h.totalCosts;
    setText("councilRisk", `${h.tradeCount} holdout trades. Peak-to-trough drawdown was ${percent(-h.maxDrawdown)} after costs. The model charged ${money(h.totalCosts)}; estimated pre-cost trade P&L was ${money(gross)}.`);
    setText("councilSkeptic", dataSource === "synthetic demo" ? `The chosen ${regime.label} path is synthetic. The holdout has ${h.tradeCount} trades; costs and random seed are fixed. This is not external market evidence.` : `The held-out segment contains ${h.tradeCount} trades. Verify timestamp, split and market coverage; one symbol and sample cannot establish robustness.`);
    const compare = h.returnPct > h.benchmark.returnPct ? "above" : h.returnPct < h.benchmark.returnPct ? "below" : "equal to";
    setText("councilChair", `The frozen strategy came in ${compare} the matched-allocation baseline on this holdout (${percent(h.returnPct)} versus ${percent(h.benchmark.returnPct)}). That result is a clue for further checking, not a reason to deploy.`);
    setText("chairVerdict", h.tradeCount < 10 ? "Hold: sample is too thin" : "Keep the rules frozen");
    setText("chairNext", `Next: repeat on longer real OHLC history across rising, falling and sideways periods; retain an untouched later test and paper-log the frozen version.`);
  }

  document.querySelectorAll("[data-view]").forEach((button) => button.addEventListener("click", () => goTo(button.dataset.view)));
  document.querySelectorAll("[data-go]").forEach((button) => button.addEventListener("click", () => goTo(button.dataset.go)));
  document.querySelectorAll(".scenarioButton").forEach((button) => button.addEventListener("click", () => chooseScenario(button.dataset.scenario)));
  $("csvUpload").addEventListener("change", (event) => handleCsv(event.target.files?.[0]));
  [$("feeBps"), $("spreadBps"), $("slippageBps")].forEach((input) => input.addEventListener("input", updateCostSummary));
  $("runBacktest").addEventListener("click", runReplay);
  $("runPaper").addEventListener("click", runPaper);
  $("workspaceOpen").addEventListener("click", openWorkspace);
  $("profileSettings").addEventListener("click", editProfile);
  $("switchProfile").addEventListener("click", editProfile);
  $("clearJournal").addEventListener("click", () => {
    try { localStorage.removeItem(JOURNAL_KEY); localStorage.removeItem("loki-paper-state-v1"); latestPaper = null; setText("paperEquity", "$10,000"); setText("paperPnl", "$0.00"); setText("paperTrades", "0"); renderJournal(); }
    catch (_) { setText("journalSource", "Browser storage could not be cleared. Try again."); }
  });
  window.addEventListener("loki:profile", updateProfile);
  updateCostSummary();
  showDataSource();
  renderJournal();
  try {
    latestPaper = JSON.parse(localStorage.getItem("loki-paper-state-v1") || "null");
    updatePaper(latestPaper);
  } catch (_) { latestPaper = null; }
  if (profile()) {
    const saved = profile();
    setText("welcomeTitle", `Welcome back, ${saved.nickname}.`);
  }
})();

