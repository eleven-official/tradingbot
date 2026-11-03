"use strict";

const proofForm = {
  button: document.querySelector("#run-proof"),
  description: document.querySelector("#proof-description"),
  symbol: document.querySelector("#proof-symbol"),
  bars: document.querySelector("#proof-bars"),
  message: document.querySelector("#proof-message"),
  results: document.querySelector("#proof-results"),
};

function proofText(value) {
  return value === null || value === undefined ? "—" : String(value);
}

function proofPercent(value) {
  return Number.isFinite(Number(value)) ? `${Number(value).toFixed(2)}%` : "—";
}

function verdictClass(status) {
  if (status.startsWith("rejected")) return "proof-verdict-rejected";
  if (status.startsWith("insufficient")) return "proof-verdict-insufficient";
  return "proof-verdict-supported";
}

function renderProofChecks(checks) {
  const list = document.createElement("ul");
  list.className = "proof-checks";
  for (const check of checks) {
    const item = document.createElement("li");
    item.innerHTML = `<b class="proof-status proof-${check.status}">${check.check.replace(/_/g, " ")}</b> <span></span>`;
    item.querySelector("span").textContent = check.detail;
    list.append(item);
  }
  return list;
}

function renderProofReviewers(reviewers) {
  const grid = document.createElement("div");
  grid.className = "proof-reviewers";
  for (const reviewer of reviewers) {
    const card = document.createElement("div");
    card.className = "proof-reviewer";
    const role = document.createElement("b");
    role.textContent = reviewer.role;
    const verdict = document.createElement("span");
    verdict.className = `proof-status proof-${reviewer.verdict}`;
    verdict.textContent = reviewer.verdict;
    const reason = document.createElement("p");
    reason.textContent = reviewer.reason;
    card.append(role, verdict, reason);
    grid.append(card);
  }
  return grid;
}

function renderProofBattery(battery) {
  const table = document.createElement("table");
  table.className = "table-scroll proof-battery";
  const headRow = document.createElement("thead");
  const head = document.createElement("tr");
  const cells = ["Run", "Fee (bps)", "Slippage (bps)", "Holdout trades", "Expectancy (R)", "Net return", "Buy &amp; hold"];
  head.innerHTML = cells.map(function (cell) { return `<th>${cell}</th>`; }).join("");
  headRow.append(head);
  table.append(headRow);
  const body = document.createElement("tbody");
  for (const run of battery) {
    const row = document.createElement("tr");
    row.innerHTML = `<td>${run.run}</td><td>${proofPercent(run.fee_bps)}</td><td>${proofPercent(run.slippage_bps)}</td><td>${run.holdout.trade_count}</td><td>${Number(run.holdout.expectancy_r).toFixed(3)}R</td><td>${proofPercent(run.holdout.net_return_percent)}</td><td>${proofPercent(run.benchmark_holdout_return_percent)}</td>`;
    body.append(row);
  }
  table.append(body);
  return table;
}

function renderProof(data) {
  const body = document.createElement("div");
  const band = document.createElement("div");
  band.className = `proof-verdict ${verdictClass(data.verdict.status)}`;
  const title = document.createElement("b");
  title.textContent = data.verdict.status.toUpperCase();
  const headline = document.createElement("p");
  headline.textContent = data.verdict.headline;
  band.append(title, headline);
  for (const reason of data.verdict.reasons) {
    const line = document.createElement("li");
    line.textContent = reason;
    band.append(line);
  }

  const spec = document.createElement("div");
  spec.className = "proof-spec";
  const specTitle = document.createElement("b");
  specTitle.textContent = `Compiled rules — ${data.spec.family_name}`;
  spec.append(specTitle);
  for (const key of ["entry_rule", "exit_rule", "sizing_rule"]) {
    const line = document.createElement("p");
    line.innerHTML = `<b>${key.replace("_rule", " rule")}:</b> `;
    line.append(document.createTextNode(data.spec[key]));
    spec.append(line);
  }
  if (data.spec.declared_drawdown_limit !== undefined && data.spec.declared_drawdown_limit !== null) {
    const limit = document.createElement("p");
    limit.innerHTML = `<b>declared drawdown limit:</b> ${proofPercent(data.spec.declared_drawdown_limit)}`;
    spec.append(limit);
  }
  if (Array.isArray(data.spec.not_modelled) && data.spec.not_modelled.length) {
    const notModelled = document.createElement("p");
    notModelled.innerHTML = "<b>explicitly not modelled:</b> ";
    notModelled.append(document.createTextNode(data.spec.not_modelled.join("; ")));
    spec.append(notModelled);
  }

  const checksTitle = document.createElement("h3");
  checksTitle.textContent = "Falsification checks";
  const batteryTitle = document.createElement("h3");
  batteryTitle.textContent = "Cost battery (parameters never re-fitted between runs)";
  const reviewersTitle = document.createElement("h3");
  reviewersTitle.textContent = "Reviewers";

  const limitations = document.createElement("div");
  limitations.className = "proof-limitations";
  const limTitle = document.createElement("b");
  limTitle.textContent = "Limitations";
  limitations.append(limTitle);
  const limList = document.createElement("ul");
  for (const limitation of data.limitations) {
    const item = document.createElement("li");
    item.textContent = limitation;
    limList.append(item);
  }
  limitations.append(limList);

  const foot = document.createElement("p");
  foot.className = "caption";
  foot.innerHTML = `${proofText(data.symbol)} · ${proofText(data.interval)} · ${data.bar_count} completed bars · fingerprint <code></code>`;
  foot.querySelector("code").textContent = `${data.fingerprint.algorithm}:${data.fingerprint.value.slice(0, 24)}…`;

  body.append(
    band, spec, checksTitle, renderProofChecks(data.checks),
    batteryTitle, renderProofBattery(data.battery),
    reviewersTitle, renderProofReviewers(data.reviewers),
    limitations, foot,
  );
  proofForm.results.replaceChildren(body);
  proofForm.results.hidden = false;
}

proofForm.button.addEventListener("click", async function () {
  const description = String(proofForm.description.value || "").trim();
  if (!description) {
    proofForm.message.dataset.state = "error";
    proofForm.message.textContent = "Describe the strategy — even one sentence is enough to compile.";
    return;
  }
  proofForm.button.disabled = true;
  proofForm.button.textContent = "Running the battery…";
  proofForm.message.dataset.state = "";
  proofForm.message.textContent = "Fetching public candles and running the falsification battery at three cost levels.";
  try {
    const response = await fetch("/api/proof/assess", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        description,
        symbol: String(proofForm.symbol.value || "").trim().toUpperCase(),
        interval: "1h",
        bars: Number(proofForm.bars.value) || 1000,
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "The proof assessment could not be completed.");
    renderProof(payload);
    proofForm.message.dataset.state = "success";
    proofForm.message.textContent = "Report ready. Same words, same candles, same config — same fingerprint.";
  } catch (error) {
    proofForm.message.dataset.state = "error";
    proofForm.message.textContent = error.message || "The proof assessment could not be completed.";
  } finally {
    proofForm.button.disabled = false;
    proofForm.button.textContent = "Attempt falsification →";
  }
});
