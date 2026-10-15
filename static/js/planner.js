const form = document.querySelector("#risk-plan-form");
const result = document.querySelector("#plan-result");

const money = (value) => new Intl.NumberFormat(undefined, {
  style: "currency", currency: "USD", maximumFractionDigits: 2,
}).format(value);

function renderPlan(plan) {
  const status = plan.approved ? "approved" : "rejected";
  const label = plan.approved ? "PAPER PLAN ACCEPTED" : "PAPER PLAN REJECTED";
  result.innerHTML = `
    <div class="status ${status}">${label}</div>
    <div class="card-heading"><p class="section-label">02 / RESULT</p><h2>${plan.quantity} whole unit${plan.quantity === 1 ? "" : "s"}</h2></div>
    <p class="result-reason">${plan.reason}</p>
    <div class="metric-grid">
      <div><span>Quantity</span><strong>${plan.quantity}</strong></div>
      <div><span>Reward / risk</span><strong>${plan.reward_risk_ratio.toFixed(2)}×</strong></div>
      <div><span>Worst-case loss</span><strong>${money(plan.estimated_loss)}</strong></div>
      <div><span>Target profit</span><strong>${money(plan.projected_profit)}</strong></div>
    </div>
    <p class="disclaimer">Risk budget: ${money(plan.risk_budget)} · Planned notional: ${money(plan.notional)}<br>${plan.disclaimer}</p>`;
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
    if (key !== "side") values[key] = Number(values[key]);
  });
  try {
    const response = await fetch("/api/risk-plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(values),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || "Unable to build the paper plan.");
    renderPlan(body);
  } catch (error) {
    renderError(error.message);
  }
});

