"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const Lab = require("../static/js/strategy-lab.js");

function barsFromCloses(closes, opens = closes) {
  return closes.map((close, i) => ({
    date: new Date(Date.UTC(2022, 0, 1 + i)).toISOString().slice(0, 10),
    open: opens[i], high: Math.max(close, opens[i]) * 1.002,
    low: Math.min(close, opens[i]) * 0.998, close, volume: 100000,
  }));
}

function trendFixture(count = 240) {
  const closes = Array.from({ length: count }, (_, i) => i < 105 ? 100 : 100 + (i - 104) * 0.8);
  return barsFromCloses(closes);
}

test("demo scenarios are deterministic and produce valid OHLCV bars", () => {
  for (const name of ["mixed", "rising", "falling", "sideways"]) {
    const first = Lab.makeScenario(name);
    const second = Lab.makeScenario(name);
    assert.deepEqual(first, second);
    assert.equal(first.length, 420);
    assert.equal(Lab.assertBars(first).length, 420);
  }
});

test("rising and falling scenarios cover different directional regimes", () => {
  const rising = Lab.makeScenario("rising");
  const falling = Lab.makeScenario("falling");
  assert.ok(rising.at(-1).close > rising[0].close);
  assert.ok(falling.at(-1).close < falling[0].close);
  assert.equal(Lab.describeRegime(rising).label, "rising overall");
  assert.equal(Lab.describeRegime(falling).label, "falling overall");
});

test("mixed demo path actually contains rising, falling and sideways segments", () => {
  const mixed = Lab.makeScenario("mixed");
  const third = Math.floor(mixed.length / 3);
  const up = mixed[third - 1].close / mixed[0].close - 1;
  const down = mixed[2 * third - 1].close / mixed[third].close - 1;
  const sideways = mixed.at(-1).close / mixed[2 * third].close - 1;
  assert.ok(up > 0.08, `rising segment returned ${(up * 100).toFixed(1)}%`);
  assert.ok(down < -0.08, `falling segment returned ${(down * 100).toFixed(1)}%`);
  assert.ok(Math.abs(sideways) < 0.15, `sideways segment moved ${(sideways * 100).toFixed(1)}%`);
});

test("unsupported scenario and invalid lengths fail closed", () => {
  assert.throws(() => Lab.makeScenario("live"), /supported demo/);
  assert.throws(() => Lab.makeScenario("mixed", 119), /between 120/);
  assert.throws(() => Lab.makeScenario("mixed", 5001), /between 120/);
});

test("CSV parser normalizes headings and accepts a missing optional volume field", () => {
  const data = Lab.makeScenario("rising", 120);
  const csv = `Timestamp,Open,High,Low,Close\n${data.map((bar) => `${bar.date},${bar.open},${bar.high},${bar.low},${bar.close}`).join("\n")}`;
  const parsed = Lab.parseCsv(csv);
  assert.equal(parsed.length, 120);
  assert.equal(parsed[0].volume, 0);
});

test("CSV parser handles quoted fields and reordered columns", () => {
  const data = Lab.makeScenario("sideways", 120);
  const csv = `Volume,Close,Date,Low,Open,High\n${data.map((bar) => `${bar.volume},${bar.close},"${bar.date}",${bar.low},${bar.open},${bar.high}`).join("\n")}`;
  assert.deepEqual(Lab.parseCsv(csv), data);
});

test("CSV parser rejects empty files, missing columns, short history and malformed rows", () => {
  assert.throws(() => Lab.parseCsv("  "), /empty/);
  assert.throws(() => Lab.parseCsv("date,open,close\n2020-01-01,1,1"), /120 price rows/);
  const short = Lab.makeScenario("mixed", 120).slice(0, 119);
  const csv = `date,open,high,low,close\n${short.map((b) => `${b.date},${b.open},${b.high},${b.low},${b.close}`).join("\n")}`;
  assert.throws(() => Lab.parseCsv(csv), /120 price rows/);
  const enoughRows = Lab.makeScenario("mixed", 120).map((b) => `${b.date},${b.open},${b.high},${b.low},${b.close}`).join("\n");
  assert.throws(() => Lab.parseCsv(`date,open,high,low,close\n${enoughRows}`.replace("date,open,high,low,close", "date,open,close,low,close")), /missing required columns/);
  assert.throws(() => Lab.parseCsv(`date,open,high,low,close\n${enoughRows}\nbad,row`), /different number of columns/);
});

