(() => {
  "use strict";

  const RULE_VERSION = "1.1";
  const AGENT_VERSION = "0.2";
  const MIN_AGENT_TRAINING_TRADES = 5;
  const STRATEGIES = Object.freeze([
    Object.freeze({ id: "trend-50-100", name: "Trend continuation · 50/100", entry: "Close above SMA100 and SMA50 above SMA100.", exit: "Close below SMA50 or 5% close-based stop." }),
    Object.freeze({ id: "breakout-20", name: "Trend-filtered 20-bar breakout", entry: "Close breaks above the prior 20-bar high while SMA50 is above SMA100.", exit: "Close below SMA20 or 5% close-based stop." }),
    Object.freeze({ id: "pullback-reclaim", name: "Uptrend pullback reclaim", entry: "In an SMA50>SMA100 uptrend, close crosses back above SMA20 while above SMA100.", exit: "Close below SMA50 or 5% close-based stop." }),
  ]);
  const WARMUP_BARS = 100;
  const DEFAULTS = Object.freeze({ feeBps: 6, spreadBps: 2, slippageBps: 3, startingEquity: 10000, allocation: 0.25, stopPct: 0.05 });

  function assertBars(input) {
    if (!Array.isArray(input) || input.length < 120) throw new Error("Add at least 120 valid, ordered OHLC rows so the indicators can warm up.");
    let previousTime = -Infinity;
    const bars = input.map((source, index) => {
      const time = Date.parse(source.date);
      const bar = { date: String(source.date), open: Number(source.open), high: Number(source.high), low: Number(source.low), close: Number(source.close), volume: Number(source.volume ?? 0) };
      if (!Number.isFinite(time) || time <= previousTime) throw new Error(`Row ${index + 2}: dates must be valid, unique, and in ascending order.`);
      previousTime = time;
      if (![bar.open, bar.high, bar.low, bar.close, bar.volume].every(Number.isFinite) || [bar.open, bar.high, bar.low, bar.close].some((n) => n <= 0) || bar.volume < 0) throw new Error(`Row ${index + 2}: OHLC prices must be positive finite values and volume cannot be negative.`);
      if (bar.high < Math.max(bar.open, bar.close, bar.low) || bar.low > Math.min(bar.open, bar.close, bar.high)) throw new Error(`Row ${index + 2}: high/low do not contain the open and close.`);
      return bar;
    });
    return bars;
  }

  function seededRandom(seed) {
    let state = seed >>> 0;
    return () => {
      state = (state + 0x6D2B79F5) >>> 0;
      let t = state;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function makeScenario(kind = "mixed", count = 420) {
    if (!["mixed", "rising", "falling", "sideways"].includes(kind)) throw new Error("Choose a supported demo market scenario.");
    if (!Number.isInteger(count) || count < 120 || count > 5000) throw new Error("Scenario length must be between 120 and 5,000 bars.");
    const seeds = { mixed: 91731, rising: 22847, falling: 66391, sideways: 44117 };
    const random = seededRandom(seeds[kind]);
    const bars = [];
    let close = 100;
    for (let i = 0; i < count; i += 1) {
      const phase = Math.min(2, Math.floor((i / count) * 3));
      const regime = kind === "mixed" ? ["rising", "falling", "sideways"][phase] : kind;
      const drift = regime === "rising" ? 0.00135 : regime === "falling" ? -0.0012 : 0.00004;
      const noise = (random() + random() + random() - 1.5) * 0.014;
      const open = close * (1 + (random() - 0.5) * 0.004);
      const nextClose = Math.max(1, open * Math.exp(drift + noise));
      const wick = 0.002 + random() * 0.012;
      const high = Math.max(open, nextClose) * (1 + wick * random());
      const low = Math.min(open, nextClose) * (1 - wick * random());
      bars.push({ date: new Date(Date.UTC(2020, 0, 1 + i)).toISOString().slice(0, 10), open, high, low, close: nextClose, volume: Math.round(90000 + random() * 190000) });
      close = nextClose;
    }
    return assertBars(bars);
  }

  function tokenizeCsvLine(line) {
    const cells = [];
    let cell = "";
    let quoted = false;
    for (let i = 0; i < line.length; i += 1) {
      const char = line[i];
      if (char === '"' && quoted && line[i + 1] === '"') { cell += '"'; i += 1; }
      else if (char === '"') quoted = !quoted;
      else if (char === "," && !quoted) { cells.push(cell.trim()); cell = ""; }
      else cell += char;
    }
    if (quoted) throw new Error("CSV contains an unclosed quoted value.");
    cells.push(cell.trim());
    return cells;
  }

  function parseCsv(text) {
    if (typeof text !== "string" || !text.trim()) throw new Error("The CSV file is empty.");
    const rows = text.replace(/^\uFEFF/, "").split(/\r?\n/).filter((line) => line.trim());
    if (rows.length < 121) throw new Error("CSV must include a header and at least 120 price rows.");
    const headings = tokenizeCsvLine(rows[0]).map((heading) => heading.trim().toLowerCase().replace(/[\s_-]+/g, ""));
    const findColumn = (...names) => headings.findIndex((heading) => names.includes(heading));
    const columns = { date: findColumn("date", "datetime", "timestamp", "time"), open: findColumn("open"), high: findColumn("high"), low: findColumn("low"), close: findColumn("close", "adjclose"), volume: findColumn("volume") };
    const missing = Object.entries(columns).filter(([name, index]) => name !== "volume" && index < 0).map(([name]) => name);
    if (missing.length) throw new Error(`CSV is missing required columns: ${missing.join(", ")}.`);
    const bars = rows.slice(1).map((line, index) => {
      const cells = tokenizeCsvLine(line);
      const value = (column) => cells[columns[column]];
      if (cells.length !== headings.length) throw new Error(`CSV row ${index + 2} has a different number of columns from the header.`);
      return { date: value("date"), open: Number(value("open")), high: Number(value("high")), low: Number(value("low")), close: Number(value("close")), volume: columns.volume < 0 || value("volume") === "" ? 0 : Number(value("volume")) };
    });
    return assertBars(bars);
  }

  function movingAverage(values, period) {
    const result = Array(values.length).fill(null);
    let sum = 0;
    for (let i = 0; i < values.length; i += 1) {
      sum += values[i];
      if (i >= period) sum -= values[i - period];
      if (i >= period - 1) result[i] = sum / period;
    }
    return result;
  }

  function priorRollingHigh(values, period) {
    const result = Array(values.length).fill(null);
    for (let i = period; i < values.length; i += 1) {
      let high = -Infinity;
      for (let j = i - period; j < i; j += 1) high = Math.max(high, values[j]);
      result[i] = high;
    }
    return result;
  }

  function normalizeOptions(options = {}) {
    const values = { ...DEFAULTS, ...options };
    for (const name of ["feeBps", "spreadBps", "slippageBps", "startingEquity", "allocation", "stopPct"]) {
      if (!Number.isFinite(Number(values[name]))) throw new Error(`${name} must be a finite number.`);
      values[name] = Number(values[name]);
    }
    if (values.feeBps < 0 || values.feeBps > 100 || values.spreadBps < 0 || values.spreadBps > 200 || values.slippageBps < 0 || values.slippageBps > 200) throw new Error("Costs must be non-negative and within the supported range.");
    if (values.startingEquity <= 0 || values.allocation <= 0 || values.allocation > 1 || values.stopPct <= 0 || values.stopPct >= 1) throw new Error("Starting equity, position size, and stop loss are outside their supported range.");
    const strategyId = String(values.strategyId ?? STRATEGIES[0].id);
    if (!STRATEGIES.some((strategy) => strategy.id === strategyId)) throw new Error("Choose a supported frozen strategy.");
    values.strategyId = strategyId;
    return values;
  }

  function maxDrawdown(curve, startingEquity) {
    let peak = startingEquity;
    let drawdown = 0;
    for (const value of curve) {
      peak = Math.max(peak, value.equity);
      if (peak > 0) drawdown = Math.max(drawdown, (peak - value.equity) / peak);
    }
    return drawdown;
  }

  function sharpe(curve) {
    const returns = [];
    for (let i = 1; i < curve.length; i += 1) {
      if (curve[i - 1].equity > 0) returns.push(curve[i].equity / curve[i - 1].equity - 1);
    }
    if (returns.length < 2) return 0;
    const mean = returns.reduce((sum, value) => sum + value, 0) / returns.length;
    const variance = returns.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (returns.length - 1);
    const deviation = Math.sqrt(variance);
    return deviation === 0 ? 0 : mean / deviation * Math.sqrt(252);
  }

  function backtest(inputBars, options = {}) {
    const bars = assertBars(inputBars);
    const config = normalizeOptions(options);
    const strategy = STRATEGIES.find((item) => item.id === config.strategyId);
    const fromIndex = Math.max(WARMUP_BARS, Math.floor(options.fromIndex ?? WARMUP_BARS));
    const toIndex = Math.min(bars.length, Math.floor(options.toIndex ?? bars.length));
    if (fromIndex >= toIndex - 1) throw new Error("The selected replay period is too short after indicator warm-up.");
    const closes = bars.map((bar) => bar.close);
    const ma20 = movingAverage(closes, 20);
    const ma50 = movingAverage(closes, 50);
    const ma100 = movingAverage(closes, 100);
    const priorHigh20 = priorRollingHigh(bars.map((bar) => bar.high), 20);
    const adverse = (config.spreadBps + config.slippageBps) / 10000;
    const feeRate = config.feeBps / 10000;
    let cash = config.startingEquity;
    let position = null;
    let pending = null;
    const trades = [];
    const curve = [{ date: bars[fromIndex].date, equity: cash }];
    let totalCosts = 0;

    const entrySignal = (i) => {
      if (strategy.id === "trend-50-100") return closes[i] > ma100[i] && ma50[i] > ma100[i];
      if (strategy.id === "breakout-20") return priorHigh20[i] !== null && closes[i] > priorHigh20[i] && ma50[i] > ma100[i];
      return closes[i] > ma100[i] && ma50[i] > ma100[i] && closes[i] > ma20[i] && closes[i - 1] <= ma20[i - 1];
    };
    const exitSignal = (i) => closes[i] < (strategy.id === "breakout-20" ? ma20[i] : ma50[i]);
    const buyAt = (barIndex, reason) => {
      const raw = bars[barIndex].open;
      const fill = raw * (1 + adverse);
      const quantity = (cash * config.allocation) / (fill * (1 + feeRate));
      if (!(quantity > 0)) return;
      const notional = quantity * fill;
      const fee = notional * feeRate;
      const outlay = notional + fee;
      if (outlay > cash) return;
      position = { entryIndex: barIndex, entrySignalIndex: barIndex - 1, entryRaw: raw, entryFill: fill, quantity, entryFee: fee, entryCost: outlay, entryReason: reason };
      cash -= outlay;
      totalCosts += fee + (fill - raw) * quantity;
    };

    const sellAt = (barIndex, rawPrice, reason) => {
      if (!position) return;
      const fill = rawPrice * (1 - adverse);
      const notional = position.quantity * fill;
      const fee = notional * feeRate;
      const proceeds = notional - fee;
      cash += proceeds;
      const grossPnl = (rawPrice - position.entryRaw) * position.quantity;
      const costs = position.entryFee + fee + (position.entryFill - position.entryRaw) * position.quantity + (rawPrice - fill) * position.quantity;
      const netPnl = proceeds - position.entryCost;
      trades.push({ entryDate: bars[position.entryIndex].date, exitDate: bars[barIndex].date, entryIndex: position.entryIndex, signalDate: bars[position.entrySignalIndex].date, exitIndex: barIndex, entryPrice: position.entryFill, exitPrice: fill, entryRawPrice: position.entryRaw, exitRawPrice: rawPrice, quantity: position.quantity, grossPnl, netPnl, costs, fees: position.entryFee + fee, spreadAndSlippage: costs - position.entryFee - fee, returnPct: netPnl / position.entryCost, entryReason: position.entryReason, exitReason: reason, ruleVersion: RULE_VERSION, strategyId: strategy.id, strategyName: strategy.name });
      totalCosts += fee + (rawPrice - fill) * position.quantity;
      position = null;
    };

    for (let i = fromIndex; i < toIndex; i += 1) {
      if (pending) {
        if (pending.type === "entry" && !position) buyAt(i, pending.reason);
        else if (pending.type === "exit" && position) sellAt(i, bars[i].open, pending.reason);
        pending = null;
      }
      const close = bars[i].close;
      const equity = cash + (position ? position.quantity * close : 0);
      curve.push({ date: bars[i].date, equity });
      if (i >= toIndex - 1) break;
      if (position) {
        if (close <= position.entryRaw * (1 - config.stopPct)) pending = { type: "exit", reason: `${(config.stopPct * 100).toFixed(0)}% close-based stop` };
        else if (exitSignal(i)) pending = { type: "exit", reason: strategy.exit };
      } else if (entrySignal(i)) {
        pending = { type: "entry", reason: strategy.entry };
      }
    }

    if (position) sellAt(toIndex - 1, bars[toIndex - 1].close, "End of replay");
    const finalEquity = cash;
    curve[curve.length - 1] = { date: bars[toIndex - 1].date, equity: finalEquity };
    const wins = trades.filter((trade) => trade.netPnl > 0).length;
    const totalNetPnl = finalEquity - config.startingEquity;
    const expectancy = trades.length ? trades.reduce((sum, trade) => sum + trade.netPnl, 0) / trades.length : 0;
    const benchmark = buyAndHold(bars, fromIndex, toIndex, config);
    return { ruleVersion: RULE_VERSION, strategyId: strategy.id, strategyName: strategy.name, fromIndex, toIndex, startDate: bars[fromIndex].date, endDate: bars[toIndex - 1].date, startingEquity: config.startingEquity, finalEquity, returnPct: totalNetPnl / config.startingEquity, totalNetPnl, totalCosts, trades, tradeCount: trades.length, winningTrades: wins, losingTrades: trades.length - wins, winRate: trades.length ? wins / trades.length : 0, expectancy, maxDrawdown: maxDrawdown(curve, config.startingEquity), sharpe: sharpe(curve), equityCurve: curve, benchmark, config };
  }

  function buyAndHold(bars, fromIndex, toIndex, config) {
    const entryRaw = bars[fromIndex].open;
    const exitRaw = bars[toIndex - 1].close;
    const adverse = (config.spreadBps + config.slippageBps) / 10000;
    const feeRate = config.feeBps / 10000;
    const entryFill = entryRaw * (1 + adverse);
    const quantity = config.startingEquity * config.allocation / (entryFill * (1 + feeRate));
    const entryFee = quantity * entryFill * feeRate;
    const exitFill = exitRaw * (1 - adverse);
    const exitFee = quantity * exitFill * feeRate;
    const finalEquity = config.startingEquity - quantity * entryFill - entryFee + quantity * exitFill - exitFee;
    return { finalEquity, returnPct: (finalEquity - config.startingEquity) / config.startingEquity, costs: entryFee + exitFee + (entryFill - entryRaw) * quantity + (exitRaw - exitFill) * quantity };
  }

  function evaluate(inputBars, options = {}) {
    const bars = assertBars(inputBars);
    const splitPercent = Number(options.splitPercent ?? 70);
    if (![70, 80].includes(splitPercent)) throw new Error("Choose a 70% or 80% training split.");
    const split = Math.floor(bars.length * splitPercent / 100);
    if (split < WARMUP_BARS + 15 || bars.length - split < 20) throw new Error("The training period or untouched holdout is too short.");
    const training = backtest(bars, { ...options, fromIndex: WARMUP_BARS, toIndex: split });
    const holdout = backtest(bars, { ...options, fromIndex: split, toIndex: bars.length });
    return { splitPercent, splitIndex: split, training, holdout, barsCount: bars.length, startDate: bars[0].date, splitDate: bars[split].date, endDate: bars[bars.length - 1].date, source: options.source || "synthetic demo" };
  }

  function emptyReplay(bars, fromIndex, toIndex, config) {
    const benchmark = buyAndHold(bars, fromIndex, toIndex, config);
    const dates = [bars[fromIndex].date, bars[toIndex - 1].date];
    return {
      ruleVersion: RULE_VERSION, strategyId: "cash", strategyName: "Cash · no candidate passed",
      fromIndex, toIndex, startDate: dates[0], endDate: dates[1],
      startingEquity: config.startingEquity, finalEquity: config.startingEquity,
      returnPct: 0, totalNetPnl: 0, totalCosts: 0, trades: [], tradeCount: 0,
      winningTrades: 0, losingTrades: 0, winRate: 0, expectancy: 0, maxDrawdown: 0,
      sharpe: 0, equityCurve: [{ date: dates[0], equity: config.startingEquity }, { date: dates[1], equity: config.startingEquity }],
      benchmark, config,
    };
  }

  function agentEvaluate(inputBars, options = {}) {
    const bars = assertBars(inputBars);
    const config = normalizeOptions(options);
    const splitPercent = Number(options.splitPercent ?? 70);
    if (![70, 80].includes(splitPercent)) throw new Error("Choose a 70% or 80% training split.");
    const split = Math.floor(bars.length * splitPercent / 100);
    if (split < WARMUP_BARS + 15 || bars.length - split < 20) throw new Error("The training period or untouched holdout is too short.");

    const trained = STRATEGIES.map((strategy) => {
      const result = backtest(bars, { ...options, strategyId: strategy.id, fromIndex: WARMUP_BARS, toIndex: split });
      const score = result.returnPct - result.maxDrawdown * 0.75;
      const beatsBaseline = result.returnPct > result.benchmark.returnPct;
      const eligible = result.tradeCount >= MIN_AGENT_TRAINING_TRADES && result.returnPct > 0 && result.expectancy > 0 && beatsBaseline;
      return { strategy, result, score, eligible, beatsBaseline };
    }).sort((a, b) => b.score - a.score);

    const selected = trained.find((candidate) => candidate.eligible) || null;
    const training = selected ? selected.result : emptyReplay(bars, WARMUP_BARS, split, config);
    const holdout = selected
      ? backtest(bars, { ...options, strategyId: selected.strategy.id, fromIndex: split, toIndex: bars.length })
      : emptyReplay(bars, split, bars.length, config);
    const candidates = trained.map(({ strategy, result, score, eligible, beatsBaseline }) => ({
      strategyId: strategy.id,
      name: strategy.name,
      trainingReturnPct: result.returnPct,
      trainingBenchmarkReturnPct: result.benchmark.returnPct,
      beatsTrainingBaseline: beatsBaseline,
      trainingDrawdown: result.maxDrawdown,
      trainingExpectancy: result.expectancy,
      trainingTrades: result.tradeCount,
      score,
      eligible,
    }));
    const selectionReason = selected
      ? `Selected ${selected.strategy.name} using training-only net return minus a drawdown penalty; it had ${selected.result.tradeCount} training trades, ${selected.result.expectancy.toFixed(2)} average net P&L per trade, and beat the matched cost-adjusted buy-and-hold baseline (${(selected.result.returnPct * 100).toFixed(2)}% vs ${(selected.result.benchmark.returnPct * 100).toFixed(2)}%). The rule is frozen for the untouched holdout.`
      : `Stayed in cash: no candidate had at least ${MIN_AGENT_TRAINING_TRADES} training trades, positive after-cost return and expectancy, and a return above the matched cost-adjusted buy-and-hold baseline. The holdout was not used to select a strategy.`;
    return {
      agentVersion: AGENT_VERSION,
      selectionMetric: "training net return − 0.75 × max drawdown",
      minimumTrainingTrades: MIN_AGENT_TRAINING_TRADES,
      selectedStrategyId: selected?.strategy.id || "cash",
      selectedStrategyName: selected?.strategy.name || "Cash · no candidate passed",
      selectionReason,
      candidates,
      splitPercent,
      splitIndex: split,
      training,
      holdout,
      barsCount: bars.length,
      startDate: bars[0].date,
      splitDate: bars[split].date,
      endDate: bars[bars.length - 1].date,
      source: options.source || "synthetic demo",
    };
  }

  function describeRegime(bars) {
    const first = bars[0].close;
    const last = bars[bars.length - 1].close;
    const change = last / first - 1;
    const deltas = bars.slice(1).map((bar, i) => bar.close / bars[i].close - 1);
    const mean = deltas.reduce((sum, value) => sum + value, 0) / Math.max(1, deltas.length);
    const variance = deltas.reduce((sum, value) => sum + (value - mean) ** 2, 0) / Math.max(1, deltas.length);
    const volatility = Math.sqrt(variance) * Math.sqrt(252);
    const label = Math.abs(change) < volatility * 0.22 ? "range-bound" : change > 0 ? "rising overall" : "falling overall";
    return { label, change, annualizedVolatility: volatility };
  }

  

  const api = Object.freeze({ RULE_VERSION, AGENT_VERSION, MIN_AGENT_TRAINING_TRADES, STRATEGIES, WARMUP_BARS, DEFAULTS, assertBars, makeScenario, parseCsv, backtest, evaluate, agentEvaluate, describeRegime });
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof window !== "undefined") window.LokiLab = api;
})();

