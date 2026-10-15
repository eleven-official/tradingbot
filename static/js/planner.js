const form = document.querySelector("#trade-council-form");
const result = document.querySelector("#plan-result");

const number = (value) => new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value);

function planMap(plan, input) {
  const levels = [input.stop_price, input.entry_price, input.target_price].map(Number);
  const min = Math.min(...levels);
  const max = Math.max(...levels);
  const padding = Math.max((max - min) * .22, max * .01);
  const scale = (value) => 182 - ((value - min + padding) / (max - min + padding * 2)) * 146;
  const line = (value, color, label) => `<line x1="62" x2="330" y1="${scale(value)}" y2="${scale(value)}" stroke="${color}" stroke-width="2"/><text x="8" y="${scale(value) + 4}" fill="${color}">${label}</text><text x="340" y="${scale(value) + 4}" fill="#e9edf6">${number(value)}</text>`;
  return `<svg class="plan-map" viewBox="0 0 410 205" role="img" aria-label="Trade plan with target, entry and stop levels">
    <rect x="61" y="16" width="270" height="166" rx="8" fill="#0b101a" stroke="rgba(233,237,246,.13)"/>
    ${line(input.target_price, "#8df2bf", "TARGET")}
    ${line(input.entry_price, "#8ac7ff", "ENTRY")}
    ${line(input.stop_price, "#ff9d9d", "STOP")}
  </svg>`;
}

function renderDecision(data, input) {
  const status = data.action.toLowerCase();
  result.innerHTML = `
    <div class="status ${status}">${data.action} · PAPER ONLY</div>
    <div class="card-heading"><p class="section-label">02 / COUNCIL DECISION</p><h2>${data.action === "BUY" ? `${data.plan.quantity} whole unit${data.plan.quantity === 1 ? "" : "s"}` : data.action}</h2></div>
    <p class="result-reason">${data.rationale}</p>
    ${planMap(data.plan, input)}
    <div class="metric-grid">
      <div><span>Quantity</span><strong>${data.plan.quantity}</strong></div>
      <div><span>Reward / risk</span><strong>${data.plan.reward_risk_ratio.toFixed(2)}×</strong></div>
      <div><span>Estimated loss</span><strong>${number(data.plan.estimated_loss)}</strong></div>
      <div><span>Target profit</span><strong>${number(data.plan.projected_profit)}</strong></div>
    </div>
    <ul class="review-list">${data.reviews.map((review) => `<li class="${review.verdict.toLowerCase()}"><b>${review.agent}</b><span>${review.verdict}</span><p>${review.reason}</p></li>`).join("")}</ul>
    <p class="disclaimer">Risk budget: ${number(data.plan.risk_budget)} · Planned notional: ${number(data.plan.notional)}<br>${data.disclaimer}</p>`;
}

function renderError(message) {
  result.innerHTML = `
    <div class="status error">CHECK THE THESIS</div>
    <div class="card-heading"><p class="section-label">02 / RESULT</p><h2>Plan not calculated</h2></div>
    <p class="result-reason">${message}</p>
    <p class="disclaimer">A valid long needs stop &lt; entry &lt; target. A valid short needs target &lt; entry &lt; stop.</p>`;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const values = Object.fromEntries(new FormData(form));
  Object.keys(values).forEach((key) => {
    if (!["side", "trend", "market_open"].includes(key)) values[key] = Number(values[key]);
  });
  values.market_open = values.market_open === "true";
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
  }
});

