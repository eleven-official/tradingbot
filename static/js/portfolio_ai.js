/* PORTFOLIO AI — paper autopilot that mirrors the tested multi-market book.
 *
 * The server (/api/fusion/ai/portfolio) replays every market's verified
 * rules to the latest completed bar and returns target weights (sum ≤ 1,
 * no leverage). This script keeps a paper book in the browser and trades it
 * toward those weights. Paper money only; no orders leave the browser.
 */
'use strict';
(() => {
  const root = document.getElementById('portfolio-ai');
  if (!root) return;
  const KEY = 'loki_portfolio_ai_v1';
  const LEASE = 'loki_portfolio_lease';
  const CHECK_MS = 5 * 60 * 1000;
  const FEE = 10 / 10000, SLIP = 5 / 10000;
  const BAND = 0.02; // rebalance when a target moves > 2% of equity
  const $ = (id) => document.getElementById(id);
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const money = (v) => (window.LokiCurrency ? window.LokiCurrency.format(v) : (v < 0 ? '-$' : '$') + Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
  const pct = (v, d = 1) => (Number.isFinite(Number(v)) ? `${Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(d)}%` : '—');
  const fresh = (cash = 10000) => ({ cash, start: cash, running: false, holdings: {}, trades: [], curve: [], log: [], lastCheck: 0 });

  let state = (() => { try { return { ...fresh(), ...(JSON.parse(localStorage.getItem(KEY) || 'null') || {}) }; } catch { return fresh(); } })();
  let plan = null, busy = false, timer = null;
  const save = () => { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch { /* storage full */ } };
  const log = (text, kind = 'info') => { state.log.unshift({ t: new Date().toISOString(), text, kind }); state.log.length = Math.min(state.log.length, 80); };

  function claim() {
    try {
      const held = Number(localStorage.getItem(LEASE) || 0);
      if (held && Date.now() - held < 60000 && !root.dataset.owner) return false;
      localStorage.setItem(LEASE, String(Date.now()));
      root.dataset.owner = '1';
      return true;
    } catch { return true; }
  }

  const priceOf = (sym) => {
    const row = plan && plan.positions.find((p) => p.symbol === sym);
    return row ? Number(row.price) : NaN;
  };
  function equity() {
    let total = state.cash;
    for (const [sym, h] of Object.entries(state.holdings)) {
      const px = priceOf(sym);
      total += h.qty * (Number.isFinite(px) ? px : h.avg);
    }
    return total;
  }

  function trade(sym, qty, px, why) {
    if (!(qty !== 0 && px > 0)) return;
    const side = qty > 0 ? 'buy' : 'sell';
    const fill = px * (side === 'buy' ? 1 + SLIP : 1 - SLIP);
    const notional = Math.abs(qty) * fill;
    const fee = notional * FEE;
    const h = state.holdings[sym] || { qty: 0, avg: 0 };
    if (side === 'buy') {
      h.avg = (h.avg * h.qty + fill * qty) / (h.qty + qty);
      h.qty += qty;
      state.cash -= notional + fee;
    } else {
      const sellQty = Math.min(h.qty, -qty);
      const pnl = (fill - h.avg) * sellQty - fee;
      h.qty -= sellQty;
      state.cash += sellQty * fill - fee;
      state.trades.unshift({ sym, qty: sellQty, price: fill, pnl, t: new Date().toISOString() });
      state.trades.length = Math.min(state.trades.length, 200);
    }
    if (h.qty <= 1e-9) delete state.holdings[sym]; else state.holdings[sym] = h;
    log(`${side.toUpperCase()} ${Math.abs(qty).toFixed(4)} ${sym} @ ${fill.toFixed(fill >= 1 ? 2 : 6)} — ${why}`, side === 'buy' ? 'good' : 'info');
  }

  function rebalance() {
    if (!plan) return 0;
    const eq = equity();
    const orders = [];
    for (const row of plan.positions) {
      const px = Number(row.price);
      if (!(px > 0)) continue;
      const have = (state.holdings[row.symbol] || { qty: 0 }).qty;
      const targetValue = row.weight * eq;
      const diffValue = targetValue - have * px;
      const exitAll = row.weight <= 0 && have > 0;
      if (!exitAll && Math.abs(diffValue) < Math.max(BAND * eq, 25)) continue;
      orders.push({ sym: row.symbol, qty: exitAll ? -have : diffValue / px, px, why: exitAll ? 'strategy exited this market' : row.weight > 0 && have === 0 ? 'new position in the tested book' : 'resize to target weight' });
    }
    for (const sym of Object.keys(state.holdings)) {
      if (!plan.positions.some((p) => p.symbol === sym)) {
        const px = Number(state.holdings[sym].avg);
        orders.push({ sym, qty: -state.holdings[sym].qty, px, why: 'market left the universe' });
      }
    }
    orders.sort((a, b) => a.qty - b.qty); // sells first free the cash
    let n = 0;
    for (const o of orders) {
      let qty = Math.round(o.qty * 1e4) / 1e4;
      if (qty > 0) qty = Math.min(qty, Math.floor((state.cash / (o.px * (1 + SLIP) * (1 + FEE))) * 1e4) / 1e4);
      if (Math.abs(qty) * o.px < 1) continue;
      trade(o.sym, qty, o.px, o.why);
      n += 1;
    }
    return n;
  }

  async function loadPlan(force) {
    const res = await fetch(`/api/fusion/ai/portfolio${force ? '?refresh=true' : ''}`, { cache: 'no-store', signal: AbortSignal.timeout(55000) });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || 'Portfolio plan unavailable');
    plan = data;
    return data;
  }

  async function step(force) {
    if (busy) return;
    busy = true;
    $('pf-message').textContent = 'Reading all 21 markets…';
    try {
      await loadPlan(force);
      if (state.running && claim()) {
        const n = rebalance();
        if (n) log(`Rebalanced ${n} market(s) toward the tested book (${(plan.gross * 100).toFixed(0)}% invested).`, 'good');
        state.curve.push({ t: Date.now(), e: equity() });
        if (state.curve.length > 500) state.curve.splice(0, state.curve.length - 500);
        state.lastCheck = Date.now();
        save();
      }
      $('pf-message').textContent = state.running
        ? `Running · plan as of ${plan.as_of} · next check in ~5 minutes while this page is open.`
        : `Plan as of ${plan.as_of}. Press Start to mirror it with paper money.`;
    } catch (error) {
      $('pf-message').textContent = `${error.message} — will retry.`;
    } finally {
      busy = false;
      render();
    }
  }

  function renderRecord() {
    const h = plan && plan.holdout, b = plan && plan.holdout_buy_hold;
    if (!h) { $('pf-record').innerHTML = ''; return; }
    const cell = (label, value, sub, tone) => `<div class="pf-stat"><span>${esc(label)}</span><strong style="color:${tone || 'inherit'}">${esc(value)}</strong><small>${esc(sub)}</small></div>`;
    $('pf-record').innerHTML =
      cell('Return / year (2023→now, unseen)', pct(h.cagr_pct), `buy & hold ${pct(b && b.cagr_pct)}`, '#a8f0c6') +
      cell('Sharpe ratio', Number(h.sharpe).toFixed(2), `buy & hold ${b ? Number(b.sharpe).toFixed(2) : '—'}`) +
      cell('Worst drop', pct(h.max_dd_pct), `buy & hold ${pct(b && b.max_dd_pct)}`, '#ffb3a7') +
      cell('Profitable months', `${Number(h.profitable_months_pct).toFixed(0)}%`, `risk target ${plan.target_vol_pct}% / yr`);
  }

  const PALETTE = ['#a8f0c6', '#8bdad4', '#6fd3bf', '#c9ffe2', '#7fb8e6', '#b8a8f0', '#f0c98b', '#e6a8d8', '#9fe0a8', '#88c9f0'];
  function donut() {
    const held = plan.positions.filter((p) => p.weight > 0);
    const C = 2 * Math.PI * 52;
    let offset = 0;
    const segs = held.map((p, i) => {
      const len = p.weight * C;
      const seg = `<circle class="seg" r="52" cx="66" cy="66" stroke="${PALETTE[i % PALETTE.length]}" stroke-dasharray="${len.toFixed(2)} ${(C - len).toFixed(2)}" stroke-dashoffset="${(-offset).toFixed(2)}" style="animation-delay:${(i * 0.06).toFixed(2)}s"/>`;
      offset += len;
      return seg;
    }).join('');
    const legend = held.slice(0, 6).map((p, i) => `<span><i style="background:${PALETTE[i % PALETTE.length]}"></i>${esc(p.symbol)} ${esc((p.weight * 100).toFixed(1))}%</span>`).join('') +
      (held.length > 6 ? `<span>+${held.length - 6} more</span>` : '') + `<span><i style="background:#2c3c48"></i>cash ${esc((plan.cash * 100).toFixed(1))}%</span>`;
    return `<div class="pf-donut-wrap"><div class="pf-donut-center"><svg class="pf-donut" viewBox="0 0 132 132" aria-hidden="true"><circle r="52" cx="66" cy="66" stroke="#1d2b35"/>${segs}</svg>` +
      `<div class="pf-donut-label"><span class="pf-donut-num">${esc(Math.round(plan.gross * 100))}%</span><small>INVESTED</small></div></div><div class="pf-legend">${legend}</div></div>`;
  }

  function renderAlloc() {
    if (!plan) return;
    const max = Math.max(0.05, ...plan.positions.map((p) => p.weight));
    const rows = plan.positions.map((p) => {
      const w = p.weight * 100;
      const held = p.in_position;
      return `<div class="pf-row${held ? '' : ' idle'}"><span class="pf-sym">${esc(p.symbol)}</span>` +
        `<span class="pf-bar"><i style="width:${(p.weight / max) * 100}%"></i></span>` +
        `<span class="pf-w">${held ? w.toFixed(1) + '%' : 'cash'}</span>` +
        `<span class="pf-meta">${held ? `since ${esc(p.entry_date)} · ${pct(p.unrealized_pct)}` : 'no uptrend'}</span></div>`;
    }).join('');
    $('pf-alloc').innerHTML = donut() + rows + `<div class="pf-row total"><span class="pf-sym">CASH</span><span class="pf-bar"><i style="width:${(plan.cash / Math.max(max, plan.cash)) * 100}%;background:#5b6b78"></i></span><span class="pf-w">${(plan.cash * 100).toFixed(1)}%</span><span class="pf-meta">${plan.active_markets} markets watched${plan.missing_markets && plan.missing_markets.length ? ` · ${plan.missing_markets.length} feed(s) missing` : ''}</span></div>`;
  }

  function renderBook() {
    const eq = equity();
    const invested = eq - state.cash;
    const realized = state.trades.reduce((a, t) => a + t.pnl, 0);
    const metric = (k, v) => `<div class="pf-metric"><span>${esc(k)}</span><strong>${esc(v)}</strong></div>`;
    $('pf-metrics').innerHTML = metric('Equity', money(eq)) + metric('Total P&L', `${money(eq - state.start)} (${pct((eq / state.start - 1) * 100, 2)})`) +
      metric('Invested', `${eq > 0 ? ((invested / eq) * 100).toFixed(0) : 0}%`) + metric('Realized P&L', money(realized));
    const rows = Object.entries(state.holdings).map(([sym, h]) => {
      const px = priceOf(sym);
      const value = h.qty * (Number.isFinite(px) ? px : h.avg);
      const pl = Number.isFinite(px) ? (px / h.avg - 1) * 100 : NaN;
      return `<tr><td>${esc(sym)}</td><td>${esc(h.qty.toFixed(4))}</td><td>${esc(money(value))}</td><td style="color:${pl >= 0 ? '#a8f0c6' : '#ffb3a7'}">${esc(pct(pl, 2))}</td></tr>`;
    }).join('');
    $('pf-positions').innerHTML = rows ? `<table><thead><tr><th>Market</th><th>Units</th><th>Value</th><th>P&amp;L</th></tr></thead><tbody>${rows}</tbody></table>` : '<p class="caption">No paper positions yet.</p>';
    $('pf-log').innerHTML = state.log.slice(0, 40).map((l) => `<li class="${esc(l.kind)}"><time>${esc(new Date(l.t).toLocaleString())}</time> ${esc(l.text)}</li>`).join('') || '<li>No rebalances yet.</li>';
    drawCurve();
  }

  function drawCurve() {
    const c = $('pf-curve');
    const pts = state.curve.map((p) => p.e);
    const ctx = c.getContext('2d');
    const dpr = window.devicePixelRatio || 1, w = c.clientWidth || 400, h = 120;
    c.width = w * dpr; c.height = h * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
    if (pts.length < 2) { ctx.fillStyle = '#5f7684'; ctx.font = '12px ui-monospace, monospace'; ctx.fillText('The equity curve draws itself as the book runs.', 10, 64); return; }
    const lo = Math.min(...pts, state.start), hi = Math.max(...pts, state.start), span = hi - lo || 1;
    const y = (v) => 8 + (1 - (v - lo) / span) * (h - 16);
    ctx.strokeStyle = 'rgba(162,181,196,.25)'; ctx.setLineDash([3, 3]); ctx.beginPath(); ctx.moveTo(0, y(state.start)); ctx.lineTo(w, y(state.start)); ctx.stroke(); ctx.setLineDash([]);
    ctx.strokeStyle = pts[pts.length - 1] >= state.start ? '#a8f0c6' : '#ffb3a7'; ctx.lineWidth = 2; ctx.beginPath();
    pts.forEach((v, i) => { const x = (i / (pts.length - 1)) * w; if (i) ctx.lineTo(x, y(v)); else ctx.moveTo(x, y(v)); });
    ctx.stroke();
  }

  function render() {
    $('pf-status').textContent = state.running ? 'Running' : 'Idle';
    $('pf-status').classList.toggle('good', state.running);
    $('pf-start').disabled = state.running;
    $('pf-pause').disabled = !state.running;
    $('pf-capital').disabled = state.running || Object.keys(state.holdings).length > 0;
    renderRecord(); renderAlloc(); renderBook();
  }

  $('pf-start').addEventListener('click', () => {
    if (!Object.keys(state.holdings).length && !state.trades.length) {
      const cap = Math.max(100, Number($('pf-capital').value) || 10000);
      state = { ...fresh(cap), log: state.log };
    }
    state.running = true;
    log(`Portfolio AI started with ${money(state.cash)} of paper cash.`, 'good');
    save(); step(false);
    clearInterval(timer); timer = setInterval(() => { if (state.running && !document.hidden) step(false); }, CHECK_MS);
  });
  $('pf-pause').addEventListener('click', () => { state.running = false; log('Paused — positions are held but no longer rebalanced.'); save(); render(); });
  $('pf-refresh').addEventListener('click', () => step(true));
  $('pf-reset').addEventListener('click', () => {
    if (!window.confirm('Reset the Portfolio AI paper book? Positions and history in this browser are cleared.')) return;
    state = fresh(Math.max(100, Number($('pf-capital').value) || 10000)); save(); render();
  });
  document.addEventListener('loki:currency', render);
  document.addEventListener('loki:view', (e) => { if (e.detail && e.detail.view === 'ai-trading' && !plan) step(false); });
  if (state.running) timer = setInterval(() => { if (state.running && !document.hidden) step(false); }, CHECK_MS);
  if (location.hash === '#ai-trading' || state.running) step(false); else render();
})();