test("CSV parser rejects unclosed quotes and out-of-order dates", () => {
  const csv = `date,open,high,low,close\n${Lab.makeScenario("mixed", 120).map((b) => `${b.date},${b.open},${b.high},${b.low},${b.close}`).join("\n")}`;
  assert.throws(() => Lab.parseCsv(csv.replace("2020-01-01", '"2020-01-01')), /unclosed quoted/);
  const lines = csv.split("\n");
  [lines[1], lines[2]] = [lines[2], lines[1]];
  assert.throws(() => Lab.parseCsv(lines.join("\n")), /ascending order/);
});

test("OHLC validation rejects invalid prices and inconsistent highs and lows", () => {
  const values = Lab.makeScenario("mixed", 120);
  const invalid = values.map((bar) => ({ ...bar }));
  invalid[10].close = NaN;
  assert.throws(() => Lab.assertBars(invalid), /positive finite/);
  const inconsistent = values.map((bar) => ({ ...bar }));
  inconsistent[10].high = inconsistent[10].low / 2;
  assert.throws(() => Lab.assertBars(inconsistent), /high\/low/);
});

test("replay executes at the next bar open and records its signal timestamp", () => {
  const bars = trendFixture();
  const result = Lab.backtest(bars, { feeBps: 0, spreadBps: 0, slippageBps: 0 });
  assert.ok(result.tradeCount >= 1);
  const trade = result.trades[0];
  assert.equal(trade.entryIndex, bars.findIndex((bar) => bar.date === trade.entryDate));
  assert.equal(trade.entryIndex, bars.findIndex((bar) => bar.date === trade.signalDate) + 1);
  assert.equal(trade.entryRawPrice, bars[trade.entryIndex].open);
});

test("open positions close at the end of the replay and appear in the journal result", () => {
  const result = Lab.backtest(trendFixture(), { feeBps: 0, spreadBps: 0, slippageBps: 0 });
  assert.ok(result.tradeCount > 0);
  assert.equal(result.trades.at(-1).exitReason, "End of replay");
  assert.equal(result.trades.at(-1).exitDate, result.endDate);
  assert.equal(result.trades.at(-1).exitRawPrice, trendFixture().at(-1).close);
});

test("5% close-based risk stop is recorded and filled at the next bar open", () => {
  const closes = Array.from({ length: 200 }, (_, i) => i < 105 ? 100 : 100 + (i - 104) * 0.8);
  closes[150] = 95;
  closes.fill(95, 151);
  const bars = barsFromCloses(closes);
  const result = Lab.backtest(bars, { feeBps: 0, spreadBps: 0, slippageBps: 0 });
  const trade = result.trades[0];
  assert.equal(trade.exitReason, "5% close-based stop");
  assert.equal(trade.exitIndex, 151);
  assert.equal(trade.exitRawPrice, bars[151].open);
  assert.ok(trade.exitIndex > 150);
});

test("costs appear on both sides and worsen a known uptrend versus zero cost", () => {
  const bars = trendFixture();
  const free = Lab.backtest(bars, { feeBps: 0, spreadBps: 0, slippageBps: 0 });
  const costly = Lab.backtest(bars, { feeBps: 8, spreadBps: 4, slippageBps: 5 });
  assert.equal(free.tradeCount, costly.tradeCount);
  assert.ok(costly.totalCosts > 0);
  assert.ok(costly.finalEquity < free.finalEquity);
  for (const trade of costly.trades) {
    assert.ok(trade.costs > 0);
    assert.ok(trade.fees > 0);
    assert.ok(trade.spreadAndSlippage > 0);
    assert.ok(Math.abs(trade.grossPnl - trade.costs - trade.netPnl) < 1e-7);
  }
});

