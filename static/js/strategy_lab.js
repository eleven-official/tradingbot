"use strict";

const form = document.querySelector("#backtest-form");
const statusLine = document.querySelector("#replay-status");
const results = document.querySelector("#replay-results");
const runButton = document.querySelector("#run-replay");
const svgNamespace = "http://www.w3.org/2000/svg";

function setText(id, value) {
  const node = document.getElementById(id);
  if (node) node.textContent = value;
}

function numberText(value, digits) {
  const precision = Number.isFinite(digits) ? digits : 2;
  return Number(value).toLocaleString(undefined, {
    minimumFractionDigits: precision,
    maximumFractionDigits: precision,
  });
}

function percentText(value) {
  return numberText(value, 2) + "%";
}

function timeText(value) {
  return new Date(Number(value) * 1000).toLocaleString();
}

function renderEquityCurve(points) {
  const svg = document.querySelector("#equity-chart");
  svg.replaceChildren();
  if (!Array.isArray(points) || points.length < 2) return;

  const width = 860;
  const height = 230;
  const inset = 16;
  const values = points.map(function (point) { return Number(point.equity); });
  const low = Math.min.apply(null, values);
  const high = Math.max.apply(null, values);
  const range = Math.max(high - low, Math.abs(high) * 0.002, 1);
  const xAt = function (index) { return inset + (width - inset * 2) * index / (points.length - 1); };
  const yAt = function (value) { return height - inset - (value - low) / range * (height - inset * 2); };

  for (let line = 0; line < 4; line += 1) {
    const y = inset + (height - inset * 2) * line / 3;
    const grid = document.createElementNS(svgNamespace, "line");
    grid.setAttribute("x1", String(inset));
    grid.setAttribute("x2", String(width - inset));
    grid.setAttribute("y1", String(y));
    grid.setAttribute("y2", String(y));
    grid.setAttribute("class", "chart-gridline");
    svg.appendChild(grid);
  }

  const definition = document.createElementNS(svgNamespace, "defs");
  const gradient = document.createElementNS(svgNamespace, "linearGradient");
  gradient.setAttribute("id", "equity-fill");
  gradient.setAttribute("x1", "0");
  gradient.setAttribute("x2", "0");
  gradient.setAttribute("y1", "0");
  gradient.setAttribute("y2", "1");
  const top = document.createElementNS(svgNamespace, "stop");
  top.setAttribute("offset", "0%");
  top.setAttribute("stop-color", "#7ed5ba");
  top.setAttribute("stop-opacity", "0.23");
  const bottom = document.createElementNS(svgNamespace, "stop");
  bottom.setAttribute("offset", "100%");
  bottom.setAttribute("stop-color", "#7ed5ba");
  bottom.setAttribute("stop-opacity", "0");
  gradient.appendChild(top);
  gradient.appendChild(bottom);
  definition.appendChild(gradient);
  svg.appendChild(definition);

  const pathPoints = points.map(function (point, index) {
    return [xAt(index), yAt(Number(point.equity))];
  });
  const linePath = pathPoints.map(function (point, index) {
    return (index === 0 ? "M " : "L ") + point[0].toFixed(1) + " " + point[1].toFixed(1);
  }).join(" ");
  const area = document.createElementNS(svgNamespace, "path");
  area.setAttribute("d", linePath + " L " + pathPoints[pathPoints.length - 1][0] + " " + (height - inset) + " L " + pathPoints[0][0] + " " + (height - inset) + " Z");
  area.setAttribute("class", "chart-area");
  svg.appendChild(area);

  const line = document.createElementNS(svgNamespace, "path");
  line.setAttribute("d", linePath);
  line.setAttribute("class", "chart-line");
  svg.appendChild(line);
}

function renderTrades(trades, count) {
  const body = document.querySelector("#trade-rows");
  body.replaceChildren();
  setText("trade-count-note", count + " holdout trades");
  if (!trades.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 6;
    cell.className = "trade-empty";
    cell.textContent = "No completed signals in this holdout window. Try another timeframe or strategy.";
    row.appendChild(cell);
    body.appendChild(row);
    return;
  }

  trades.slice().reverse().forEach(function (trade) {
    const row = document.createElement("tr");
    const values = [
      timeText(trade.entry_time),
      numberText(trade.entry_price, 4),
      numberText(trade.exit_price, 4),
      numberText(trade.net_pnl_quote, 2),
      numberText(trade.net_r, 2) + "R",
      String(trade.exit_reason).replaceAll("_", " "),
    ];
    values.forEach(function (value, index) {
      const cell = document.createElement("td");
      cell.textContent = value;
      if (index === 3 || index === 4) {
        cell.className = Number(index === 3 ? trade.net_pnl_quote : trade.net_r) >= 0
          ? "trade-positive"
          : "trade-negative";
      }
      row.appendChild(cell);
    });
    body.appendChild(row);
  });
}

function renderResult(data) {
  const holdout = data.out_of_sample;
  const training = data.training;
  setText("result-market", data.symbol + " · " + data.interval + " · " + data.bar_count + " completed bars");
  setText("holdout-return", percentText(holdout.net_return_percent));
  setText("holdout-trades", String(holdout.trade_count));
  setText("holdout-bars", holdout.sample_bars + " unseen chronological bars");
  setText("holdout-winrate", percentText(holdout.win_rate_percent));
  setText("holdout-expectancy", numberText(holdout.expectancy_r, 2) + "R");
  setText("holdout-drawdown", percentText(holdout.max_drawdown_percent));
  setText("holdout-profit-factor", holdout.profit_factor === null ? "—" : numberText(holdout.profit_factor, 2));
  setText("training-return", percentText(training.net_return_percent));
  setText("training-trades", String(training.trade_count));
  setText("comparison-holdout-return", percentText(holdout.net_return_percent));
  setText("benchmark-return", percentText(holdout.buy_hold_return_percent));
  setText("equity-start", "Start · " + numberText(data.equity_curve[0].equity, 2));
  setText("equity-end", "End · " + numberText(data.equity_curve[data.equity_curve.length - 1].equity, 2));
  setText("replay-disclaimer", data.disclaimer + " A candle that touches both stop and target is scored as a stop; final sample-end exits are marked in the ledger.");
  renderEquityCurve(data.equity_curve);
  renderTrades(data.trades, holdout.trade_count);
  results.hidden = false;
}

form.addEventListener("submit", async function (event) {
  event.preventDefault();
  const values = Object.fromEntries(new FormData(form).entries());
  ["bars", "starting_capital", "risk_percent", "fee_bps", "slippage_bps", "max_holding_bars"].forEach(function (key) {
    values[key] = Number(values[key]);
  });
  values.symbol = values.symbol.trim().toUpperCase();
  runButton.disabled = true;
  runButton.textContent = "Loading completed candles…";
  statusLine.dataset.state = "";
  statusLine.textContent = "Fetching public candle history and replaying the selected fixed rules.";
  try {
    const response = await fetch("/api/strategy-backtest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(values),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "The replay could not be completed.");
    }
    renderResult(payload);
    statusLine.dataset.state = "success";
    statusLine.textContent = "Replay complete. Review the later holdout window before changing your rules.";
  } catch (error) {
    statusLine.dataset.state = "error";
    statusLine.textContent = error.message || "The replay could not be completed.";
  } finally {
    runButton.disabled = false;
    runButton.innerHTML = 'Run historical replay <span aria-hidden="true">↗</span>';
  }
});
