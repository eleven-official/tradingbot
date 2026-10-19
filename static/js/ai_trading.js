/* AI Trading: autonomous paper trading driven by the trained strategy book.
 *
 * The server runs the Director→Quant→Risk pipeline in review-only mode and
 * returns the auditable decision trail; this script performs the paper fills
 * locally (browser journal, no real orders). Paper money only.
 */
'use strict';
(() => {
  const STORAGE_KEY = 'loki_ai_paper_v1';
  const POLL_MS = 20000;

  const $ = (id) => document.getElementById(id);
  const escapeHtml = (value) =>
    String(value ?? '').replace(/[&<>\"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));

  const defaults = () => ({
    cash: 10000,
    startCash: 10000,
    symbol: 'SPY',
    running: false,
    position: null,
    trades: [],
    log: [],
    curve: [],
    lastPrice: null
  });

  let state = loadState();
  let timer = null;
  let busy = false;

  function loadState() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        return { ...defaults(), ...parsed };
      }
    } catch { /* corrupt state: start fresh */ }
    return defaults();
  }

  function save() {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch { /* storage full: ignore */ }
  }

  function message(text, ok) {
    const target = $('ai-message');
    if (!target) return;
    target.textContent = text || '';
    target.style.color = ok ? '#b8f0d8' : '';
  }

  function logLine(text, kind) {
    state.log.unshift({ t: new Date().toISOString(), text, kind: kind || 'info' });
    if (state.log.length > 60) state.log.length = 60;
  }

  const fmtMoney = (value) =>
    (value < 0 ? '-$' : '$') + Math.abs(value).toLocaleString('en-US', { maximumFractionDigits: 2, minimumFractionDigits: 2 });

  const fmtTime = (iso) => {
    try { return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }); }
    catch { return ''; }
  };

  const isCrypto = (symbol) => symbol.endsWith('-USD');

  function roundQty(symbol, qty) {
    return isCrypto(symbol) ? Math.max(0, Math.round(qty * 1e6) / 1e6) : Math.max(0, Math.floor(qty));
  }

  function equityNow() {
    let total = state.cash;
    if (state.position && state.lastPrice) total += state.position.qty * state.lastPrice;
    return total;
  }

  function openPosition(price, qty, trail) {
    const quant = trail.find((t) => t.agent === 'quant') || {};
    state.position = {
      symbol: state.symbol,
      qty,
      entry: price,
      stop: quant.stop || 0,
      target: quant.target || 0,
      opened: new Date().toISOString()
    };
    state.cash -= qty * price;
  }

  function closePosition(price, reason) {
    const pos = state.position;
    if (!pos) return;
    const pnl = (price - pos.entry) * pos.qty;
    state.cash += pos.qty * price;
    state.trades.unshift({
      symbol: pos.symbol, qty: pos.qty, entry: pos.entry, exit: price,
      pnl, opened: pos.opened, closed: new Date().toISOString(), reason
    });
    if (state.trades.length > 50) state.trades.length = 50;
    state.position = null;
    logLine(`Closed ${pos.symbol} @ ${price.toFixed(2)} (${reason}) — ${pnl >= 0 ? 'won' : 'lost'} ${fmtMoney(Math.abs(pnl))}`, pnl >= 0 ? 'good' : 'bad');
  }

  function consecutiveLosses() {
    let count = 0;
    for (const trade of state.trades) {
      if (trade.pnl < 0) count += 1;
      else break;
    }
    return count;
  }

  async function step() {
    if (busy || !state.running) return;
    if (document.hidden || $('ai-trading').hidden) return;
    busy = true;
    try {
      const res = await fetch('/api/fusion/ai/step', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: state.symbol,
          equity: equityNow(),
          open_positions: state.position ? 1 : 0,
          has_position: !!state.position,
          equity_start: state.startCash,
          consecutive_losses: consecutiveLosses()
        })
      });
      if (!res.ok) {
        const detail = ((await res.json().catch(() => ({}))) || {}).detail;
        logLine(detail || 'AI feed unavailable — will retry.', 'warn');
        render();
        return;
      }
      const data = await res.json();
      state.lastPrice = data.price;
      const trail = data.trail || [];
      const quant = trail.find((t) => t.agent === 'quant') || {};
      const risk = trail.find((t) => t.agent === 'risk') || {};
      const director = trail.find((t) => t.agent === 'director') || {};

      // Auto-exit checks first: stops and targets outrank new entries.
      if (state.position && state.position.symbol === data.symbol) {
        if (state.position.stop && data.price <= state.position.stop) closePosition(data.price, 'stop hit');
        else if (state.position.target && data.price >= state.position.target) closePosition(data.price, 'target reached');
      }

      const action = (quant.action || 'HOLD').toUpperCase();
      if (action === 'BUY' && risk.approved && !state.position) {
        let qty = Number(risk.qty) > 0 ? Number(risk.qty) : roundQty(data.symbol, (state.cash * 0.95) / data.price);
        qty = roundQty(data.symbol, qty);
        if (qty > 0 && qty * data.price <= state.cash) {
          openPosition(data.price, qty, trail);
          logLine(`BUY ${qty} ${data.symbol} @ ${data.price.toFixed(2)} — ${quant.confidence ?? '?'}% confidence · ${director.thesis || ''}`, 'good');
        } else {
          logLine(`BUY signal skipped — not enough paper cash.`, 'warn');
        }
      } else if (action === 'SELL' && state.position && state.position.symbol === data.symbol) {
        closePosition(data.price, 'AI exit signal');
      } else if (action === 'BUY' && risk.approved === false && !state.position) {
        logLine(`HOLD — risk declined: ${risk.reason || 'unknown'}`, 'info');
      } else {
        const reason = (quant.reasons || []).slice(0, 2).join(' · ');
        logLine(`HOLD ${data.symbol} @ ${data.price.toFixed(2)}${reason ? ' — ' + reason : ''}`, 'info');
      }
      renderTrail(data);
      state.curve.push({ t: Date.now(), e: equityNow() });
      if (state.curve.length > 240) state.curve.splice(0, state.curve.length - 240);
      render();
    } catch {
      logLine('Connection hiccup — will retry.', 'warn');
      render();
    } finally {
      busy = false;
    }
  }

  function renderTrail(data) {
    const target = $('ai-trail');
    if (!target) return;
    const badges = {
      director: ['DIRECTOR', '#8bdad4'],
      quant: ['QUANT', '#b8f0d8'],
      risk: ['RISK', '#f0c98b'],
      execution: ['EXECUTION', '#9fb0c2']
    };
    const cards = (data.trail || []).map((entry) => {
      const [name, color] = badges[entry.agent] || [entry.agent.toUpperCase(), '#9fb0c2'];
      let body = '';
      if (entry.agent === 'director') body = escapeHtml(entry.thesis || '') + `<br><span style="color:#7f93a8">posture: ${escapeHtml(entry.posture || '—')}</span>`;
      if (entry.agent === 'quant') {
        body = entry.action === 'HOLD' || !entry.action
          ? `<strong>HOLD</strong>${entry.reasons && entry.reasons.length ? '<br>' + escapeHtml(entry.reasons.slice(0, 3).join(' · ')) : ''}`
          : `<strong style="color:${entry.action === 'BUY' ? '#b8f0d8' : '#ff9d9d'}">${escapeHtml(entry.action)}</strong> @ ${escapeHtml(Number(entry.entry).toFixed(2))}<br>` +
            `stop ${escapeHtml(Number(entry.stop).toFixed(2))} · target ${escapeHtml(Number(entry.target).toFixed(2))}<br>` +
            `<span style="color:#7f93a8">score ${escapeHtml(entry.score)} · confidence ${escapeHtml(entry.confidence)}%</span>` +
            (entry.reasons && entry.reasons.length ? '<br>' + escapeHtml(entry.reasons.slice(0, 3).join(' · ')) : '');
      }
      if (entry.agent === 'risk') {
        body = entry.approved
          ? `<strong style="color:#b8f0d8">Approved</strong> — size ${escapeHtml(String(entry.qty))}`
          : `<strong>Declined</strong> — ${escapeHtml(entry.reason || 'no signal')}`;
      }
      if (entry.agent === 'execution') {
        body = 'Paper fill happens in your browser journal — no real orders.';
      }
      return `<article style="flex:1 1 220px;border:1px solid rgba(139,218,212,.18);border-radius:12px;padding:12px 14px;background:rgba(10,18,32,.6)">` +
        `<p style="letter-spacing:.14em;font-size:10.5px;color:${color};margin-bottom:6px">${name}</p>` +
        `<p style="font-size:13px;line-height:1.5;color:#e7f0ff">${body}</p></article>`;
    });
    const profileBadge = data.trained_profile_applied
      ? `<span class="tag">Trained profile active</span>`
      : `<span class="tag">Default params (no trained profile)</span>`;
    target.innerHTML =
      `<div style="display:flex;gap:10px;align-items:center;margin-bottom:10px">` +
      `<strong style="font-size:15px">${escapeHtml(data.symbol)}</strong>` +
      `<span style="color:#9fb0c2;font-size:13px">@ ${escapeHtml(Number(data.price).toFixed(2))} · regime ${escapeHtml(data.regime || '—')}</span>` +
      profileBadge + `</div>` +
      `<div style="display:flex;flex-wrap:wrap;gap:10px">${cards.join('')}</div>`;
  }

  function drawCurve() {
    const canvas = $('ai-curve');
    const note = $('ai-curve-note');
    if (!canvas) return;
    const width = canvas.clientWidth || 600;
    const height = 120;
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, width, height);
    const points = state.curve.map((p) => p.e);
    if (points.length < 2) {
      if (note) note.textContent = 'The equity curve draws itself as the AI trades.';
      return;
    }
    const min = Math.min(...points, state.startCash);
    const max = Math.max(...points, state.startCash);
    const span = max - min || 1;
    const pad = 6;
    const xAt = (i) => (points.length === 1 ? width : (i / (points.length - 1)) * (width - 2 * pad) + pad);
    const yAt = (v) => height - pad - ((v - min) / span) * (height - 2 * pad);
    // Baseline (starting capital) reference line.
    ctx.strokeStyle = 'rgba(127,147,168,.35)';
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(pad, yAt(state.startCash));
    ctx.lineTo(width - pad, yAt(state.startCash));
    ctx.stroke();
    ctx.setLineDash([]);
    const up = points[points.length - 1] >= state.startCash;
    const stroke = up ? '#8bdad4' : '#ff9d9d';
    const gradient = ctx.createLinearGradient(0, 0, 0, height);
    gradient.addColorStop(0, up ? 'rgba(139,218,212,.25)' : 'rgba(255,157,157,.25)');
    gradient.addColorStop(1, 'rgba(10,18,32,0)');
    ctx.beginPath();
    ctx.moveTo(xAt(0), yAt(points[0]));
    points.forEach((v, i) => ctx.lineTo(xAt(i), yAt(v)));
    ctx.strokeStyle = stroke;
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.lineTo(xAt(points.length - 1), height - pad);
    ctx.lineTo(xAt(0), height - pad);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();
    if (note) {
      const change = points[points.length - 1] - state.startCash;
      note.textContent = `Equity curve · ${change >= 0 ? '+' : '-'}${fmtMoney(Math.abs(change)).replace('$', '$')} vs start · last ${points.length} checks.`;
    }
  }

  function render() {
    const stats = $('ai-stats');
    if (stats) {
      const wins = state.trades.filter((t) => t.pnl > 0).length;
      const realized = state.trades.reduce((sum, t) => sum + t.pnl, 0);
      const winRate = state.trades.length ? (100 * wins) / state.trades.length : null;
      const pnls = state.trades.map((t) => t.pnl);
      const best = pnls.length ? Math.max(...pnls) : null;
      const worst = pnls.length ? Math.min(...pnls) : null;
      stats.innerHTML =
        metric('Paper equity', fmtMoney(equityNow())) +
        metric('Realized P&L', fmtMoney(realized)) +
        metric('Closed trades', String(state.trades.length)) +
        metric('Win rate', winRate === null ? '—' : winRate.toFixed(0) + '%') +
        metric('Best trade', best === null ? '—' : fmtMoney(best)) +
        metric('Worst trade', worst === null ? '—' : fmtMoney(worst));
    }
    const posTarget = $('ai-position');
    if (posTarget) {
      if (!state.position) {
        posTarget.innerHTML = '<p class="muted">No open paper position.</p>';
      } else {
        const pos = state.position;
        const unrealized = state.lastPrice ? (state.lastPrice - pos.entry) * pos.qty : null;
        posTarget.innerHTML =
          `<div class="inline-metrics" style="margin:10px 0">` +
          metric('Open', `${pos.qty} ${escapeHtml(pos.symbol)}`) +
          metric('Entry', '$' + Number(pos.entry).toFixed(2)) +
          metric('Stop', pos.stop ? '$' + Number(pos.stop).toFixed(2) : '—') +
          metric('Target', pos.target ? '$' + Number(pos.target).toFixed(2) : '—') +
          metric('Unrealized', unrealized === null ? '—' : fmtMoney(unrealized)) +
          `</div>`;
      }
    }
    const trades = $('ai-trades');
    if (trades) {
      if (!state.trades.length) {
        trades.innerHTML = '<p class="muted">No closed trades yet. The AI only fires when its verified edge lines up.</p>';
      } else {
        const rows = state.trades.slice(0, 12).map((t) =>
          `<tr><td>${fmtTime(t.closed)}</td><td>${escapeHtml(t.symbol)}</td><td>${escapeHtml(String(t.qty))}</td>` +
          `<td>$${Number(t.entry).toFixed(2)}</td><td>$${Number(t.exit).toFixed(2)}</td>` +
          `<td style="color:${t.pnl >= 0 ? '#b8f0d8' : '#ff9d9d'}">${fmtMoney(t.pnl)}</td><td>${escapeHtml(t.reason)}</td></tr>`);
        trades.innerHTML =
          `<table><thead><tr><th>Closed</th><th>Symbol</th><th>Qty</th><th>Entry</th><th>Exit</th><th>P&L</th><th>Why</th></tr></thead>` +
          `<tbody>${rows.join('')}</tbody></table>`;
      }
    }
    const logEl = $('ai-log');
    if (logEl) {
      logEl.innerHTML = state.log.length
        ? state.log.map((l) => `<div style="padding:4px 0;border-bottom:1px dashed rgba(139,218,212,.1);font-size:12.5px;color:${l.kind === 'good' ? '#b8f0d8' : l.kind === 'bad' ? '#ff9d9d' : l.kind === 'warn' ? '#f0c98b' : '#9fb0c2'}"><span style="color:#7f93a8">${fmtTime(l.t)}</span> ${escapeHtml(l.text)}</div>`).join('')
        : '<p class="muted">The decision log will fill in as the AI works.</p>';
    }
    drawCurve();
    const tag = $('ai-status-tag');
    if (tag) {
      tag.textContent = state.running ? `Running · ${state.symbol}` : 'Idle';
      tag.style.color = state.running ? '#b8f0d8' : '';
    }
    const start = $('ai-start');
    const stop = $('ai-stop');
    if (start && stop) {
      start.disabled = state.running;
      stop.disabled = !state.running;
    }
    const symbolSelect = $('ai-symbol');
    if (symbolSelect) symbolSelect.disabled = state.running;
  }

  async function scanAll() {
    const button = $('ai-scan');
    if (!button || button.disabled || busy) return;
    button.disabled = true;
    try {
      const symbols = [...$('ai-symbol').options].map((o) => o.value);
      for (const symbol of symbols) {
        try {
          const res = await fetch('/api/fusion/ai/step', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              symbol,
              equity: equityNow(),
              open_positions: state.position && state.position.symbol === symbol ? 1 : 0,
              has_position: !!(state.position && state.position.symbol === symbol),
              equity_start: state.startCash,
              consecutive_losses: consecutiveLosses()
            })
          });
          if (!res.ok) { logLine(`${symbol}: AI feed unavailable.`, 'warn'); continue; }
          const data = await res.json();
          const trail = data.trail || [];
          const quant = trail.find((t) => t.agent === 'quant') || {};
          const risk = trail.find((t) => t.agent === 'risk') || {};
          const action = (quant.action || 'HOLD').toUpperCase();
          let note = '';
          if (action !== 'HOLD') {
            note = risk.approved ? ` · risk approved (${risk.qty})` : ` · risk declined: ${risk.reason || ''}`;
          }
          logLine(
            `${symbol} @ ${Number(data.price).toFixed(2)} → ${action} · regime ${data.regime || '—'}${note}`,
            action === 'BUY' && risk.approved ? 'good' : 'info'
          );
          if (state.symbol === symbol) {
            state.lastPrice = data.price;
            renderTrail(data);
          }
        } catch {
          logLine(`${symbol}: connection hiccup.`, 'warn');
        }
      }
      logLine('Scan complete — next auto-check in 20s.', 'info');
      render();
    } finally {
      button.disabled = false;
    }
  }

  const metric = (label, value) =>
    `<article class="metric"><p>${label}</p><strong>${value}</strong></article>`;

  async function loadSymbols() {
    const select = $('ai-symbol');
    if (!select) return;
    try {
      const res = await fetch('/api/fusion/research-book', { cache: 'no-store' });
      if (!res.ok) return;
      const book = await res.json();
      const symbols = (book.symbols || []).map((s) => s.symbol).filter(Boolean);
      if (!symbols.length) return;
      select.innerHTML = symbols.map((s) => `<option${s === state.symbol ? ' selected' : ''}>${escapeHtml(s)}</option>`).join('');
      state.symbol = select.value;
    } catch { /* leave the default */ }
  }

  function startLoop() {
    if (timer) clearInterval(timer);
    timer = setInterval(step, POLL_MS);
  }

  function bind() {
    $('ai-start').addEventListener('click', () => {
      state.running = true;
      state.symbol = $('ai-symbol').value;
      state.startCash = Number($('ai-capital').value) || state.startCash;
      if (!state.trades.length && !state.position) state.cash = state.startCash;
      logLine(`AI trading started on ${state.symbol} with ${fmtMoney(state.cash)} paper cash.`, 'good');
      message(`AI is now checking ${state.symbol} every 20 seconds — paper money only.`, true);
      save();
      render();
      step();
      startLoop();
    });
    $('ai-stop').addEventListener('click', () => {
      const proceed = !state.position || window.confirm('A paper position is open. Pause anyway? It will not be monitored while paused.');
      if (!proceed) return;
      state.running = false;
      if (timer) { clearInterval(timer); timer = null; }
      logLine('AI trading paused.', 'warn');
      message('Paused — the AI stopped checking the market.');
      save();
      render();
    });
    $('ai-reset').addEventListener('click', () => {
      if (!window.confirm('Flatten everything and restart the paper account with fresh capital?')) return;
      const keepSymbol = state.symbol;
      state = defaults();
      state.symbol = keepSymbol;
      if (timer) { clearInterval(timer); timer = null; }
      logLine('Paper account reset.', 'warn');
      message('Paper account reset — fresh capital, empty journal.');
      save();
      $('ai-capital').value = state.startCash;
      render();
    });
    $('ai-symbol').addEventListener('change', (event) => {
      state.symbol = event.target.value;
      save();
      render();
    });
    $('ai-scan').addEventListener('click', scanAll);
  }

  const init = async () => {
    if (!$('ai-trading')) return;
    await loadSymbols();
    bind();
    $('ai-capital').value = state.startCash;
    render();
    if (state.running) {
      startLoop();
      step();
    }
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