test("fees, spread and slippage all zero leaves no hidden execution cost", () => {
  const result = Lab.backtest(trendFixture(), { feeBps: 0, spreadBps: 0, slippageBps: 0 });
  assert.equal(result.totalCosts, 0);
  assert.ok(result.trades.every((trade) => trade.costs === 0));
});

test("flat prices do not trigger a trend entry", () => {
  const flat = barsFromCloses(Array(240).fill(100));
  const result = Lab.backtest(flat);
  assert.equal(result.tradeCount, 0);
  assert.equal(result.totalCosts, 0);
  assert.equal(result.finalEquity, 10000);
  assert.equal(result.maxDrawdown, 0);
});

test("falling demo scenario produces finite, cost-aware risk metrics", () => {
  const result = Lab.backtest(Lab.makeScenario("falling"));
  assert.ok(Number.isFinite(result.returnPct));
  assert.ok(Number.isFinite(result.maxDrawdown));
  assert.ok(result.totalCosts >= 0);
  assert.ok(result.finalEquity <= result.startingEquity * 1.05);
});

test("holdout starts flat and cannot carry training-period trades into test", () => {
  const bars = trendFixture(420);
  const result = Lab.evaluate(bars, { splitPercent: 70, feeBps: 0, spreadBps: 0, slippageBps: 0 });
  assert.equal(result.holdout.fromIndex, result.splitIndex);
  assert.ok(result.holdout.trades.every((trade) => trade.entryIndex >= result.splitIndex));
  assert.ok(result.holdout.equityCurve.every((point) => Date.parse(point.date) >= Date.parse(result.splitDate)));
});

test("holdout uses earlier history for moving-average warmup without pre-split trades", () => {
  const bars = trendFixture(420);
  const result = Lab.evaluate(bars, { splitPercent: 70 });
  assert.equal(result.holdout.fromIndex, 294);
  assert.equal(result.holdout.startDate, bars[294].date);
});

test("training and untouched holdout compare after costs against matched-allocation baseline", () => {
  const result = Lab.evaluate(Lab.makeScenario("mixed"), { splitPercent: 80, feeBps: 6, spreadBps: 2, slippageBps: 3 });
  assert.equal(result.splitIndex, 336);
  assert.equal(result.training.toIndex, 336);
  assert.equal(result.holdout.toIndex, 420);
  assert.ok(Number.isFinite(result.training.benchmark.returnPct));
  assert.ok(Number.isFinite(result.holdout.benchmark.returnPct));
  assert.ok(result.holdout.maxDrawdown >= 0 && result.holdout.maxDrawdown <= 1);
  assert.ok(Number.isFinite(result.holdout.sharpe));
});

test("unsupported split percentages and too-short test segments are rejected", () => {
  assert.throws(() => Lab.evaluate(Lab.makeScenario("mixed"), { splitPercent: 75 }), /70% or 80%/);
  assert.throws(() => Lab.evaluate(Lab.makeScenario("mixed", 120), { splitPercent: 80 }), /too short/);
});

test("cost inputs reject negatives, non-finite values and unbounded bps", () => {
  const bars = trendFixture();
  assert.throws(() => Lab.backtest(bars, { feeBps: -1 }), /non-negative/);
  assert.throws(() => Lab.backtest(bars, { spreadBps: 201 }), /supported range/);
  assert.throws(() => Lab.backtest(bars, { feeBps: Infinity }), /finite number/);
});

test("position allocation cannot spend beyond available cash", () => {
  const result = Lab.backtest(trendFixture(), { allocation: 1, feeBps: 100, spreadBps: 100, slippageBps: 100 });
  assert.ok(result.trades.length > 0);
  assert.ok(result.trades.every((trade) => Number.isFinite(trade.quantity) && trade.quantity > 0));
  assert.ok(Number.isFinite(result.finalEquity));
});

test("result metrics reconcile to final balance and trade expectancy", () => {
  const result = Lab.backtest(trendFixture());
  const sum = result.trades.reduce((total, trade) => total + trade.netPnl, 0);
  assert.ok(Math.abs(sum - result.totalNetPnl) < 1e-7);
  assert.equal(result.tradeCount, result.trades.length);
  if (result.tradeCount) assert.ok(Math.abs(result.expectancy - sum / result.tradeCount) < 1e-7);
});

test("rule version is visible on every logged trade", () => {
  const result = Lab.backtest(trendFixture());
  assert.equal(result.ruleVersion, "1.1");
  assert.ok(result.trades.every((trade) => trade.ruleVersion === "1.1"));
});


test("candidate strategies keep delayed fills and explicit per-trade rule metadata", () => {
  const bars = Lab.makeScenario("rising");
  for (const strategyId of ["trend-50-100", "breakout-20", "pullback-reclaim"]) {
    const result = Lab.backtest(bars, { strategyId });
    assert.equal(result.strategyId, strategyId);
    assert.ok(result.trades.every((trade) => trade.strategyId === strategyId));
    assert.ok(result.trades.every((trade) => trade.ruleVersion === "1.1"));
    for (const trade of result.trades) {
      assert.equal(trade.entryIndex, bars.findIndex((bar) => bar.date === trade.entryDate));
      assert.equal(trade.entryIndex, bars.findIndex((bar) => bar.date === trade.signalDate) + 1);
    }
  }
});

test("AI paper agent selects only candidates with enough profitable training evidence", () => {
  const result = Lab.agentEvaluate(Lab.makeScenario("rising"), { splitPercent: 70 });
  assert.notEqual(result.selectedStrategyId, "cash");
  assert.equal(result.minimumTrainingTrades, 5);
  assert.ok(result.candidates.some((candidate) => candidate.strategyId === result.selectedStrategyId && candidate.eligible));
  assert.ok(result.holdout.trades.every((trade) => trade.entryIndex >= result.splitIndex));
  assert.match(result.selectionReason, /training-only/);
  assert.ok(result.candidates.every((candidate) => candidate.trainingTrades >= 0 && Number.isFinite(candidate.score)));
});

test("AI agent candidate selection is unchanged when untouched holdout prices change", () => {
  const bars = Lab.makeScenario("rising");
  const first = Lab.agentEvaluate(bars, { splitPercent: 70 });
  const changed = bars.map((bar, index) => {
    if (index < first.splitIndex) return { ...bar };
    const progress = (index - first.splitIndex) / Math.max(1, bars.length - 1 - first.splitIndex);
    const factor = 1 - 0.45 * progress;
    return {
      ...bar, open: bar.open * factor, high: bar.high * factor,
      low: bar.low * factor, close: bar.close * factor,
    };
  });
  const second = Lab.agentEvaluate(changed, { splitPercent: 70 });
  assert.equal(second.selectedStrategyId, first.selectedStrategyId);
  assert.deepEqual(second.candidates, first.candidates);
  assert.notEqual(second.holdout.benchmark.returnPct, first.holdout.benchmark.returnPct);
});

test("AI agent parks in cash when no training rule meets the evidence floor", () => {
  const result = Lab.agentEvaluate(Lab.makeScenario("falling"), { splitPercent: 70 });
  assert.equal(result.selectedStrategyId, "cash");
  assert.equal(result.holdout.tradeCount, 0);
  assert.equal(result.holdout.returnPct, 0);
  assert.ok(result.holdout.benchmark.returnPct < 0);
  assert.match(result.selectionReason, /Stayed in cash/);
});

test("AI agent rejects invalid splits and never trades unsupported strategy identifiers", () => {
  const bars = Lab.makeScenario("rising");
  assert.throws(() => Lab.agentEvaluate(bars, { splitPercent: 75 }), /70% or 80%/);
  assert.throws(() => Lab.backtest(bars, { strategyId: "magic-profit" }), /frozen strategy/);
});
